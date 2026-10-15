"""
Descarga el PDF que genera el dashboard de Centro de Costos y lo manda por mail.
Corre local o en GitHub Actions (ver .github/workflows/reporte-cdc.yml).
"""
import os
import base64
import smtplib
import datetime
from pathlib import Path
from email.message import EmailMessage
from playwright.sync_api import sync_playwright

# ---------- CONFIG ----------
URL = os.environ.get("CDC_URL", "https://dashboard-rentabilidad-neix.vercel.app")
BTN_PDF = os.environ.get("CDC_BTN_PDF", "#generar-reporte-btn")  # selector del botón que genera el PDF

# "antes": clicks a hacer antes de apretar el botón (ej. elegir el área/tab).
# Si el botón ya exporta todo de una, dejá un solo reporte con "antes": ["text=Reportes Mensuales"].
REPORTES = [
    {"area": "Neix", "antes": ["text=Reportes Mensuales"], "para": ["lfeit@neix.com.ar", "mupon@neix.com.ar", "fgilges@neix.com.ar"]},
]
CC = [x for x in os.environ.get("MAIL_CC", "").split(",") if x]

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_PASS"]
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)

# Firma del mail (igual a la de Outlook). El GIF tiene que estar en el repo como firma.gif
FIRMA_TXT = """Luna Feit
Analista de Proyectos
Tel. 4859-1552
P8 Buenavista - Don Francisco 3345, Piso 5, San Fernando"""

FIRMA_HTML = """
<div style="font-family:'Segoe UI',Calibri,Arial,sans-serif;font-size:11pt;color:#222;line-height:1.35">
  <b>Luna Feit</b><br>
  <b style="color:#AB1930">Analista de Proyectos</b><br>
  Tel. 4859-1552<br>
  P8 Buenavista - Don Francisco 3345, Piso 5, San Fernando
</div>
<img src="cid:firma" width="341" height="125" alt="NEIX" style="display:block;margin-top:6px;border:0">
"""
FIRMA_GIF = Path(__file__).parent / "firma.gif"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
OUT = Path("pdfs"); OUT.mkdir(exist_ok=True)
# ----------------------------


def periodo():
    hoy = datetime.date.today()
    mes_ant = (hoy.replace(day=1) - datetime.timedelta(days=1))
    return f"{MESES[mes_ant.month - 1]} {mes_ant.year}"


def login(page):
    try:
        page.wait_for_selector("input[type=password]", timeout=10_000)
    except Exception:
        return  # no pidió contraseña
    page.fill("input[type=password]", os.environ["DASH_PASS"])
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")


PRINT_HOOK = "window.__printed = false; window.print = () => { window.__printed = true; };"


def capturar_salida(page, path, boton):
    """El botón puede: descargar un archivo, abrir una pestaña nueva, o llamar a imprimir."""
    descargas, popups = [], []
    page.on("download", lambda d: descargas.append(d))

    def nueva_pestana(p):
        popups.append(p)
        p.on("download", lambda d: descargas.append(d))   # el PDF a veces se baja desde la pestaña nueva
    page.context.on("page", nueva_pestana)
    page.evaluate(PRINT_HOOK)

    boton.click()

    for _ in range(90):  # hasta 90 segundos
        if descargas or popups or page.evaluate("window.__printed"):
            break
        page.wait_for_timeout(1000)

    if popups and not descargas:
        destino = popups[-1]
        for _ in range(20):                       # espera a que la pestaña tenga una URL real
            if destino.url not in ("", "about:blank") or descargas:
                break
            page.wait_for_timeout(1000)
        try:
            destino.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

    if descargas:                                   # descarga (directa o desde la pestaña nueva)
        descargas[-1].save_as(path)
        return

    if popups:                                      # pestaña nueva con el PDF
        destino = popups[-1]
        url = destino.url
        print("Pestaña nueva abrió:", url)
        try:
            destino.screenshot(path=str(OUT / "pestana.png"))
        except Exception:
            pass
        if url.startswith("blob:") or url.startswith("data:"):
            b64 = destino.evaluate("""async (u) => {
                const b = await (await fetch(u)).blob();
                return await new Promise(r => { const f = new FileReader();
                    f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); });
            }""", url)
            path.write_bytes(base64.b64decode(b64))
            return
        if url.startswith("http"):
            r = page.context.request.get(url)
            if "pdf" in r.headers.get("content-type", "").lower():
                path.write_bytes(r.body())
                return
    elif page.evaluate("window.__printed"):         # llamó a imprimir
        destino = page
    else:
        raise RuntimeError("El botón no descargó, no abrió pestaña ni mandó a imprimir")

    destino.wait_for_timeout(2000)
    destino.emulate_media(media="print")
    destino.pdf(path=str(path), format="A4", print_background=True,
                prefer_css_page_size=True)


def descargar(page, rep):
    page.goto(URL, wait_until="networkidle")
    login(page)
    path = OUT / "CDC_Neix.pdf"
    try:
        page.wait_for_timeout(5000)
        for sel in rep["antes"]:
            page.click(sel)
            page.wait_for_timeout(3000)
        boton = page.get_by_text("Ver PDF", exact=True).first   # primera fila = mes más reciente
        boton.wait_for(state="visible", timeout=60_000)
        mes = boton.evaluate("""el => {
            const fila = el.closest('tr') || el.parentElement.parentElement;
            return (fila.firstElementChild || fila).innerText.trim();
        }""")
        path = OUT / f"Reporte Mensual NEIX · {mes}.pdf"
        capturar_salida(page, path, boton)
    except Exception:
        page.screenshot(path=str(OUT / "error.png"), full_page=True)
        raise
    return path, mes


def enviar(smtp, rep, pdf, per):
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(rep["para"])
    if CC:
        msg["Cc"] = ", ".join(CC)
    msg["Subject"] = f"Reporte Mensual Costos - {per}"
    texto = (f"Hola Peli y Lucas,\n\nAdjunto el reporte mensual de costos "
             f"correspondiente a {per}.\n\nSaludos,\n\n{FIRMA_TXT}")
    html = f"""<div style="font-family:'Segoe UI',Calibri,Arial,sans-serif;font-size:11pt;color:#222">
<p>Hola Peli y Lucas,</p>
<p>Adjunto el reporte mensual de costos correspondiente a {per}.</p>
<p>Saludos,</p>
</div>
{FIRMA_HTML}"""
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    if FIRMA_GIF.exists():
        msg.get_payload()[1].add_related(FIRMA_GIF.read_bytes(), maintype="image",
                                         subtype="gif", cid="<firma>")
    msg.add_attachment(pdf.read_bytes(), maintype="application",
                       subtype="pdf", filename=pdf.name)
    smtp.send_message(msg)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(accept_downloads=True).new_page()
        pdfs = [(rep, *descargar(page, rep)) for rep in REPORTES]
        browser.close()

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        for rep, pdf, mes in pdfs:
            enviar(smtp, rep, pdf, mes)
            print(f"Enviado {pdf.name} → {', '.join(rep['para'])}")


if __name__ == "__main__":
    main()
