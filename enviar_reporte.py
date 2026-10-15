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
    """El botón puede: descargar un archivo, abrir una pestaña nueva, o llamar a imprimir.
    Esto cubre los tres casos."""
    descargas, popups = [], []
    page.on("download", lambda d: descargas.append(d))
    page.context.on("page", lambda p: popups.append(p))
    page.evaluate(PRINT_HOOK)

    boton.click()

    for _ in range(90):  # hasta 90 segundos
        if descargas or popups or page.evaluate("window.__printed"):
            break
        page.wait_for_timeout(1000)

    if descargas:                                   # caso 1: descarga directa
        descargas[0].save_as(path)
        return

    if popups:                                      # caso 2: abre pestaña nueva
        destino = popups[-1]
        destino.wait_for_load_state("load")
        destino.wait_for_timeout(4000)
        url = destino.url
        if url.startswith("blob:") or url.startswith("data:") or url.lower().endswith(".pdf"):
            b64 = destino.evaluate("""async (u) => {
                const b = await (await fetch(u)).blob();
                return await new Promise(r => { const f = new FileReader();
                    f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); });
            }""", url)
            path.write_bytes(base64.b64decode(b64))
            return
    elif page.evaluate("window.__printed"):         # caso 3: llamó a imprimir
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
            return fila.innerText.trim().split(/[\t\n]/)[0].trim();
        }""")
        path = OUT / f"CDC_Neix_{mes.replace(' ', '_')}.pdf"
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
    msg["Subject"] = f"Centro de Costos – {per}"
    msg.set_content(f"Hola,\n\nAdjunto el reporte de Centro de Costos "
                    f"correspondiente a {per}.\n\nSaludos,\nLuna")
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
