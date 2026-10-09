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
from contextlib import contextmanager

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
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


def build(data, mes_label, out_path, bullets_extra=None):
    story = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('H2White', fontName='DMSans-Bold', fontSize=11.5, textColor=colors.white))
    styles.add(ParagraphStyle('KpiLabel', fontName='DMSans-Bold', fontSize=8, textColor=GRAFITO, alignment=TA_CENTER))
    styles.add(ParagraphStyle('KpiValue', fontName='DMMono-Medium', fontSize=16, leading=21, textColor=GRAFITO, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('KpiVar', fontName='DMMono-Medium', fontSize=10, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('VarCell', fontName='DMMono-Medium', fontSize=9.5, alignment=TA_CENTER))
    styles.add(ParagraphStyle('BulletCustom', fontName='DMSans', fontSize=9.5, leading=14, textColor=GRAFITO, leftIndent=4))
    styles.add(ParagraphStyle('NotaChica', fontName='DMSans', fontSize=8, textColor=MUTED, leftIndent=0))

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
    # Rubros que efectivamente subieron (deltaPct > 0), tope 10 -- usado acá
    # y en "Análisis del mes" para que ambos miren la misma lista; si se
    # completara con bajas solo para llegar a 10 contradiría el título de
    # la sección de abajo.
    rubros_suben = [r for r in data['rubrosVariacion'] if r['deltaPct'] > 0][:10]

    if kpi_ant:
        fact_ant, gastos_ant, result_ant = kpi_ant['ingresos'], kpi_ant['egresos'], kpi_ant['resultado']
        fact_var = pct_or_delta(fact_act, fact_ant)
        gastos_var = pct_or_delta(gastos_act, gastos_ant)
        result_var = pct_or_delta(result_act, result_ant)
    else:
        fact_var = gastos_var = result_var = var_cell(0.0)

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

    # ── Análisis del mes: arranca con lo mínimo verificable automáticamente
    # (mayor rubro que subió) y, si se pasaron --bullet por CLI, los suma en
    # vez del placeholder genérico -- ver docstring del módulo y el README
    # de este directorio para el criterio de cuándo conviene escribir uno a
    # mano (el "por qué", no repetir números que ya están en las tablas;
    # si citás un monto puntual, sumale el promedio histórico para que se
    # note si es un valor atípico de este mes o no). ──
    with keep_together():
        section_title(f"ANÁLISIS DEL MES · {mes_label.upper()}")
        bullets = []
        ya_mencionado = set()
        if data['rubrosVariacion']:
            top = data['rubrosVariacion'][0]
            top_txt = (
                f"{top['nombre']} fue el rubro que más subió ({'+' if top['deltaPct'] >= 0 else ''}{top['deltaPct']:.1f}%, "
                f"de {num(top['anterior'])} a {num(top['actual'])})."
            )
            if top.get('notaManual'):
                top_txt += f" Esto fue porque {top['notaManual']}."
            bullets.append(top_txt)
            ya_mencionado.add(top['nombre'])
        # Notas manuales para cualquier otro rubro/proveedor del top que
        # tenga un "por qué" cargado (ver NOTAS_CUENTAS en extract_data.js)
        # y no se haya mencionado ya arriba -- esto es lo que hace que el
        # análisis explique, no solo liste números.
        for item in rubros_suben + data['proveedores'][:5]:
            nota = item.get('notaManual')
            if not nota or item['nombre'] in ya_mencionado:
                continue
            ya_mencionado.add(item['nombre'])
            signo = 'subió' if item['deltaPct'] >= 0 else 'bajó'
            pct = f"{'+' if item['deltaPct'] >= 0 else ''}{item['deltaPct']:.1f}%"
            bullets.append(
                f"{item['nombre']} {signo} {pct} (de {num(item['anterior'])} a {num(item['actual'])}) porque {nota}."
            )
        if bullets_extra:
            bullets.extend(bullets_extra)
        else:
            bullets.append("[Completar a mano: por qué pasó lo de arriba, y cualquier otra cosa llamativa de este mes.]")
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

    # ── Top rubros que más subieron (rubros_suben calculado arriba) ──
    if rubros_suben:
        with keep_together():
            section_title("TOP RUBROS QUE MÁS SUBIERON")
            rows = [[r['nombre'], num(r['anterior']), num(r['actual']), var_cell(r['deltaPct'])] for r in rubros_suben]
            data_table(["Rubro", data['mesAnterior'], data['mesActual'], "Variación"], rows,
                       [55 * mm, 28 * mm, 28 * mm, CONTENT_W - 55 * mm - 56 * mm], var_colidx=3)

    # ── Mismo top, aperturado por área (rubrosVariacionPorArea en
    # extract_data.js) -- "Clasificación de gastos" (la fuente de la tabla
    # de arriba) es un total de toda la empresa, así que esto sale de la
    # otra fuente que sí tiene columna por área. Una mini-tabla por área
    # (top 5 cada una, mismo criterio deltaPct > 0 que la tabla general) --
    # se salta el área si no tuvo ningún rubro que subiera. ──
    rubros_por_area = data.get('rubrosVariacionPorArea') or {}
    area_blocks = []
    for area in AREAS:
        suben_area = [r for r in rubros_por_area.get(area, []) if r['deltaPct'] > 0][:5]
        if suben_area:
            area_blocks.append((area, suben_area))
    for i, (area, suben_area) in enumerate(area_blocks):
        with keep_together():
            if i == 0:
                section_title("TOP RUBROS QUE MÁS SUBIERON · POR ÁREA")
            story.append(Paragraph(area, ParagraphStyle(f'areaRubroLabel{area}', fontName='DMSans-Bold', fontSize=9.5, textColor=AREA_COLOR[area])))
            story.append(Spacer(1, 2))
            rows = [[r['nombre'], num(r['anterior']), num(r['actual']), var_cell(r['deltaPct'])] for r in suben_area]
            data_table(["Rubro", data['mesAnterior'], data['mesActual'], "Variación"], rows,
                       [55 * mm, 28 * mm, 28 * mm, CONTENT_W - 55 * mm - 56 * mm], var_colidx=3)

    # ── Cuentas/proveedores con mayor variación (no los de mayor monto --
    # ver nota en extract_data.js sobre el filtro anterior>0 && actual>0).
    # "Cuenta / Proveedor" porque Gastos Fijos Detalle no siempre tiene un
    # proveedor con nombre propio en esa fila -- a veces es una cuenta
    # genérica (ej. "Gtos Mant de Oficina"), y llamarlo solo "Proveedor"
    # sugiere algo más específico de lo que hay. ──
    if data['proveedores']:
        with keep_together():
            section_title("CUENTAS / PROVEEDORES CON MAYOR VARIACIÓN")
            rows = []
            for p in data['proveedores'][:5]:
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

    # ── Gastos totales + Impuestos por área: barra de % si todas > 0 ──
    gt_area = data['gastosTotalesActual'] or {}
    imp_area = data['impuestosActual'] or {}
    gastos_area_abs = {a: (gt_area.get(a, 0) or 0) + (imp_area.get(a, 0) or 0) for a in AREAS}
    total_gastos_area = sum(gastos_area_abs.values())
    with keep_together():
        section_title("GASTOS TOTALES + IMPUESTOS POR ÁREA")
        if total_gastos_area > 0 and all(v >= 0 for v in gastos_area_abs.values()):
            area_bar_chart([(a, gastos_area_abs[a], gastos_area_abs[a] / total_gastos_area * 100) for a in AREAS])
        else:
            plain_table(["Área", "Gastos + Impuestos"], [[a, usd(gastos_area_abs[a])] for a in AREAS],
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
        data_table(["Área", "Facturación", "Gastos + Impuestos", "Gastos / Facturación"], rows,
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

    # ── Unit economics: cruza "CÁLCULOS AUX" de la Matriz (comitentes,
    # empleados por área -- sin desglose mensual en el Sheet) con
    # Facturación y Gastos Totales de mesActual. Si el Sheet no tiene esos
    # datos todavía (hoja Matriz sin la sección CÁLCULOS AUX), extract_data.js
    # manda unitEconomics=null y esta sección se omite en vez de romper.
    #
    # "Comitentes" y "Empleados" son fijos en la Matriz (no cambian de mes a
    # mes, no hay desglose mensual para eso en el Sheet); "Facturación" y
    # "Costo" sí son de mesActual -- por eso en un mes con facturación
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
                f"Comitentes y Empleados: Matriz (fijo, no cambia mes a mes) "
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
    # o bajando, no solo la foto del mes. Comitentes es fijo (Matriz), así
    # que la serie es simplemente facturación/costo de cada mes dividido
    # por ese número constante. ──
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
                          'Si no se pasa ninguna, queda el placeholder "[Completar a mano: ...]".')
    args = ap.parse_args()

    with open(args.data, encoding='utf-8') as f:
        data = json.load(f)

    mes_label = args.mes_label or (f"{data['mesActual']} {args.anio}" if args.anio else data['mesActual'])
    build(data, mes_label, args.out, bullets_extra=args.bullet)
    print(f"OK: {args.out}")
