"""Arma el PDF de "Reporte Mensual con IA" a partir de real_data.json
(generado por extract_data.js) para el mes más reciente cargado en el Sheet.

Uso:
    python3 build_report.py --data real_data.json --out reporte.pdf \
        [--anio 2026]

Decisiones de diseño que valen la pena recordar (se pisaron una vez en el
primer reporte real, el de Agosto 2026, cuando la Facturación de Mesa dio
negativa ese mes):
  - Las 3 KPI cards (Facturación Bruta, Gastos Totales, Resultado) muestran
    la variación como % usando el valor ABSOLUTO del mes anterior como
    base (pct_or_delta) -- así el signo del % siempre coincide con si
    mejoró o empeoró, sin importar si la base era negativa o el valor
    cruzó el cero. Solo se muestra el delta en $ (var_cell_delta) cuando
    la base es exactamente 0 (división por cero de verdad).
  - Un ratio Gastos/Facturación por área es N/D si la facturación de esa
    área es <= 0 ese mes (dividir por negativo invierte el sentido).
  - Los dos ratios generales (Margen neto, Gastos/Facturación) son N/D si
    la Facturación Bruta TOTAL del mes es <= 0 (mismo motivo, a nivel
    compañía).
  - "Facturación por área" se muestra siempre como tabla con el monto real
    (con signo) -- nunca como barra de %, porque una sola área negativa
    rompe el concepto de "% del total".

Esto cubre los casos ya vistos, pero esto son datos reales y pueden traer
sorpresas nuevas cada mes: antes de dar un reporte por bueno, mirá los
números -- si algo se ve raro (un N/D inesperado, un % absurdo, una tabla
vacía), es más probable que sea un dato real atípico que un bug de acá, y
merece una línea propia en "Análisis del mes" en vez de pasar de largo.
"""
import argparse
import json
import os
import re
from contextlib import contextmanager

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether, Flowable, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import svg2rlg

HERE = os.path.dirname(os.path.abspath(__file__))


def asset(*parts):
    return os.path.join(HERE, *parts)


pdfmetrics.registerFont(TTFont('DMSans', asset('fonts', 'DMSans-Regular.ttf')))
pdfmetrics.registerFont(TTFont('DMSans-Medium', asset('fonts', 'DMSans-Medium.ttf')))
pdfmetrics.registerFont(TTFont('DMSans-Bold', asset('fonts', 'DMSans-Bold.ttf')))
pdfmetrics.registerFont(TTFont('DMMono', asset('fonts', 'DMMono-Regular.ttf')))
pdfmetrics.registerFont(TTFont('DMMono-Medium', asset('fonts', 'DMMono-Medium.ttf')))
pdfmetrics.registerFontFamily('DMSans', normal='DMSans', bold='DMSans-Bold')

GRAFITO_HEX, BORDEAUX_HEX, VERDE_HEX, MUTED_HEX, AZUL_HEX = '#3D3D3D', '#AB1930', '#004836', '#9A8E7D', '#003F61'
GRAFITO = colors.HexColor(GRAFITO_HEX)
BORDEAUX = colors.HexColor(BORDEAUX_HEX)
VERDE = colors.HexColor(VERDE_HEX)
MUTED = colors.HexColor(MUTED_HEX)
AZUL = colors.HexColor(AZUL_HEX)
CREMA = colors.HexColor('#F7F5F3')
BORDER = colors.HexColor('#E8E6E3')
VERDE_TINT = colors.HexColor('#E6EEEA')
BORDEAUX_TINT = colors.HexColor('#F6E3E6')
MUTED_TINT = colors.HexColor('#F0EDE8')
AREA_COLOR = {
    'Mesa': AZUL,
    'FAs': MUTED,
    'Banca Corporativa': BORDEAUX,
    'Banca Privada': VERDE,
}
AREAS = ['Mesa', 'FAs', 'Banca Corporativa', 'Banca Privada']

# "Cuentas / Proveedores con mayor variación" -- 10, no 5: desde que
# extract_data.js suma las bajas a cero (un proveedor con gasto real el
# mes anterior que pasó a 0), todas esas bajas empatan en -100% y, en un
# mes con varias cancelaciones, un top 5 quedaría copado solo por ellas.
PROVEEDORES_TOP_N = 10

PAGE_W, PAGE_H = letter
HEADER_H = 30 * mm
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

logo = svg2rlg(asset('neix_logo.svg'))
logo_target_h = 10.5 * mm
_scale = logo_target_h / logo.height
logo.width *= _scale
logo.height *= _scale
logo.scale(_scale, _scale)


def usd(n):
    sign = '-' if n < 0 else ''
    return f"{sign}USD {abs(n):,.0f}".replace(',', '.')


def num(n):
    sign = '-' if n < 0 else ''
    return f"{sign}{abs(n):,.0f}".replace(',', '.')


def usd2(n):
    # Igual que fmtD() del dashboard: 2 decimales, separador de miles "."
    # y de decimales ",", para montos "por unidad" (facturación/comitente,
    # costo/empleado, etc.) donde redondear a entero pierde demasiado.
    sign = '-' if n < 0 else ''
    s = f"{abs(n):,.2f}"
    integer, dec = s.split('.')
    return f"{sign}{integer.replace(',', '.')},{dec}"


def slugify(texto):
    # Solo ascii/dígitos/guion bajo, para no depender de cómo reportlab
    # codifique tildes/espacios en un nombre de destino interno (clave de
    # ancla PDF).
    return re.sub(r'[^a-z0-9]+', '_', texto.strip().lower()).strip('_')


def cuenta_slug(nombre):
    # Clave de ancla PDF para una cuenta del Anexo.
    return 'anexo_' + slugify(nombre)


class Anchor(Flowable):
    # Flowable invisible (0x0) que solo marca, al dibujarse, el destino de
    # un link interno (ver cuenta_slug) -- bookmarkPage apunta al tope de
    # la página donde termina cayendo esta cuenta, no a la fila exacta,
    # pero alcanza para "llevarte al Anexo" al tocar el rubro.
    def __init__(self, key):
        Flowable.__init__(self)
        self.key = key
        self.width = 0
        self.height = 0

    def draw(self):
        self.canv.bookmarkPage(self.key)


