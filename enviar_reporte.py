"""
Manda por mail el último Reporte Mensual del Centro de Costos.
Los PDFs ya están en el repo (carpeta reportes/) y la lista está en el HTML
del dashboard (REPORTES_MENSUALES), así que no hace falta abrir el navegador.
"""
import os
import re
import smtplib
from pathlib import Path
from email.message import EmailMessage

REPO = Path(__file__).parent

PARA = ["lfeit@neix.com.ar", "mupon@neix.com.ar", "fgilges@neix.com.ar"]
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
FIRMA_GIF = REPO / "firma.gif"


def ultimo_reporte():
    """Busca en el HTML del dashboard la lista REPORTES_MENSUALES y devuelve el último."""
    patron = re.compile(r"\{mes:'([^']+)',archivo:'([^']+)'")
    for html in REPO.glob("*.html"):
        texto = html.read_text(encoding="utf-8", errors="ignore")
        if "REPORTES_MENSUALES" in texto:
            bloque = texto.split("REPORTES_MENSUALES", 1)[1].split("];", 1)[0]
            reportes = patron.findall(bloque)
            if reportes:
                mes, archivo = reportes[-1]
                return mes, REPO / archivo
    raise RuntimeError("No encontré REPORTES_MENSUALES en ningún .html del repo")


def armar_mail(mes, pdf):
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(PARA)
    if CC:
        msg["Cc"] = ", ".join(CC)
    msg["Subject"] = f"Reporte Mensual Costos - {mes}"
    texto = (f"Hola Peli y Lucas,\n\nAdjunto el reporte mensual de costos "
             f"correspondiente a {mes}.\n\nSaludos,\n\n{FIRMA_TXT}")
    html = f"""<div style="font-family:'Segoe UI',Calibri,Arial,sans-serif;font-size:11pt;color:#222">
<p>Hola Peli y Lucas,</p>
<p>Adjunto el reporte mensual de costos correspondiente a {mes}.</p>
<p>Saludos,</p>
</div>
{FIRMA_HTML}"""
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    if FIRMA_GIF.exists():
        msg.get_payload()[1].add_related(FIRMA_GIF.read_bytes(), maintype="image",
                                         subtype="gif", cid="<firma>")
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf",
                       filename=f"Reporte Mensual NEIX · {mes}.pdf")
    return msg


def main():
    mes, pdf = ultimo_reporte()
    print("Reporte encontrado:", mes, "→", pdf.relative_to(REPO))
    msg = armar_mail(mes, pdf)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
    print("Enviado a", ", ".join(PARA))


if __name__ == "__main__":
    main()
