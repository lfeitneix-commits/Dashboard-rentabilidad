"""
Descarga el PDF que genera el dashboard de Centro de Costos y lo manda por mail.
Corre local o en GitHub Actions (ver .github/workflows/reporte-cdc.yml).
"""
import os
import smtplib
import datetime
from pathlib import Path
from email.message import EmailMessage
from playwright.sync_api import sync_playwright

# ---------- CONFIG ----------
URL = os.environ.get("CDC_URL", "https://dashboard-rentabilidad-neix.vercel.app")
BTN_PDF = os.environ.get("CDC_BTN_PDF", "#generar-reporte-btn")  # selector del botón que genera el PDF

# "antes": clicks a hacer antes de apretar el botón (ej. elegir el área/tab).
# Si el botón ya exporta todo de una, dejá un solo reporte con "antes": [].
REPORTES = [
    {"area": "Neix", "antes": [], "para": ["lfeit@neix.com.ar", "mupon@neix.com.ar", "fgilges@neix.com.ar"]},
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


def descargar(page, rep):
    page.goto(URL, wait_until="networkidle")
    login(page)
    page.wait_for_selector(BTN_PDF, timeout=60_000)
    page.wait_for_timeout(5000)   # da tiempo a que carguen datos y gráficos
    for sel in rep["antes"]:
        page.click(sel)
        page.wait_for_timeout(1500)
    with page.expect_download(timeout=90_000) as d:
        page.click(BTN_PDF)
    path = OUT / f"CDC_{rep['area'].replace(' ', '_')}.pdf"
    d.value.save_as(path)
    return path


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
    per = periodo()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(accept_downloads=True).new_page()
        pdfs = [(rep, descargar(page, rep)) for rep in REPORTES]
        browser.close()

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        for rep, pdf in pdfs:
            enviar(smtp, rep, pdf, per)
            print(f"Enviado {pdf.name} → {', '.join(rep['para'])}")


if __name__ == "__main__":
    main()