def build(data, mes_label, out_path, bullets_extra=None):
    # Rubros donde la detección automática de "salto atípico" no es
    # confiable y se apaga a propósito (decisión del usuario) -- "Gastos de
    # Representación" es gasto puntual por evento, no algo con un
    # promedio histórico que tenga sentido comparar mes a mes.
    RUBROS_SIN_ANALISIS_ATIPICO = {'Gastos de Representación'}
    story = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('H2White', fontName='DMSans-Bold', fontSize=11.5, textColor=colors.white))
    styles.add(ParagraphStyle('KpiLabel', fontName='DMSans-Bold', fontSize=8, textColor=GRAFITO, alignment=TA_CENTER))
    styles.add(ParagraphStyle('KpiValue', fontName='DMMono-Medium', fontSize=16, leading=21, textColor=GRAFITO, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('KpiVar', fontName='DMMono-Medium', fontSize=10, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('VarCell', fontName='DMMono-Medium', fontSize=9.5, alignment=TA_CENTER))
    styles.add(ParagraphStyle('BulletCustom', fontName='DMSans', fontSize=9.5, leading=14, textColor=GRAFITO, leftIndent=4))
    styles.add(ParagraphStyle('NotaChica', fontName='DMSans', fontSize=8, textColor=MUTED, leftIndent=0))
    styles.add(ParagraphStyle('AnexoCuenta', fontName='DMSans-Bold', fontSize=11.5, textColor=GRAFITO))

    def draw_header(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(GRAFITO)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(BORDEAUX)
        p = canvas.beginPath()
        p.moveTo(PAGE_W * 0.56, PAGE_H - HEADER_H)
        p.lineTo(PAGE_W * 0.66, PAGE_H - HEADER_H)
        p.lineTo(PAGE_W * 0.60, PAGE_H)
        p.lineTo(PAGE_W * 0.50, PAGE_H)
        p.close()
        canvas.drawPath(p, stroke=0, fill=1)
        canvas.setFillColor(GRAFITO)
        p2 = canvas.beginPath()
        p2.moveTo(PAGE_W * 0.66, PAGE_H - HEADER_H)
        p2.lineTo(PAGE_W * 0.72, PAGE_H - HEADER_H)
        p2.lineTo(PAGE_W * 0.66, PAGE_H)
        p2.lineTo(PAGE_W * 0.60, PAGE_H)
        p2.close()
        canvas.drawPath(p2, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor('#2A2A2A'))
        canvas.rect(0, PAGE_H - HEADER_H - 2.2 * mm, PAGE_W, 2.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(BORDEAUX)
        canvas.rect(0, PAGE_H - HEADER_H - 2.2 * mm, PAGE_W * 0.35, 2.2 * mm, stroke=0, fill=1)
        renderPDF.draw(logo, canvas, MARGIN, PAGE_H - HEADER_H + (HEADER_H - logo_target_h) / 2 + 1 * mm)
        canvas.setFillColor(colors.white)
        canvas.setFont('DMSans-Bold', 15)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - HEADER_H / 2 - 1, "Reporte mensual")
        canvas.setFont('DMSans', 9)
        canvas.setFillColor(colors.HexColor('#C9C2B8'))
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - HEADER_H / 2 + 11, f"{mes_label.upper()}  ·  NEIX")
        canvas.setFillColor(MUTED)
        canvas.setFont('DMSans', 7.5)
        canvas.drawString(MARGIN, 10 * mm, "Generado automáticamente a partir del Dashboard de Rentabilidad")
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Página {canvas.getPageNumber()}")
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
        canvas.restoreState()

    def var_cell(pct):
        if pct == 0:
            icon, color_hex, tint = asset('tri_flat_muted.png'), MUTED_HEX, MUTED_TINT
            txt = '0,0%'
        elif pct > 0:
            icon, color_hex, tint = asset('tri_up_verde.png'), VERDE_HEX, VERDE_TINT
            txt = f'+{pct:.1f}%'
        else:
            icon, color_hex, tint = asset('tri_down_bordeaux.png'), BORDEAUX_HEX, BORDEAUX_TINT
            txt = f'{pct:.1f}%'
        html = f'<img src="{icon}" width="7.5" height="7.5" valign="-1.3"/>&nbsp;<font color="{color_hex}">{txt}</font>'
        return Paragraph(html, styles['VarCell']), tint

    def var_cell_delta(delta):
        # Delta en USD (nunca %) -- solo para cuando el % es indefinido de
        # verdad (base = 0, división por cero; ver pct_or_delta). "USD"
        # explícito para que no se confunda con un % o un monto en otra
        # unidad.
        if delta == 0:
            icon, color_hex, tint = asset('tri_flat_muted.png'), MUTED_HEX, MUTED_TINT
            txt = 'USD 0'
        elif delta > 0:
            icon, color_hex, tint = asset('tri_up_verde.png'), VERDE_HEX, VERDE_TINT
            txt = f'+USD {num(delta)}'
        else:
            icon, color_hex, tint = asset('tri_down_bordeaux.png'), BORDEAUX_HEX, BORDEAUX_TINT
            txt = f'USD {num(delta)}'
        html = f'<img src="{icon}" width="7.5" height="7.5" valign="-1.3"/>&nbsp;<font color="{color_hex}">{txt}</font>'
        return Paragraph(html, styles['VarCell']), tint

    def pct_or_delta(actual, anterior):
        # % de variación sobre el valor ABSOLUTO de la base, no la base con
        # signo -- así el signo del % siempre coincide con el del delta
        # (mejoró = +, empeoró = -), sin importar si la base era negativa o
        # si el valor cruzó el cero. Con la fórmula estándar (delta/base),
        # una base negativa invierte el signo: de -213.675 a -1.608.860
        # (un resultado bastante peor) daba "+653,8%", que se lee como una
        # mejora. Con la base en valor absoluto da "-653,8%": coincide con
        # que el resultado empeoró. Solo si la base es 0 el % es
        # indefinido de verdad (división por cero) y se muestra el delta
        # en USD.
        if anterior == 0:
            return var_cell_delta(actual - anterior)
        return var_cell((actual - anterior) / abs(anterior) * 100)

    def ratio_cell(pct, good_below=50.0):
        good = pct <= good_below
        color_hex = VERDE_HEX if good else BORDEAUX_HEX
        tint = VERDE_TINT if good else BORDEAUX_TINT
        return Paragraph(f'<font color="{color_hex}">{pct:.1f}%</font>', styles['VarCell']), tint

    def margen_cell(pct):
        # Para un margen (a diferencia de un ratio de costo), "bueno" es
        # positivo -- no "por debajo de un umbral" como en ratio_cell, que
        # mostraría verde a una pérdida grande con tal de que no pase cierto
        # número.
        good = pct >= 0
        color_hex = VERDE_HEX if good else BORDEAUX_HEX
        tint = VERDE_TINT if good else BORDEAUX_TINT
        sign = '+' if pct >= 0 else ''
        return Paragraph(f'<font color="{color_hex}">{sign}{pct:.1f}%</font>', styles['VarCell']), tint

    def na_cell():
        return Paragraph(f'<font color="{MUTED_HEX}">N/D</font>', styles['VarCell']), MUTED_TINT

    def historico_cell(r):
        # Marca, en la tabla de "Top rubros", cuáles de ellos son además un
        # salto atípico vs. su propio promedio histórico (ver
        # historialRubro() en extract_data.js) -- no solo el #1, que es el
        # único que ya se explicaba en "Análisis del mes".
        # Nada de ⚠/▲/▼ acá: VarCell usa DMMono-Medium, que no tiene esos
        # glyphs (salían como tofu boxes). Mismo signo +/- que usa el resto
        # del reporte para arriba/abajo (ver var_cell), no símbolos nuevos.
        if r['nombre'] in RUBROS_SIN_ANALISIS_ATIPICO or r.get('ratioVsHistorico') is None:
            return Paragraph(f'<font color="{MUTED_HEX}">N/D</font>', styles['VarCell'])
        if not r.get('esAtipico'):
            return Paragraph(f'<font color="{MUTED_HEX}">en línea</font>', styles['VarCell'])
        desvio_pct = (r['ratioVsHistorico'] - 1) * 100
        signo = '+' if desvio_pct >= 0 else ''
        return Paragraph(f'<font color="{BORDEAUX_HEX}">atípico {signo}{desvio_pct:.0f}%</font>', styles['VarCell'])

    @contextmanager
    def keep_together():
        # Agrupa todo lo que se agregue a `story` dentro del `with` en un
        # solo flowable -- evita que un salto de página corte una tabla (o
        # el título de una sección) por la mitad. Si el bloque es más alto
        # que una página entera reportlab lo deja pasar igual (no hay forma
        # de evitar eso sin partirlo), pero ninguna tabla de este reporte
        # llega a esa altura.
        start = len(story)
        yield
        block = story[start:]
        del story[start:]
        if block:
            story.append(KeepTogether(block))

    def section_title(title):
        story.append(Spacer(1, 16))
        t = Table([[Paragraph(title, styles['H2White'])]], colWidths=[CONTENT_W], rowHeights=[8 * mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GRAFITO),
            ('LINEBEFORE', (0, 0), (0, 0), 3.5, BORDEAUX),
            ('LEFTPADDING', (0, 0), (0, 0), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    def data_table(header_row, rows, col_widths, var_colidx):
        table_data = [header_row] + [[c[0] if isinstance(c, tuple) else c for c in row] for row in rows]
        t = Table(table_data, colWidths=col_widths)
        style_cmds = [
            ('FONTNAME', (0, 0), (-1, -1), 'DMSans'),
            ('FONTNAME', (1, 1), (2, -1), 'DMMono'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EDEAE4')),
            ('FONTNAME', (0, 0), (-1, 0), 'DMSans-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), GRAFITO),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CREMA]),
            ('TOPPADDING', (0, 0), (-1, -1), 5.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
            ('LINEBELOW', (0, -1), (-1, -1), 0.6, BORDER),
            ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
            ('FONTNAME', (var_colidx, 1), (var_colidx, -1), 'DMMono-Medium'),
            ('ALIGN', (var_colidx, 0), (var_colidx, 0), 'CENTER'),
        ]
        for i, row in enumerate(rows, start=1):
            cell = row[var_colidx]
            if isinstance(cell, tuple):
                style_cmds.append(('BACKGROUND', (var_colidx, i), (var_colidx, i), cell[1]))
                style_cmds.append(('ALIGN', (var_colidx, i), (var_colidx, i), 'CENTER'))
        t.setStyle(TableStyle(style_cmds))
        story.append(t)
        story.append(Spacer(1, 4))

    def plain_table(header_row, rows, col_widths, signed_colidx=None, signed_vals=None):
        table_data = [header_row] + rows
        t = Table(table_data, colWidths=col_widths)
        style_cmds = [
            ('FONTNAME', (0, 0), (-1, -1), 'DMSans'),
            ('FONTNAME', (1, 1), (-1, -1), 'DMMono-Medium'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EDEAE4')),
            ('FONTNAME', (0, 0), (-1, 0), 'DMSans-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CREMA]),
            ('TOPPADDING', (0, 0), (-1, -1), 5.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
            ('LINEBELOW', (0, -1), (-1, -1), 0.6, BORDER),
            ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
        ]
        if signed_colidx is not None:
            for i, v in enumerate(signed_vals, start=1):
                style_cmds.append(('TEXTCOLOR', (signed_colidx, i), (signed_colidx, i), BORDEAUX if v < 0 else VERDE))
        t.setStyle(TableStyle(style_cmds))
        story.append(t)
        story.append(Spacer(1, 4))

    def kpi_card(label, value_str, para_tint, sub_label=None):
        # sub_label (ej. "vs. Julio") aclara contra qué mes es la
        # variación de abajo -- sin esto no es obvio a simple vista que
        # siempre es "vs. el mes inmediato anterior", nunca un promedio ni
        # el mismo mes del año pasado.
        para, _tint = para_tint
        para.style = styles['KpiVar']
        content = [
            [Paragraph(label.upper(), styles['KpiLabel'])],
            [Paragraph(value_str, styles['KpiValue'])],
            [para],
        ]
        if sub_label:
            content.append([Paragraph(
                sub_label,
                ParagraphStyle('KpiSub', fontName='DMSans', fontSize=7, textColor=MUTED, alignment=TA_CENTER),
            )])
        cell = Table(content, colWidths=[58 * mm])
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, BORDEAUX),
            ('TOPPADDING', (0, 0), (0, 0), 12),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 12),
            ('TOPPADDING', (0, 1), (0, 1), 1),
            ('TOPPADDING', (0, 2), (0, 2), 1),
        ]
        if sub_label:
            style_cmds.append(('TOPPADDING', (0, 3), (0, 3), 1))
        cell.setStyle(TableStyle(style_cmds))
        return cell

    def na_card(label, note):
        cell = Table(
            [[Paragraph(label.upper(), styles['KpiLabel'])],
             [Paragraph('N/D', ParagraphStyle('nd', parent=styles['VarCell'], fontSize=15, textColor=MUTED))],
             [Paragraph(note, ParagraphStyle('ndnote', fontName='DMSans', fontSize=7, textColor=MUTED, alignment=TA_CENTER))]],
            colWidths=[87 * mm],
        )
        cell.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, GRAFITO),
            ('TOPPADDING', (0, 0), (0, 0), 11),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (0, 1), 3),
            ('TOPPADDING', (0, 2), (0, 2), 2),
        ]))
        return cell

    def ratio_card(label, pct, good_below):
        para, _tint = ratio_cell(pct, good_below)
        para.style = ParagraphStyle('rc', parent=styles['VarCell'], fontSize=15)
        cell = Table([[Paragraph(label.upper(), styles['KpiLabel'])], [para]], colWidths=[87 * mm])
        cell.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, GRAFITO),
            ('TOPPADDING', (0, 0), (0, 0), 11),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 11),
            ('TOPPADDING', (0, 1), (0, 1), 3),
        ]))
        return cell

    def margen_card(label, pct):
        # No reutiliza ratio_card: ratio_cell es "bueno si está por debajo
        # de un umbral" (sirve para costo), pero un margen es al revés --
        # "bueno" es positivo, sin importar qué tan alto.
        para, _tint = margen_cell(pct)
        para.style = ParagraphStyle('mc', parent=styles['VarCell'], fontSize=15)
        cell = Table([[Paragraph(label.upper(), styles['KpiLabel'])], [para]], colWidths=[87 * mm])
        cell.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, GRAFITO),
            ('TOPPADDING', (0, 0), (0, 0), 11),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 11),
            ('TOPPADDING', (0, 1), (0, 1), 3),
        ]))
        return cell

    def accum_card(label, value):
        color = VERDE if value >= 0 else BORDEAUX
        cell = Table(
            [[Paragraph(label.upper(), styles['KpiLabel'])],
             [Paragraph(usd(value), ParagraphStyle('AccumValue', fontName='DMMono-Medium', fontSize=16, textColor=color, alignment=TA_CENTER))]],
            colWidths=[CONTENT_W],
        )
        cell.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, color),
            ('TOPPADDING', (0, 0), (0, 0), 10),
            ('BOTTOMPADDING', (0, 1), (0, 1), 10),
            ('TOPPADDING', (0, 1), (0, 1), 3),
        ]))
        return cell

    def area_bar_chart(area_data):
        bar_w = CONTENT_W
        bar_h = 9 * mm
        row_gap = 4 * mm
        dwg_h = len(area_data) * (bar_h + row_gap)
        d = Drawing(bar_w, dwg_h)
        label_w = 42 * mm
        track_w = bar_w - label_w - 22 * mm
        for i, (area, _monto, pct) in enumerate(area_data):
            y = dwg_h - (i + 1) * (bar_h + row_gap) + row_gap / 2
            d.add(String(0, y + bar_h / 2 - 3, area, fontName='DMSans-Bold', fontSize=9.5, fillColor=GRAFITO))
            d.add(Rect(label_w, y, track_w, bar_h, fillColor=colors.HexColor('#EDEAE4'), strokeColor=None))
            fill_w = track_w * (pct / 100.0)
            d.add(Rect(label_w, y, fill_w, bar_h, fillColor=AREA_COLOR[area], strokeColor=None))
            d.add(String(label_w + track_w + 4, y + bar_h / 2 - 3, f"{pct:.1f}%", fontName='DMMono-Medium', fontSize=9.5, fillColor=GRAFITO))
        story.append(d)
        story.append(Spacer(1, 4))

    def trend_chart(meses, series, fmt_axis=None):
        # fmt_axis: formateador del eje Y -- por default compacta a "k"
        # (pensado para montos grandes, Facturación/Gastos/Resultado). Para
        # series de montos chicos (ej. Unit Economics, $ por comitente) esa
        # compactación hace que varias líneas de grilla redondeen al mismo
        # "1k" -- pasar un formateador en USD sin compactar en ese caso.
        if fmt_axis is None:
            fmt_axis = lambda v: f"{v/1000:,.0f}k".replace(',', '.')
        chart_w = CONTENT_W
        chart_h = 52 * mm
        pad_l, pad_r, pad_t, pad_b = 16 * mm, 4 * mm, 4 * mm, 8 * mm
        plot_w = chart_w - pad_l - pad_r
        plot_h = chart_h - pad_t - pad_b
        all_vals = [v for _, _, vals in series for v in vals]
        raw_min, raw_max = min(all_vals), max(all_vals)
        pad = (raw_max - raw_min) * 0.1 or abs(raw_max) * 0.1 or 1
        vmin, vmax = raw_min - pad, raw_max + pad
        d = Drawing(chart_w, chart_h)
        for frac in (0, 0.25, 0.5, 0.75, 1.0):
            y = pad_b + plot_h * frac
            val = vmin + (vmax - vmin) * frac
            d.add(Line(pad_l, y, pad_l + plot_w, y, strokeColor=BORDER, strokeWidth=0.5))
            d.add(String(pad_l - 3, y - 2.5, fmt_axis(val), fontName='DMMono', fontSize=6.5, fillColor=MUTED, textAnchor='end'))
        if vmin < 0 < vmax:
            y0 = pad_b + (0 - vmin) / (vmax - vmin) * plot_h
            d.add(Line(pad_l, y0, pad_l + plot_w, y0, strokeColor=MUTED, strokeWidth=0.75, strokeDashArray=[2, 2]))
        n = len(meses)
        step_x = plot_w / (n - 1) if n > 1 else 0
        for _label, color, vals in series:
            pts = []
            for i, v in enumerate(vals):
                x = pad_l + i * step_x
                y = pad_b + (v - vmin) / (vmax - vmin) * plot_h
                pts.append((x, y))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                d.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=2))
            for x, y in pts:
                d.add(Circle(x, y, 2.4, fillColor=color, strokeColor=colors.white, strokeWidth=0.8))
        for i, mesname in enumerate(meses):
            x = pad_l + i * step_x
            d.add(String(x, 0, mesname, fontName='DMSans', fontSize=7.5, fillColor=MUTED, textAnchor='middle'))
        story.append(d)
        legend_cells = []
        for label, color, _ in series:
            sw = Table([['']], colWidths=[3 * mm], rowHeights=[3 * mm])
            sw.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), color)]))
            legend_cells.append(sw)
            legend_cells.append(Paragraph(label, ParagraphStyle('leg', fontName='DMSans', fontSize=8.5, textColor=GRAFITO)))
        leg = Table([legend_cells], colWidths=[4 * mm, 28 * mm] * len(series))
        leg.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(leg)
        story.append(Spacer(1, 4))

    # ============================================================
    # Contenido
    # ============================================================
    kpi_act, kpi_ant = data['kpiActual'], data['kpiAnterior']
    fact_act, gastos_act, result_act = kpi_act['ingresos'], kpi_act['egresos'], kpi_act['resultado']
    # TODOS los rubros que efectivamente subieron (deltaPct > 0), sin tope --
    # usado acá y en "Análisis del mes" para que ambos miren la misma lista;
    # si se completara con bajas solo para llegar a un número fijo
    # contradiría el título de la sección de abajo.
    rubros_suben = [r for r in data['rubrosVariacion'] if r['deltaPct'] > 0]

    if kpi_ant:
        fact_ant, gastos_ant, result_ant = kpi_ant['ingresos'], kpi_ant['egresos'], kpi_ant['resultado']
        fact_var = pct_or_delta(fact_act, fact_ant)
        gastos_var = pct_or_delta(gastos_act, gastos_ant)
        result_var = pct_or_delta(result_act, result_ant)
    else:
        fact_var = gastos_var = result_var = var_cell(0.0)

    # ── Señales críticas (ex "Alertas del mes"): ya no tienen su propia
    # caja -- se calculan acá y se insertan con máxima prioridad dentro de
    # "Análisis del mes" (ver más abajo), para que el pantallazo de 5
    # bullets nunca se quede sin lo más urgente aunque haya mucho rubro
    # material compitiendo por un lugar. ──
    ing_area_alert = data['ingresosPorAreaActual']
    areas_sin_facturacion = [a for a in AREAS if ing_area_alert[a] <= 0]
    # Área que PASA a margen negativo este mes -- no "tiene margen
    # negativo" a secas, porque un área chica (Banca Corporativa, Banca
    # Privada) corre así casi todos los meses por el prorrateo de
    # indirectos, y repetir eso cada reporte sería ruido, no una alerta.
    # Solo dispara cuando el mes anterior era positivo y este no.
    resultado_area_alert = data.get('resultadoPorAreaActual') or {}
    ing_area_ant_alert = data.get('ingresosPorAreaAnterior') or {}
    resultado_area_ant_alert = data.get('resultadoPorAreaAnterior') or {}
    areas_margen_nuevo_negativo = []
    for a in AREAS:
        fact, fact_ant = ing_area_alert[a], ing_area_ant_alert.get(a, 0)
        if fact <= 0 or not fact_ant or fact_ant <= 0:
            continue
        margen_actual = resultado_area_alert.get(a, 0) / fact
        margen_anterior = resultado_area_ant_alert.get(a, 0) / fact_ant
        if margen_actual < 0 and margen_anterior >= 0:
            areas_margen_nuevo_negativo.append(a)
    kpi_sub = f"vs. {data['mesAnterior']}" if kpi_ant else None
    kpis = Table(
        [[kpi_card("Facturación bruta", usd(fact_act), fact_var, kpi_sub),
          kpi_card("Gastos totales", usd(gastos_act), gastos_var, kpi_sub),
          kpi_card("Resultado", usd(result_act), result_var, kpi_sub)]],
        colWidths=[CONTENT_W / 3] * 3,
    )
    kpis.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(kpis)

    # ── Resultado acumulado del año en curso -- suma de los mismos
    # "resultado" por mes que ya arma kpiTrend para el gráfico de
    # Evolución (no una cuenta nueva). Se omite en el primer mes del año:
    # ahí "acumulado" sería el mismo número que el KPI "Resultado" de
    # arriba, no aporta nada. ──
    if len(data['kpiTrend']) > 1:
        resultado_acum = sum(m['resultado'] for m in data['kpiTrend'])
        primer_mes = data['kpiTrend'][0]['mes']
        with keep_together():
            story.append(Spacer(1, 6))
            story.append(accum_card(f"Resultado acumulado {primer_mes} - {data['mesActual']}", resultado_acum))

    # ── Análisis del mes: reemplaza a "Alertas del mes" + el análisis
    # anterior -- EXACTAMENTE hasta 5 bullets (no una lista abierta), armados
    # en orden de prioridad para que, leyendo solo estos 5, alcance como
    # pantallazo completo del mes sin tener que bajar al resto del reporte.
    # Orden: (1) señales críticas (ex "Alertas del mes": resultado negativo,
    # áreas sin facturación, áreas a margen negativo) -- siempre primero, se
    # queden o no afuera del corte de 5; (2) bullets manuales (--bullet);
    # (3) panorama base (facturación, acumulado, rubro que más sube); (4)
    # relleno por materialidad (notas manuales, otros rubros atípicos) solo
    # si sobra lugar. Nunca se "completa" a la fuerza: si hay menos de 5
    # candidatos genuinos, se muestran menos. ──
    # Frase de detección automática de valor atípico, reutilizada tanto para
    # el rubro #1 como para cualquier otro rubro que llame la atención más
    # abajo: compara el monto de este mes contra el promedio histórico del
    # mismo rubro en los meses previos (ver historialRubro() en
    # extract_data.js), con al menos MESES_MIN_HISTORIAL de datos para que
    # el promedio no sea un invento de 1-2 puntos.
    def nota_historico(r):
        # Fragmento corto, no una oración aparte -- se pega al final del
        # bullet principal en vez de sumar una segunda frase.
        if r['nombre'] in RUBROS_SIN_ANALISIS_ATIPICO or r.get('ratioVsHistorico') is None:
            return ''
        n_hist = r['historicoMesesCount']
        promedio_txt = num(r['promedioHistorico'])
        desvio_pct = abs(r['ratioVsHistorico'] - 1) * 100
        if r.get('esAtipico'):
            direccion = 'sobre' if r['ratioVsHistorico'] > 1 else 'bajo'
            return f" Atípico: {desvio_pct:.0f}% {direccion} su promedio de {n_hist} meses ({promedio_txt})."
        return f" En línea con su promedio de {n_hist} meses ({promedio_txt})."

    def variacion_cell_txt(item):
        signo = '+' if item['deltaPct'] >= 0 else ''
        return f"{signo}{item['deltaPct']:.1f}% ({num(item['anterior'])} → {num(item['actual'])})"

    def variacion_kpi_txt(actual, anterior):
        # Mismo criterio de signo que pct_or_delta (% sobre la base en
        # valor absoluto), pero en texto plano para un bullet en vez de una
        # celda de tabla.
        if anterior is None:
            return ''
        if anterior == 0:
            delta = actual - anterior
            signo = '+' if delta >= 0 else ''
            return f" ({signo}USD {num(delta)} vs. {data['mesAnterior']})"
        pct = (actual - anterior) / abs(anterior) * 100
        signo = '+' if pct >= 0 else ''
        return f" ({signo}{pct:.1f}% vs. {data['mesAnterior']})"

    MAX_BULLETS = 5
    candidatos = []
    ya_mencionado = set()

    # (1) Señales críticas -- máxima prioridad.
    if result_act < 0:
        candidatos.append(f"Resultado del mes fue negativo: {usd(result_act)}{variacion_kpi_txt(result_act, result_ant if kpi_ant else None)}.")
    else:
        candidatos.append(f"Resultado del mes: {usd(result_act)}{variacion_kpi_txt(result_act, result_ant if kpi_ant else None)}.")
    if areas_sin_facturacion:
        candidatos.append(
            f"{', '.join(areas_sin_facturacion)}: facturación bruta negativa o cero este mes "
            f"(ratios de esa área salen N/D más abajo)."
        )
    if areas_margen_nuevo_negativo:
        candidatos.append(
            f"{', '.join(areas_margen_nuevo_negativo)}: pasó a margen negativo este mes "
            f"(el mes anterior había sido positivo)."
        )

    # (2) Bullets manuales (--bullet) -- después de las señales críticas,
    # antes del panorama base: un humano decidió que esto importa.
    if bullets_extra:
        candidatos.extend(bullets_extra)

    # (3) Panorama base: facturación, acumulado, rubro que más sube.
    candidatos.append(f"Facturación del mes: {usd(fact_act)}{variacion_kpi_txt(fact_act, fact_ant if kpi_ant else None)}.")
    if len(data['kpiTrend']) > 1:
        resultado_acum = sum(m['resultado'] for m in data['kpiTrend'])
        primer_mes = data['kpiTrend'][0]['mes']
        candidatos.append(f"Resultado acumulado {primer_mes} - {data['mesActual']}: {usd(resultado_acum)}.")
    if data['rubrosVariacion']:
        top = data['rubrosVariacion'][0]
        top_txt = f"{top['nombre']}, el rubro que más subió: {variacion_cell_txt(top)}."
        if top.get('notaManual'):
            top_txt += f" {top['notaManual']}."
        top_txt += nota_historico(top)
        candidatos.append(top_txt)
        ya_mencionado.add(top['nombre'])

    # (4) Relleno por materialidad -- solo entra si sobra lugar en los 5.
    # Notas manuales para cualquier otro rubro/proveedor del top que tenga
    # un "por qué" cargado (ver NOTAS_CUENTAS en extract_data.js).
    for item in rubros_suben + data['proveedores'][:PROVEEDORES_TOP_N]:
        nota = item.get('notaManual')
        if not nota or item['nombre'] in ya_mencionado:
            continue
        ya_mencionado.add(item['nombre'])
        candidatos.append(f"{item['nombre']}: {variacion_cell_txt(item)} -- {nota}.")
    # Cualquier otro rubro (suba o baja, no solo el #1) que sea un salto
    # atípico vs. su propio historial, ordenado por delta en USD (no el %)
    # -- eso sí es "relevante" en plata, no solo en términos relativos.
    ATIPICOS_EXTRA_TOP_N = 3
    atipicos_extra = sorted(
        (r for r in data['rubrosVariacion']
         if r['nombre'] not in ya_mencionado and r['nombre'] not in RUBROS_SIN_ANALISIS_ATIPICO
         and r.get('esAtipico')),
        key=lambda r: abs(r['actual'] - r['anterior']),
        reverse=True,
    )[:ATIPICOS_EXTRA_TOP_N]
    for item in atipicos_extra:
        ya_mencionado.add(item['nombre'])
        candidatos.append(f"{item['nombre']}: {variacion_cell_txt(item)}.{nota_historico(item)}")

    bullets = candidatos[:MAX_BULLETS]
    with keep_together():
        section_title(f"ANÁLISIS DEL MES · {mes_label.upper()}")
        for b in bullets:
            story.append(Paragraph(f"•  {b}", styles['BulletCustom']))
            story.append(Spacer(1, 4))

    # ── Evolución (año en curso) ──
    if len(data['kpiTrend']) > 1:
        with keep_together():
            section_title("EVOLUCIÓN ÚLTIMOS MESES")
            meses_trend = [m['mes'][:3] for m in data['kpiTrend']]
            series = [
                ("Facturación", AZUL, [m['ingresos'] for m in data['kpiTrend']]),
                ("Gastos", BORDEAUX, [m['egresos'] for m in data['kpiTrend']]),
                ("Resultado", VERDE, [m['resultado'] for m in data['kpiTrend']]),
            ]
            trend_chart(meses_trend, series)

    # ── Mismo top, aperturado por área (rubrosVariacionPorArea en
    # extract_data.js) -- "Clasificación de gastos" (la fuente de la tabla
    # de arriba) es un total de toda la empresa, así que esto sale de la
    # otra fuente que sí tiene columna por área. Una mini-tabla por área
    # (top 5 cada una, mismo criterio deltaPct > 0 que la tabla general) --
    # se salta el área si no tuvo ningún rubro que subiera. Se calcula
    # ACÁ (antes de las tablas de "Top rubros") para saber, antes de
    # dibujarlas, qué nombres de rubro van a tener un link al Anexo. ──
    rubros_por_area = data.get('rubrosVariacionPorArea') or {}
    area_blocks = []
    for area in AREAS:
        suben_area = [r for r in rubros_por_area.get(area, []) if r['deltaPct'] > 0][:5]
        if suben_area:
            area_blocks.append((area, suben_area))

    # ── Qué rubros de las tablas de abajo tienen algo para mostrar en el
    # Anexo -- calculado acá para poder linkear el nombre del rubro
    # directo a su entrada, en vez de solo mencionarlo al final del PDF.
    #
    # Ojo, esto NO es "mostrame cuánto es cada cuenta por mes" (eso ya
    # está en la tabla de arriba, mesAnterior/mesActual) -- es de qué
    # proveedores/conceptos/movimientos se compone. Dos fuentes posibles
    # por rubro (`anexo_entries`, cada una con su `tipo`), en este orden:
    #   'providers' -- el rubro coincide por nombre con una cuenta de
    #     Gastos Fijos Detalle: proveedores con su monto en mesAnterior y
    #     mesActual (gastosFijosDetalleCuentas, ya agregado por mes).
    #   'ledger' -- no hay esa cuenta en Gastos Fijos Detalle (ej.
    #     "Honorarios por Servicios" -- confirmado contra la hoja cruda,
    #     no tiene bloque propio ahí, solo "Honorarios Profesionales" lo
    #     tiene), pero el nombre coincide EXACTO con una cuenta del mayor
    #     contable (gastosLedgerDetalle, extract_data.js): movimiento por
    #     movimiento de mesActual, con fecha y concepto reales. Si el
    #     rubro es un agregado de varias cuentas del mayor (ej.
    #     "Impuestos" = Impuesto Ley 25413 + IVA No Computable + ...) NO
    #     hay match exacto a propósito -- sumar esas cuentas a mano acá
    #     sería adivinar, no leer el Sheet.
    # Si un rubro no tiene ninguna de las dos, queda sin link -- no inventa
    # un desglose que no existe, ni lo reemplaza por otra cosa (una serie
    # mensual se probó como "tercera fuente" y no resolvía "qué es esto";
    # se sacó). ──
    cuentas_detalle = data.get('gastosFijosDetalleCuentas') or {}
    ledger_detalle = data.get('gastosLedgerDetalle') or {}
    # Agrupado por proveedor/concepto (ya sumado por mes en
    # extract_data.js) -- lo que se muestra en el Anexo para una cuenta
    # "ledger"; ledger_detalle (movimiento por movimiento, sin agrupar)
    # solo se usa más abajo para decidir SI la cuenta tiene algo que
    # mostrar, no para la tabla en sí (ponerlos todos sueltos separaba un
    # mismo proveedor recurrente -- ej. "Banco de Valores" -- en una fila
    # por día/comprobante distinto).
    ledger_agrupado = data.get('gastosLedgerAgrupado') or {}
    # Dónde aparece cada nombre de rubro -- para armar, en el Anexo, un
    # link de "volver" preciso a CADA lugar donde ese rubro tiene su link
    # de ida (puede ser más de uno: la tabla general Y la de su área).
    # Un link fijo a un solo destino (se probó "volver arriba" a la
    # página 1) no sirve -- no hay una única "página de origen". Esto sí
    # apunta exacto, a la sección real de la que vino cada link.
    fuentes_por_nombre = {}
    for r in rubros_suben:
        fuentes_por_nombre.setdefault(r['nombre'], []).append(('general', None))
    for area, suben_area in area_blocks:
        for r in suben_area:
            fuentes_por_nombre.setdefault(r['nombre'], []).append(('area', area))
    nombres_vistos = set(fuentes_por_nombre.keys())
    cuentas_por_nombre = {k.strip().lower(): k for k in cuentas_detalle.keys()}
    ledger_por_nombre = {k.strip().lower(): k for k in ledger_detalle.keys()}
    anexo_entries = []
    anexo_fuentes = {}
    vistos_lower = set()
    for n in sorted(nombres_vistos):
        nl = n.strip().lower()
        if nl in vistos_lower:
            continue
        canon = None
        if nl in cuentas_por_nombre and cuentas_detalle.get(cuentas_por_nombre[nl]):
            canon = cuentas_por_nombre[nl]
            anexo_entries.append((canon, 'providers'))
        elif nl in ledger_por_nombre and ledger_detalle.get(ledger_por_nombre[nl]):
            canon = ledger_por_nombre[nl]
            anexo_entries.append((canon, 'ledger'))
        if canon:
            vistos_lower.add(nl)
            anexo_fuentes.setdefault(canon, []).extend(fuentes_por_nombre[n])
    anexo_entries.sort(key=lambda e: e[0])
    anexo_nombres = {e[0] for e in anexo_entries}
    nombre_style = ParagraphStyle('rubroNombre', fontName='DMSans', fontSize=9.5, textColor=GRAFITO)

    def nombre_cell(nombre):
        # Si ese rubro tiene una entrada en el Anexo (providers o ledger),
        # el nombre es un link interno -- mismo criterio de match
        # (case-insensitive) que arriba.
        match = cuentas_por_nombre.get(nombre.strip().lower()) or ledger_por_nombre.get(nombre.strip().lower())
        if match and match in anexo_nombres:
            html = f'<a href="#{cuenta_slug(match)}" color="{AZUL_HEX}"><u>{nombre}</u></a>'
            return Paragraph(html, nombre_style)
        return Paragraph(nombre, nombre_style)

    # ── Top rubros que más subieron (rubros_suben calculado arriba) --
    # el Anchor('sec_top_rubros') es el destino del link de "volver" que
    # el Anexo pone para cada rubro que vino de ACÁ (ver anexo_fuentes). ──
    if rubros_suben:
        with keep_together():
            story.append(Anchor('sec_top_rubros'))
            section_title("TOP RUBROS QUE MÁS SUBIERON")
            rows = [[nombre_cell(r['nombre']), num(r['anterior']), num(r['actual']), var_cell(r['deltaPct']), historico_cell(r)] for r in rubros_suben]
            data_table(["Rubro", data['mesAnterior'], data['mesActual'], "Variación", "vs. Histórico"], rows,
                       [48 * mm, 24 * mm, 24 * mm, 28 * mm, CONTENT_W - 48 * mm - 24 * mm - 24 * mm - 28 * mm], var_colidx=3)

    for i, (area, suben_area) in enumerate(area_blocks):
        with keep_together():
            if i == 0:
                section_title("TOP RUBROS QUE MÁS SUBIERON · POR ÁREA")
            # Ancla propia por área (no una sola para toda la sección):
            # cada área puede caer en una página distinta, y el link de
            # "volver" del Anexo tiene que apuntar a la de ESA área.
            story.append(Anchor(f'sec_top_rubros_area_{slugify(area)}'))
            story.append(Paragraph(area, ParagraphStyle(f'areaRubroLabel{area}', fontName='DMSans-Bold', fontSize=9.5, textColor=AREA_COLOR[area])))
            story.append(Spacer(1, 2))
            rows = [[nombre_cell(r['nombre']), num(r['anterior']), num(r['actual']), var_cell(r['deltaPct'])] for r in suben_area]
            data_table(["Rubro", data['mesAnterior'], data['mesActual'], "Variación"], rows,
                       [55 * mm, 28 * mm, 28 * mm, CONTENT_W - 55 * mm - 56 * mm], var_colidx=3)

    # ── Cuentas/proveedores con mayor variación (no los de mayor monto --
    # ver nota en extract_data.js sobre el filtro anterior>0 && actual>0).
    # "Cuenta / Proveedor" porque Gastos Fijos Detalle no siempre tiene un
    # proveedor con nombre propio en esa fila -- a veces es una cuenta
    # genérica (ej. "Gtos Mant de Oficina"), y llamarlo solo "Proveedor"
    # sugiere algo más específico de lo que hay.
    #
    # Top 10, no 5: desde que extract_data.js suma las bajas a cero (un
    # proveedor con gasto real el mes anterior que pasó a 0), todas esas
    # bajas empatan en -100% y, en un mes con varias cancelaciones, un
    # top 5 quedaría copado solo por ellas -- tapando otras variaciones ya
    # explicadas (ej. "Gtos Mant de Oficina", que tiene nota manual en
    # NOTAS_CUENTAS). Con 10 lugares entran las dos cosas. ──
    if data['proveedores']:
        with keep_together():
            section_title("CUENTAS / PROVEEDORES CON MAYOR VARIACIÓN")
            rows = []
            for p in data['proveedores'][:PROVEEDORES_TOP_N]:
                rows.append([p['nombre'], num(p['anterior']), num(p['actual']), var_cell(p['deltaPct'])])
            data_table(["Cuenta / Proveedor", data['mesAnterior'], data['mesActual'], "Variación"], rows,
                       [65 * mm, 26 * mm, 26 * mm, CONTENT_W - 65 * mm - 52 * mm], var_colidx=3)

    # ── Facturación por área: siempre tabla con signo (nunca %, por si
    # alguna área da negativa -- ver docstring). ──
    ing_area = data['ingresosPorAreaActual']
    with keep_together():
        section_title("FACTURACIÓN POR ÁREA")
        rows = [[a, usd(ing_area[a])] for a in AREAS]
        plain_table(["Área", "Facturación"], rows, [55 * mm, CONTENT_W - 55 * mm], signed_colidx=1,
                    signed_vals=[ing_area[a] for a in AREAS])

    # ── Gastos totales por área: barra de % si todas > 0 -- NO suma
    # Impuestos (fila aparte en el Sheet, "GASTOS TOTALES" ya es Directos +
    # Indirectos prorrateados por sí sola). Antes se sumaba impuestosActual
    # acá, a pedido se sacó: Impuestos no se cuenta como "gasto" en ninguna
    # apertura por área de este reporte (mismo criterio que ya usaba Unit
    # Economics, que nunca lo sumó). ──
    gt_area = data['gastosTotalesActual'] or {}
    gastos_area_abs = {a: (gt_area.get(a, 0) or 0) for a in AREAS}
    total_gastos_area = sum(gastos_area_abs.values())
    with keep_together():
        section_title("GASTOS TOTALES POR ÁREA")
        if total_gastos_area > 0 and all(v >= 0 for v in gastos_area_abs.values()):
            area_bar_chart([(a, gastos_area_abs[a], gastos_area_abs[a] / total_gastos_area * 100) for a in AREAS])
        else:
            plain_table(["Área", "Gastos Totales"], [[a, usd(gastos_area_abs[a])] for a in AREAS],
                        [55 * mm, CONTENT_W - 55 * mm], signed_colidx=1,
                        signed_vals=[gastos_area_abs[a] for a in AREAS])

    # ── Directos vs Indirectos: el ratio de "Ratios por área" mezcla costo
    # propio del área (Directos, fila "GASTOS DIRECTOS" del Sheet) con el
    # prorrateo de la estructura común (Indirectos, repartido según la
    # Matriz) -- en áreas chicas eso puede ser la mayor parte del ratio.
    # "Directos" acá es un gasto real (no una contribución/margen), así que
    # no debería dar negativo -- si pasa, es una señal real de revisar el
    # Sheet para cualquier área, no un caso esperado como en otras partes
    # del reporte (ver docstring del módulo sobre la facturación de Mesa). ──
    di_area = data.get('directosIndirectosActual')
    if di_area:
        with keep_together():
            section_title("GASTOS DIRECTOS VS INDIRECTOS POR ÁREA")
            rows = []
            areas_directos_neg = []
            for a in AREAS:
                dd = di_area.get(a, {})
                directos, indirectos = dd.get('directos', 0), dd.get('indirectos', 0)
                total = directos + indirectos
                pct_txt = f"{indirectos / total * 100:.1f}%" if (total > 0 and directos >= 0) else "N/D"
                if directos < 0:
                    areas_directos_neg.append(a)
                rows.append([a, usd(directos), usd(indirectos), pct_txt])
            plain_table(["Área", "Directos", "Indirectos", "% Indirectos / Total"], rows,
                        [40 * mm, 42 * mm, 42 * mm, CONTENT_W - 40 * mm - 42 * mm - 42 * mm],
                        signed_colidx=1, signed_vals=[di_area.get(a, {}).get('directos', 0) for a in AREAS])
            story.append(Paragraph(
                "El ratio de \"Gastos / Facturación\" de abajo mezcla costo propio del área (Directos) con el "
                "prorrateo de la estructura común (Indirectos) -- en áreas chicas como Banca Corporativa y Banca "
                "Privada, el prorrateo puede explicar la mayor parte del ratio.",
                styles['NotaChica'],
            ))
            if areas_directos_neg:
                story.append(Spacer(1, 2))
                story.append(Paragraph(
                    f"{', '.join(areas_directos_neg)}: \"Directos\" dio negativo este mes -- es un gasto real, no "
                    f"debería pasar. Vale la pena revisarlo en el Sheet antes de dar el mes por cerrado.",
                    styles['NotaChica'],
                ))

    # ── Ratios por área ──
    with keep_together():
        section_title("RATIOS POR ÁREA · GASTOS / FACTURACIÓN")
        rows = []
        hubo_na = False
        for a in AREAS:
            fact = ing_area[a]
            gasto = gastos_area_abs[a]
            if fact <= 0:
                cell = na_cell()
                hubo_na = True
            else:
                cell = ratio_cell(gasto / fact * 100)
            rows.append([a, usd(fact), usd(gasto), cell])
        data_table(["Área", "Facturación", "Gastos Totales", "Gastos / Facturación"], rows,
                   [40 * mm, 38 * mm, 42 * mm, CONTENT_W - 40 * mm - 38 * mm - 42 * mm], var_colidx=3)
        if hubo_na:
            story.append(Paragraph(
                "N/D: esa área tuvo facturación bruta <= 0 este mes (ver tabla de Facturación por área).",
                styles['NotaChica'],
            ))

    # ── Margen por área: "Ratios por área" mira costo (cuánto se gasta
    # por cada $ facturado); esto mira rentabilidad (cuánto queda). Mismo
    # Resultado por área que ya usa el KPI "Resultado" de arriba (suma por
    # área, no una resta re-derivada acá). ──
    resultado_area = data.get('resultadoPorAreaActual') or {}
    if resultado_area:
        with keep_together():
            section_title("MARGEN POR ÁREA · RESULTADO / FACTURACIÓN")
            rows = []
            hubo_na_margen = False
            for a in AREAS:
                fact = ing_area[a]
                result = resultado_area.get(a, 0)
                if fact <= 0:
                    cell = na_cell()
                    hubo_na_margen = True
                else:
                    cell = margen_cell(result / fact * 100)
                rows.append([a, usd(fact), usd(result), cell])
            data_table(["Área", "Facturación", "Resultado", "Margen"], rows,
                       [40 * mm, 42 * mm, 42 * mm, CONTENT_W - 40 * mm - 42 * mm - 42 * mm], var_colidx=3)
            if hubo_na_margen:
                story.append(Paragraph(
                    "N/D: esa área tuvo facturación bruta <= 0 este mes (ver tabla de Facturación por área).",
                    styles['NotaChica'],
                ))

    # ── Ratios generales ──
    with keep_together():
        story.append(Spacer(1, 2))
        if fact_act > 0:
            margen_pct = result_act / fact_act * 100
            gf_pct = gastos_act / fact_act * 100
            ratios_row = Table(
                [[margen_card("Margen neto (Resultado / Facturación)", margen_pct),
                  ratio_card("Gastos totales / Facturación", gf_pct, good_below=55)]],
                colWidths=[CONTENT_W / 2] * 2,
            )
        else:
            nota = "Facturación total negativa o cero este mes: el % no es interpretable"
            ratios_row = Table(
                [[na_card("Margen neto (Resultado / Facturación)", nota),
                  na_card("Gastos totales / Facturación", nota)]],
                colWidths=[CONTENT_W / 2] * 2,
            )
        ratios_row.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(ratios_row)

    # ── Unit economics: cruza la Matriz (comitentes y empleados por área)
    # con Facturación y Gastos Totales de mesActual. Si el Sheet no tiene
    # esos datos todavía, extract_data.js manda unitEconomics=null y esta
    # sección se omite en vez de romper.
    #
    # "Comitentes" sale de "CUENTAS ABIERTAS" (Matriz) -- SÍ cambia mes a
    # mes (antes se usaba "Comitentes totales" de CÁLCULOS AUX, un único
    # número fijo para todo el año; eso quedó como respaldo si un mes
    # puntual todavía no está cargado en CUENTAS ABIERTAS, ver
    # comitentesPorMes en extract_data.js). "Empleados" sigue siendo fijo
    # (no hay desglose mensual para eso en el Sheet). "Facturación" y
    # "Costo" son de mesActual -- por eso en un mes con facturación
    # negativa (ej. Mesa en Agosto), "Facturación / comitente" también da
    # negativa (correcto: antes usaba un promedio histórico fijo que no
    # reflejaba lo que pasó ese mes puntual). La "Facturación" de FAs acá es
    # neta de Comisiones Productores (lo que se queda FAs, no lo que
    # factura bruto el productor externo) -- no toca el resto del reporte,
    # donde "Facturación por área" sigue siendo la bruta del Sheet. ──
    ue = data.get('unitEconomics')
    if ue:
        col_a = 48 * mm
        col_rest = (CONTENT_W - col_a) / 3
        with keep_together():
            section_title("UNIT ECONOMICS")
            story.append(Paragraph(
                f"Comitentes: cuentas abiertas de {ue['mes']} (Matriz) "
                f"&nbsp;·&nbsp; Empleados: Matriz (fijo, no cambia mes a mes) "
                f"&nbsp;·&nbsp; Facturación (FAs neta de Comisiones Productores) y Costo total "
                f"(Directos + Indirectos prorrateados): datos de {ue['mes']}",
                styles['NotaChica'],
            ))
            story.append(Spacer(1, 4))
            rows = [[a['area'], num(a['comitentes']) if a['comitentes'] else '—',
                     usd2(a['facturacionMes'] / a['comitentes']) if a['comitentes'] else '—',
                     usd2(a['gastoTotal'] / a['comitentes']) if a['comitentes'] else '—']
                    for a in ue['porArea']]
            plain_table(["Área", "Comitentes", "Facturación / comitente", "Costo total / comitente"], rows,
                        [col_a, col_rest, col_rest, col_rest])

        with keep_together():
            rows = [[a['area'], num(a['empleados']) if a['empleados'] else '—',
                     usd2(a['facturacionMes'] / a['empleados']) if a['empleados'] else '—',
                     usd2(a['gastoTotal'] / a['empleados']) if a['empleados'] else '—']
                    for a in ue['porArea']]
            plain_table(["Área", "Empleados", "Facturación / empleado", "Costo total / empleado"], rows,
                        [col_a, col_rest, col_rest, col_rest])

    # ── Evolución Unit Economics: mismo criterio que "Evolución últimos
    # meses" (Facturación/Gastos/Resultado), pero por área y por comitente
    # -- para ver si el costo o la facturación por cliente vienen subiendo
    # o bajando, no solo la foto del mes. Comitentes sale de "CUENTAS
    # ABIERTAS" (Matriz) y varía mes a mes -- cada punto de la serie divide
    # por el comitente de ESE mes puntual, no por un número fijo. ──
    ue_trend = data.get('unitEconomicsTrend') or []
    if ue and len(ue_trend) > 1:
        meses_ue = [m['mes'][:3] for m in ue_trend]

        def serie_por_area(campo):
            series = []
            for a in AREAS:
                vals = []
                for m in ue_trend:
                    area_data = next((x for x in m['porArea'] if x['area'] == a), None)
                    comit = area_data['comitentes'] if area_data else 0
                    vals.append(area_data[campo] / comit if area_data and comit else 0)
                series.append((a, AREA_COLOR[a], vals))
            return series

        fmt_axis_usd2 = lambda v: usd2(v)
        with keep_together():
            section_title("EVOLUCIÓN UNIT ECONOMICS · COSTO TOTAL / COMITENTE")
            trend_chart(meses_ue, serie_por_area('gastoTotal'), fmt_axis=fmt_axis_usd2)

        with keep_together():
            section_title("EVOLUCIÓN UNIT ECONOMICS · FACTURACIÓN / COMITENTE")
            trend_chart(meses_ue, serie_por_area('facturacionMes'), fmt_axis=fmt_axis_usd2)

    # ── Excepciones / no recurrentes: gastos puntuales identificados por
    # palabra clave en la nota de la cuenta (ver EXCEPCION_KEYWORDS en
    # extract_data.js). Solo del mes actual -- extract_data.js ya filtra,
    # por eso no hace falta columna de mes acá. Vacío si no hubo ninguno. ──
    excepciones = data.get('excepciones') or []
    if excepciones:
        with keep_together():
            section_title("EXCEPCIONES / NO RECURRENTES")
            story.append(Paragraph(f"Datos de {excepciones[0]['mes']}", styles['NotaChica']))
            story.append(Spacer(1, 4))
            nota_style = ParagraphStyle('ExcNota', fontName='DMSans', fontSize=8.5, textColor=MUTED, leading=11)
            col_cuenta, col_monto = 45 * mm, 28 * mm
            col_nota = CONTENT_W - col_cuenta - col_monto
            rows = [[e['cuenta'], Paragraph(e['nota'], nota_style), usd(e['monto'])] for e in excepciones]
            total = sum(e['monto'] for e in excepciones)
            table_data = [["Cuenta", "Nota", "Monto"]] + rows + [['', 'Total', usd(total)]]
            t = Table(table_data, colWidths=[col_cuenta, col_nota, col_monto])
            t.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'DMSans'),
                ('FONTNAME', (-1, 1), (-1, -1), 'DMMono-Medium'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EDEAE4')),
                ('FONTNAME', (0, 0), (-1, 0), 'DMSans-Bold'),
                ('FONTNAME', (-1, -1), (-1, -1), 'DMSans-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, CREMA]),
                ('TOPPADDING', (0, 0), (-1, -1), 5.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
                ('LINEABOVE', (0, -1), (-1, -1), 0.6, BORDER),
                ('LINEBELOW', (0, -1), (-1, -1), 0.6, BORDER),
                ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
            ]))
            story.append(t)
            story.append(Spacer(1, 4))

    # ── Anexo: para cada rubro de "Top rubros" (general o por área) que
    # tiene algo más para mostrar (ver anexo_entries, calculado arriba), de
    # qué proveedores/movimientos se compone -- para responder "¿y qué es
    # esto?" (no "cuánto es cada mes" -- eso ya está arriba) sin inflar las
    # tablas principales. No todos los rubros de arriba tienen esto
    # cargado en el Sheet: si uno no aparece acá, es porque no hay cuenta
    # de Gastos Fijos Detalle NI cuenta exacta del mayor contable para ese
    # nombre (no un bug de este script -- ver el comentario de
    # anexo_entries más arriba para el porqué). Sin piso de USD 500 a
    # propósito en 'providers': la idea de este anexo es completitud, no
    # destacar los movimientos más grandes como las tablas de arriba.
    #
    # anexo_entries/cuentas_detalle/ledger_detalle ya se calcularon más
    # arriba (antes de las tablas de "Top rubros", para poder linkear el
    # nombre del rubro a su entrada acá vía nombre_cell/Anchor). Esta
    # sección siempre arranca en página nueva (PageBreak) -- un anexo no
    # es "más del cuerpo del reporte", es la referencia aparte a la que
    # ese link te manda, y mezclarlo con lo anterior en la misma página
    # rompería esa lectura.
    #
    # Cada entrada del Anexo termina con un link "Volver" de vuelta a CADA
    # lugar de donde realmente vino (anexo_fuentes, calculado arriba) --
    # un rubro visto solo en la tabla general lleva un link; uno visto
    # también en su área lleva dos. Nada de un destino fijo (se probó un
    # único "Volver arriba" a la página 1 y no servía: un mismo rubro
    # puede tener el link de ida desde más de un lugar, así que no hay una
    # única "página de origen"). Cada "Volver" apunta al Anchor de esa
    # sección puntual (sec_top_rubros / sec_top_rubros_area_<área>,
    # creados más arriba, justo antes de section_title/el label del
    # área), no al tope de la página 1. ──
    volver_style = ParagraphStyle('anexoVolver', fontName='DMSans', fontSize=8, textColor=AZUL)
    if anexo_entries:
        story.append(PageBreak())
        section_title("ANEXO · DETALLE DE CUENTAS")
        story.append(Paragraph(
            "De qué proveedores/conceptos (o movimientos del mayor contable, cuando no hay cuenta en "
            "Gastos Fijos Detalle) se compone cada cuenta de \"Top rubros\" -- no todas tienen este "
            "desglose cargado en el Sheet. Tocá el nombre de un rubro en las tablas de arriba para "
            "volver acá directamente.",
            styles['NotaChica'],
        ))
        story.append(Spacer(1, 4))
        for nombre, tipo in anexo_entries:
            with keep_together():
                story.append(Spacer(1, 10))
                story.append(Anchor(cuenta_slug(nombre)))
                # Más grande y con una mini-barra lateral + fondo, como un
                # section_title() pero más chico -- antes era un Paragraph
                # bold del mismo tamaño que el texto de las tablas de abajo
                # y se perdía entre una cuenta y la siguiente.
                cuenta_t = Table([[Paragraph(nombre, styles['AnexoCuenta'])]], colWidths=[CONTENT_W], rowHeights=[7 * mm])
                cuenta_t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), CREMA),
                    ('LINEBEFORE', (0, 0), (0, 0), 3, BORDEAUX),
                    ('LINEBELOW', (0, 0), (-1, 0), 0.6, BORDER),
                    ('LEFTPADDING', (0, 0), (0, 0), 10),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(cuenta_t)
                story.append(Spacer(1, 4))
                if tipo == 'providers':
                    rows = [[p['nombre'], num(p['anterior']), num(p['actual'])] for p in cuentas_detalle[nombre]]
                    plain_table(["Proveedor / Concepto", data['mesAnterior'], data['mesActual']], rows,
                                [CONTENT_W - 64 * mm, 32 * mm, 32 * mm])
                else:
                    # Agrupado por proveedor/concepto canónico (sin separar
                    # por número de factura/comprobante -- varias compras al
                    # mismo proveedor en distintos días del mes se suman en
                    # una sola fila), mismo estilo de tabla que "providers".
                    rows = [[p['nombre'], num(p['anterior']), num(p['actual'])] for p in ledger_agrupado[nombre]]
                    story.append(Paragraph(
                        "Sin cuenta propia en \"Gastos Fijos Detalle\" -- agrupado del mayor contable por "
                        "proveedor/concepto (convertidos de ARS a USD con el MEP de cada mes):",
                        styles['NotaChica'],
                    ))
                    story.append(Spacer(1, 2))
                    plain_table(["Proveedor / Concepto", data['mesAnterior'], data['mesActual']], rows,
                                [CONTENT_W - 64 * mm, 32 * mm, 32 * mm])
                for tipo_fuente, area_fuente in anexo_fuentes.get(nombre, []):
                    if tipo_fuente == 'general':
                        key, label = 'sec_top_rubros', 'Top rubros que más subieron'
                    else:
                        key, label = f'sec_top_rubros_area_{slugify(area_fuente)}', f'Top rubros · {area_fuente}'
                    story.append(Paragraph(f'<a href="#{key}"><u>&#8593; Volver a "{label}"</u></a>', volver_style))
                    story.append(Spacer(1, 1))

    # ── Notas de metodología: breve, al pie -- no repite todo el docstring
    # del módulo, solo lo que hace falta para leer los montos de este PDF
    # puntual (el tipo de cambio usado, principalmente). ──
    dolar = data.get('dolarMEP')
    with keep_together():
        section_title("NOTAS DE METODOLOGÍA")
        bullets_meta = []
        if dolar:
            bullets_meta.append(f"Tipo de cambio (MEP) usado para convertir a USD este mes: {usd2(dolar)}.")
        bullets_meta.append(
            "Las variaciones de Facturación Bruta, Gastos Totales y Resultado (arriba de todo) usan el valor "
            "absoluto del mes anterior como base del %, para que el signo siempre coincida con si mejoró o "
            "empeoró, incluso si la base era negativa o el valor cruzó el cero. Solo se reemplaza por el delta "
            "en USD cuando la base del mes anterior es exactamente 0 (división por cero)."
        )
        bullets_meta.append(
            "\"Gastos / Facturación\" por área mezcla costo directo del área con el prorrateo de gastos "
            "indirectos (ver \"Gastos Directos vs Indirectos por área\")."
        )
        for b in bullets_meta:
            story.append(Paragraph(f"•  {b}", styles['NotaChica']))
            story.append(Spacer(1, 3))

    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=HEADER_H + 11 * mm, bottomMargin=17 * mm,
                             leftMargin=MARGIN, rightMargin=MARGIN,
                             title=f"Reporte Mensual NEIX · {mes_label}", author="NEIX")
    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='real_data.json')
    ap.add_argument('--out', default='reporte.pdf')
    ap.add_argument('--mes-label', default=None, help='Ej. "Agosto 2026" -- si no se pasa, se arma de mesActual + --anio')
    ap.add_argument('--anio', default=None)
    ap.add_argument('--bullet', action='append', default=[],
                     help='Línea de "Análisis del mes" escrita a mano (repetible, 1-3 veces). '
                          'Si no se pasa ninguna, el análisis queda solo con lo que se detecta automáticamente.')
    args = ap.parse_args()

    with open(args.data, encoding='utf-8') as f:
        data = json.load(f)

    mes_label = args.mes_label or (f"{data['mesActual']} {args.anio}" if args.anio else data['mesActual'])
    build(data, mes_label, args.out, bullets_extra=args.bullet)
    print(f"OK: {args.out}")
