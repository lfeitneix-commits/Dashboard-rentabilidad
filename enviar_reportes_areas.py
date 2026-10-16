"""
Manda a cada líder el último Reporte Mensual de SU área.
Lee REPORTES_MENSUALES_AREA del HTML del dashboard y toma los PDFs de reportes/area/.
Es independiente de enviar_reporte.py (el reporte general).
"""
import os
import re
import smtplib
from pathlib import Path
from email.message import EmailMessage

REPO = Path(__file__).parent

# ---------- LÍDERES POR ÁREA (completá nombre y mail) ----------
LIDERES = {
    "Mesa":              {"nombre": "Nacho",   "mail": "lfeit@neix.com.ar"},
    "FAs":               {"nombre": "Sole",    "mail": "lfeit@neix.com.ar"},
    "Banca Corporativa": {"nombre": "NOMBRE",  "mail": "lfeit@neix.com.ar"},
    "Banca Privada":     {"nombre": "Nicanor", "mail": "lfeit@neix.com.ar"},
}
# ---------------------------------------------------------------
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


def ultimos_por_area():
    """Devuelve {area: (mes, pdf)} con el último reporte de cada área."""
    patron_area = re.compile(r"'([^']+)':\[(.*?)\]", re.S)
    patron_rep = re.compile(r"\{mes:'([^']+)',archivo:'([^']+)'")
    for html in REPO.glob("*.html"):
        texto = html.read_text(encoding="utf-8", errors="ignore")
        if "REPORTES_MENSUALES_AREA" in texto:
            bloque = texto.split("REPORTES_MENSUALES_AREA", 1)[1].split("};", 1)[0]
            res = {}
            for area, contenido in patron_area.findall(bloque):
                reps = patron_rep.findall(contenido)
                if reps:
                    mes, archivo = reps[-1]
                    res[area] = (mes, REPO / archivo)
            if res:
                return res
    raise RuntimeError("No encontré REPORTES_MENSUALES_AREA en ningún .html del repo")


def armar_mail(area, lider, mes, pdf):
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = lider["mail"]
    if CC:
        msg["Cc"] = ", ".join(CC)
    msg["Subject"] = f"Reporte Mensual Costos {area} - {mes}"
    texto = (f"Hola {lider['nombre']},\n\nAdjunto el reporte mensual de costos de {area} "
             f"correspondiente a {mes}.\n\nSaludos,\n\n{FIRMA_TXT}")
    html = f"""<div style="font-family:'Segoe UI',Calibri,Arial,sans-serif;font-size:11pt;color:#222">
<p>Hola {lider['nombre']},</p>
<p>Adjunto el reporte mensual de costos de {area} correspondiente a {mes}.</p>
<p>Saludos,</p>
</div>
{FIRMA_HTML}"""
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    if FIRMA_GIF.exists():
        msg.get_payload()[1].add_related(FIRMA_GIF.read_bytes(), maintype="image",
                                         subtype="gif", cid="<firma>")
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf",
                       filename=f"Reporte Mensual NEIX {area} · {mes}.pdf")
    return msg


def main():
    reportes = ultimos_por_area()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        for area, (mes, pdf) in reportes.items():
            lider = LIDERES.get(area)
            if not lider:
                print(f"Sin líder cargado para {area}, no se manda")
                continue
            if not pdf.exists():
                print(f"No existe {pdf.relative_to(REPO)}, no se manda {area}")
                continue
            smtp.send_message(armar_mail(area, lider, mes, pdf))
            print(f"Enviado {area} · {mes} → {lider['mail']}")


if __name__ == "__main__":
    main()
