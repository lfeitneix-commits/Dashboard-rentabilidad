"""Arma el PDF de "Reporte Mensual con IA" a partir de real_data.json
(generado por extract_data.js) para el mes más reciente cargado en el Sheet.

Uso:
    python3 build_report.py --data real_data.json --out reporte.pdf \
        [--anio 2026]

Decisiones de diseño que valen la pena recordar (se pisaron una vez en el
primer reporte real, el de Agosto 2026, cuando la Facturación de Mesa dio
negativa ese mes):
  - Un % de variación solo es confiable si la base (mes anterior) es > 0.
    Si no, se muestra el delta en $ (var_cell_delta), nunca un % que puede
    salir con el signo invertido por dividir por un número negativo.
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

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
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

GRAFITO_HEX, BORDEAUX_HEX, VERDE_HEX, MUTED_HEX = '#3D3D3D', '#AB1930', '#004836', '#9A8E7D'
GRAFITO = colors.HexColor(GRAFITO_HEX)
BORDEAUX = colors.HexColor(BORDEAUX_HEX)
VERDE = colors.HexColor(VERDE_HEX)
MUTED = colors.HexColor(MUTED_HEX)
CREMA = colors.HexColor('#F7F5F3')
BORDER = colors.HexColor('#E8E6E3')
VERDE_TINT = colors.HexColor('#E6EEEA')
BORDEAUX_TINT = colors.HexColor('#F6E3E6')
MUTED_TINT = colors.HexColor('#F0EDE8')
AREA_COLOR = {
    'Mesa': colors.HexColor('#003F61'),
    'FAs': colors.HexColor('#9A8E7D'),
    'Banca Corporativa': colors.HexColor('#AB1930'),
    'Banca Privada': colors.HexColor('#004836'),
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
        if delta == 0:
            icon, color_hex, tint = asset('tri_flat_muted.png'), MUTED_HEX, MUTED_TINT
            txt = '0'
        elif delta > 0:
            icon, color_hex, tint = asset('tri_up_verde.png'), VERDE_HEX, VERDE_TINT
            txt = f'+{num(delta)}'
        else:
            icon, color_hex, tint = asset('tri_down_bordeaux.png'), BORDEAUX_HEX, BORDEAUX_TINT
            txt = num(delta)
        html = f'<img src="{icon}" width="7.5" height="7.5" valign="-1.3"/>&nbsp;<font color="{color_hex}">{txt}</font>'
        return Paragraph(html, styles['VarCell']), tint

    def ratio_cell(pct, good_below=50.0):
        good = pct <= good_below
        color_hex = VERDE_HEX if good else BORDEAUX_HEX
        tint = VERDE_TINT if good else BORDEAUX_TINT
        return Paragraph(f'<font color="{color_hex}">{pct:.1f}%</font>', styles['VarCell']), tint

    def na_cell():
        return Paragraph(f'<font color="{MUTED_HEX}">N/D</font>', styles['VarCell']), MUTED_TINT

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

    def kpi_card(label, value_str, para_tint):
        para, _tint = para_tint
        para.style = styles['KpiVar']
        cell = Table(
            [[Paragraph(label.upper(), styles['KpiLabel'])],
             [Paragraph(value_str, styles['KpiValue'])],
             [para]],
            colWidths=[58 * mm],
        )
        cell.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, BORDEAUX),
            ('TOPPADDING', (0, 0), (0, 0), 12),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 12),
            ('TOPPADDING', (0, 1), (0, 1), 1),
            ('TOPPADDING', (0, 2), (0, 2), 1),
        ]))
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

    def trend_chart(meses, series):
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
            d.add(String(pad_l - 3, y - 2.5, f"{val/1000:,.0f}k".replace(',', '.'), fontName='DMMono', fontSize=6.5, fillColor=MUTED, textAnchor='end'))
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

    if kpi_ant:
        fact_ant, gastos_ant, result_ant = kpi_ant['ingresos'], kpi_ant['egresos'], kpi_ant['resultado']
        fact_var = var_cell((fact_act - fact_ant) / fact_ant * 100) if fact_ant > 0 else var_cell_delta(fact_act - fact_ant)
        gastos_var = var_cell((gastos_act - gastos_ant) / gastos_ant * 100) if gastos_ant > 0 else var_cell_delta(gastos_act - gastos_ant)
        result_var = var_cell((result_act - result_ant) / result_ant * 100) if result_ant > 0 else var_cell_delta(result_act - result_ant)
    else:
        fact_var = gastos_var = result_var = var_cell(0.0)

    kpis = Table(
        [[kpi_card("Facturación bruta", usd(fact_act), fact_var),
          kpi_card("Gastos totales", usd(gastos_act), gastos_var),
          kpi_card("Resultado", usd(result_act), result_var)]],
        colWidths=[CONTENT_W / 3] * 3,
    )
    kpis.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(kpis)

    # ── Análisis del mes: arranca con lo mínimo verificable automáticamente
    # (mayor rubro que subió) y, si se pasaron --bullet por CLI, los suma en
    # vez del placeholder genérico -- ver docstring del módulo y el README
    # de este directorio para el criterio de cuándo conviene escribir uno a
    # mano (el "por qué", no repetir números que ya están en las tablas;
    # si citás un monto puntual, sumale el promedio histórico para que se
    # note si es un valor atípico de este mes o no). ──
    section_title(f"ANÁLISIS DEL MES · {mes_label.upper()}")
    bullets = []
    if data['rubrosVariacion']:
        top = data['rubrosVariacion'][0]
        bullets.append(
            f"{top['nombre']} fue el rubro que más subió ({'+' if top['deltaPct'] >= 0 else ''}{top['deltaPct']:.1f}%, "
            f"de {num(top['anterior'])} a {num(top['actual'])})."
        )
    if bullets_extra:
        bullets.extend(bullets_extra)
    else:
        bullets.append("[Completar a mano: por qué pasó lo de arriba, y cualquier otra cosa llamativa de este mes.]")
    for b in bullets:
        story.append(Paragraph(f"•  {b}", styles['BulletCustom']))
        story.append(Spacer(1, 4))

    # ── Evolución (hasta 6 meses) ──
    if len(data['kpiTrend']) > 1:
        section_title("EVOLUCIÓN ÚLTIMOS MESES")
        meses_trend = [m['mes'][:3] for m in data['kpiTrend']]
        series = [
            ("Facturación", GRAFITO, [m['ingresos'] for m in data['kpiTrend']]),
            ("Gastos", BORDEAUX, [m['egresos'] for m in data['kpiTrend']]),
            ("Resultado", VERDE, [m['resultado'] for m in data['kpiTrend']]),
        ]
        trend_chart(meses_trend, series)

    # ── Top rubros que más subieron ──
    if data['rubrosVariacion']:
        section_title("TOP RUBROS QUE MÁS SUBIERON")
        rows = [[r['nombre'], num(r['anterior']), num(r['actual']), var_cell(r['deltaPct'])] for r in data['rubrosVariacion'][:3]]
        data_table(["Rubro", data['mesAnterior'], data['mesActual'], "Variación"], rows,
                   [55 * mm, 28 * mm, 28 * mm, CONTENT_W - 55 * mm - 56 * mm], var_colidx=3)

    # ── Proveedores con mayor variación (no los de mayor monto -- ver nota
    # en extract_data.js sobre el filtro anterior>0 && actual>0) ──
    if data['proveedores']:
        section_title("PROVEEDORES CON MAYOR VARIACIÓN")
        rows = []
        for p in data['proveedores'][:5]:
            rows.append([p['nombre'], num(p['anterior']), num(p['actual']), var_cell(p['deltaPct'])])
        data_table(["Proveedor", data['mesAnterior'], data['mesActual'], "Variación"], rows,
                   [65 * mm, 26 * mm, 26 * mm, CONTENT_W - 65 * mm - 52 * mm], var_colidx=3)

    # ── Facturación por área: siempre tabla con signo (nunca %, por si
    # alguna área da negativa -- ver docstring). ──
    section_title("FACTURACIÓN POR ÁREA")
    ing_area = data['ingresosPorAreaActual']
    rows = [[a, usd(ing_area[a])] for a in AREAS]
    plain_table(["Área", "Facturación"], rows, [55 * mm, CONTENT_W - 55 * mm], signed_colidx=1,
                signed_vals=[ing_area[a] for a in AREAS])

    # ── Gastos totales + Impuestos por área: barra de % si todas > 0 ──
    gt_area = data['gastosTotalesActual'] or {}
    imp_area = data['impuestosActual'] or {}
    gastos_area_abs = {a: (gt_area.get(a, 0) or 0) + (imp_area.get(a, 0) or 0) for a in AREAS}
    total_gastos_area = sum(gastos_area_abs.values())
    section_title("GASTOS TOTALES + IMPUESTOS POR ÁREA")
    if total_gastos_area > 0 and all(v >= 0 for v in gastos_area_abs.values()):
        area_bar_chart([(a, gastos_area_abs[a], gastos_area_abs[a] / total_gastos_area * 100) for a in AREAS])
    else:
        plain_table(["Área", "Gastos + Impuestos"], [[a, usd(gastos_area_abs[a])] for a in AREAS],
                    [55 * mm, CONTENT_W - 55 * mm], signed_colidx=1,
                    signed_vals=[gastos_area_abs[a] for a in AREAS])

    # ── Ratios por área ──
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

    # ── Ratios generales ──
    story.append(Spacer(1, 2))
    if fact_act > 0:
        margen_pct = result_act / fact_act * 100
        gf_pct = gastos_act / fact_act * 100
        ratios_row = Table(
            [[ratio_card("Margen neto (Resultado / Facturación)", margen_pct, good_below=100),
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
    # empleados, operaciones promedio por área) con Gastos Totales y Sueldos
    # y CS Back del mes actual. Si el Sheet no tiene esos datos todavía
    # (hoja Matriz sin la sección CÁLCULOS AUX), extract_data.js manda
    # unitEconomics=null y esta sección se omite en vez de romper. ──
    ue = data.get('unitEconomics')
    if ue:
        section_title("UNIT ECONOMICS")
        story.append(Paragraph(f"Datos de {ue['mes']}", styles['NotaChica']))
        story.append(Spacer(1, 4))
        col_a = 48 * mm
        col_rest = (CONTENT_W - col_a) / 3

        rows = [[a['area'], num(a['comitentes']) if a['comitentes'] else '—',
                 usd2(a['facturacionPromedio'] / a['comitentes']) if a['comitentes'] else '—',
                 usd2(a['gastoTotal'] / a['comitentes']) if a['comitentes'] else '—']
                for a in ue['porArea']]
        plain_table(["Área", "Comitentes", "Facturación / comitente", "Costo / comitente"], rows,
                    [col_a, col_rest, col_rest, col_rest])

        rows = [[a['area'], num(a['empleados']) if a['empleados'] else '—',
                 usd2(a['facturacionPromedio'] / a['empleados']) if a['empleados'] else '—',
                 usd2(a['gastoTotal'] / a['empleados']) if a['empleados'] else '—']
                for a in ue['porArea']]
        plain_table(["Área", "Empleados", "Facturación / empleado", "Costo / empleado"], rows,
                    [col_a, col_rest, col_rest, col_rest])

    # ── Excepciones / no recurrentes: gastos puntuales identificados por
    # palabra clave en la nota de la cuenta (ver EXCEPCION_KEYWORDS en
    # extract_data.js). Vacío si no hubo ninguno en los meses cargados. ──
    excepciones = data.get('excepciones') or []
    if excepciones:
        section_title("EXCEPCIONES / NO RECURRENTES")
        nota_style = ParagraphStyle('ExcNota', fontName='DMSans', fontSize=8.5, textColor=MUTED, leading=11)
        col_mes, col_cuenta, col_monto = 20 * mm, 38 * mm, 26 * mm
        col_nota = CONTENT_W - col_mes - col_cuenta - col_monto
        rows = [[e['mes'], e['cuenta'], Paragraph(e['nota'], nota_style), usd(e['monto'])] for e in excepciones]
        total = sum(e['monto'] for e in excepciones)
        table_data = [["Mes", "Cuenta", "Nota", "Monto"]] + rows + [['', '', 'Total', usd(total)]]
        t = Table(table_data, colWidths=[col_mes, col_cuenta, col_nota, col_monto])
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

    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=HEADER_H + 11 * mm, bottomMargin=17 * mm,
                             leftMargin=MARGIN, rightMargin=MARGIN)
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
