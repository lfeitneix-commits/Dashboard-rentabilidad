"""Arma el PDF de "Reporte Mensual Capital N" a partir de real_data.json
(generado por extract_data.js).

Uso:
    python3 build_report_capn.py --data real_data.json \
        --out reporte_capital_n.pdf --mes-label "Junio 2026"

Capital N es una entidad propia (hoja separada del Sheet, ST.capnData en
index.html), no una de las 4 áreas de staff -- tiene su propio
Facturación/Gastos/Resultado, sin prorrateo de indirectos (no aplica acá:
es una sola entidad, no hay nada que repartir entre áreas). Mismo tipo de
reporte que build_report_area.py (KPIs, Resultado Acumulado, ALERTAS DEL
MES, Análisis del mes, evolución en gráfico), pero con "FIJOS VS.
VARIABLES" en vez de Unit Economics -- Capital N no tiene datos de
comitentes/empleados propios en el Sheet. Sin Anexo ni
"Excepciones/No recurrentes" (dependen del mayor contable, que Capital N
no tiene).
"""
import argparse
import json
from contextlib import contextmanager

from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, String, Line, Circle

from build_report import (
    num, usd,
    GRAFITO, BORDEAUX, VERDE, MUTED, AZUL, CREMA, BORDER,
    VERDE_TINT, BORDEAUX_TINT, MUTED_TINT,
    PAGE_W, PAGE_H, HEADER_H, MARGIN, CONTENT_W, logo, logo_target_h,
)

CAPN_COLOR = colors.HexColor('#8C6B2F')  # dorado/bronce -- distingue a Capital N de las 4 áreas (AZUL/MUTED/BORDEAUX/VERDE)
FIJOS_COLOR = colors.HexColor('#476785')  # mismo celeste que "Fijos" en el gráfico de barras de index.html
VARIABLES_COLOR = colors.HexColor('#9A8E7D')  # mismo tono que "Variables" en index.html


def build_capn(data, mes_label, out_path):
    story = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('KpiLabel', fontName='DMSans-Bold', fontSize=8, textColor=GRAFITO, alignment=TA_CENTER))
    styles.add(ParagraphStyle('KpiValue', fontName='DMMono-Medium', fontSize=16, leading=21, textColor=GRAFITO, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('KpiVar', fontName='DMMono-Medium', fontSize=10, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('VarCell', fontName='DMMono-Medium', fontSize=9.5, alignment=TA_CENTER))
    styles.add(ParagraphStyle('NotaChica', fontName='DMSans', fontSize=8, textColor=MUTED, leftIndent=0))
    styles.add(ParagraphStyle('BulletCustom', fontName='DMSans', fontSize=9.5, leading=14, textColor=GRAFITO, leftIndent=4))
    styles.add(ParagraphStyle('H2White', fontName='DMSans-Bold', fontSize=11.5, textColor=colors.white))

    def draw_header(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(GRAFITO)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(CAPN_COLOR)
        p = canvas.beginPath()
        p.moveTo(PAGE_W * 0.56, PAGE_H - HEADER_H)
        p.lineTo(PAGE_W * 0.66, PAGE_H - HEADER_H)
        p.lineTo(PAGE_W * 0.60, PAGE_H)
        p.lineTo(PAGE_W * 0.50, PAGE_H)
        p.close()
        canvas.drawPath(p, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor('#2A2A2A'))
        canvas.rect(0, PAGE_H - HEADER_H - 2.2 * mm, PAGE_W, 2.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(CAPN_COLOR)
        canvas.rect(0, PAGE_H - HEADER_H - 2.2 * mm, PAGE_W * 0.35, 2.2 * mm, stroke=0, fill=1)
        renderPDF.draw(logo, canvas, MARGIN, PAGE_H - HEADER_H + (HEADER_H - logo_target_h) / 2 + 1 * mm)
        canvas.setFillColor(colors.white)
        canvas.setFont('DMSans-Bold', 15)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - HEADER_H / 2 - 1, "Reporte · Capital N")
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
            color_hex, tint, txt = '#9A8E7D', MUTED_TINT, '0,0%'
        elif pct > 0:
            color_hex, tint = '#004836', VERDE_TINT
            txt = f'+{pct:.1f}%'
        else:
            color_hex, tint = '#AB1930', BORDEAUX_TINT
            txt = f'{pct:.1f}%'
        return Paragraph(f'<font color="{color_hex}">{txt}</font>', styles['VarCell']), tint

    def var_cell_delta(delta):
        if delta == 0:
            color_hex, tint, txt = '#9A8E7D', MUTED_TINT, 'USD 0'
        elif delta > 0:
            color_hex, tint = '#004836', VERDE_TINT
            txt = f'+USD {num(delta)}'
        else:
            color_hex, tint = '#AB1930', BORDEAUX_TINT
            txt = f'USD {num(delta)}'
        return Paragraph(f'<font color="{color_hex}">{txt}</font>', styles['VarCell']), tint

    def pct_or_delta(actual, anterior):
        if anterior == 0:
            return var_cell_delta(actual - anterior)
        return var_cell((actual - anterior) / abs(anterior) * 100)

    @contextmanager
    def keep_together():
        start = len(story)
        yield
        block = story[start:]
        del story[start:]
        if block:
            story.append(KeepTogether(block))

    def section_title(title):
        story.append(Spacer(1, 16))
        t = Table([[Paragraph(title, styles['H2White'])]],
                   colWidths=[CONTENT_W], rowHeights=[8 * mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GRAFITO),
            ('LINEBEFORE', (0, 0), (0, 0), 3.5, CAPN_COLOR),
            ('LEFTPADDING', (0, 0), (0, 0), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    def kpi_card(label, value_str, para_tint, sub_label=None):
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
            ('LINEABOVE', (0, 0), (-1, 0), 3, CAPN_COLOR),
            ('TOPPADDING', (0, 0), (0, 0), 12),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 12),
            ('TOPPADDING', (0, 1), (0, 1), 1),
            ('TOPPADDING', (0, 2), (0, 2), 1),
        ]
        if sub_label:
            style_cmds.append(('TOPPADDING', (0, 3), (0, 3), 1))
        cell.setStyle(TableStyle(style_cmds))
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

    def ratio_card(label, value_str):
        cell = Table(
            [[Paragraph(label.upper(), styles['KpiLabel'])],
             [Paragraph(value_str, ParagraphStyle('RatioValue', fontName='DMMono-Medium', fontSize=15, textColor=GRAFITO, alignment=TA_CENTER, spaceBefore=4))]],
            colWidths=[CONTENT_W / 3],
        )
        cell.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
            ('LINEABOVE', (0, 0), (-1, 0), 3, CAPN_COLOR),
            ('TOPPADDING', (0, 0), (0, 0), 10),
            ('BOTTOMPADDING', (0, 1), (0, 1), 10),
            ('TOPPADDING', (0, 1), (0, 1), 2),
        ]))
        return cell

    def plain_table(header_row, rows, col_widths):
        table_data = [header_row] + rows
        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
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
        ]))
        story.append(t)
        story.append(Spacer(1, 4))

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

    def historico_cell(r):
        if r.get('ratioVsHistorico') is None:
            return Paragraph('<font color="#9A8E7D">N/D</font>', styles['VarCell'])
        if not r.get('esAtipico'):
            return Paragraph('<font color="#9A8E7D">en línea</font>', styles['VarCell'])
        desvio_pct = (r['ratioVsHistorico'] - 1) * 100
        signo = '+' if desvio_pct >= 0 else ''
        return Paragraph(f'<font color="#AB1930">atípico {signo}{desvio_pct:.0f}%</font>', styles['VarCell'])

    def trend_chart(meses, series, fmt_axis=None):
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
    capn = data.get('capn')
    if not capn or not capn.get('trend'):
        raise ValueError('No hay datos de Capital N en real_data.json -- revisar que ST.capnData se haya cargado')

    trend = capn['trend']
    fv_trend = capn.get('fijosVariablesTrend') or []
    rubros = capn.get('rubrosVariacion') or []
    conceptos_actual = capn.get('conceptosActual') or {}
    actual = trend[-1]
    anterior = trend[-2] if len(trend) > 1 else None

    fact_var = pct_or_delta(actual['ingresos'], anterior['ingresos']) if anterior else (Paragraph('', styles['VarCell']), MUTED_TINT)
    gastos_var = pct_or_delta(actual['egresos'], anterior['egresos']) if anterior else (Paragraph('', styles['VarCell']), MUTED_TINT)
    result_var = pct_or_delta(actual['resultado'], anterior['resultado']) if anterior else (Paragraph('', styles['VarCell']), MUTED_TINT)
    kpi_sub = f"vs. {anterior['mes']}" if anterior else None

    rubros_suben = [r for r in rubros if r['deltaPct'] is not None and r['deltaPct'] > 0]

    def nota_historico(r):
        if r.get('ratioVsHistorico') is None:
            return ''
        n_hist = r['historicoMesesCount']
        promedio_txt = num(r['promedioHistorico'])
        desvio_pct = abs(r['ratioVsHistorico'] - 1) * 100
        if r.get('esAtipico'):
            direccion = 'sobre' if r['ratioVsHistorico'] > 1 else 'bajo'
            return f" Atípico: {desvio_pct:.0f}% {direccion} su promedio de {n_hist} meses ({promedio_txt})."
        return f" En línea con su promedio de {n_hist} meses ({promedio_txt})."

    kpis = Table(
        [[kpi_card("Facturación", usd(actual['ingresos']), fact_var, kpi_sub),
          kpi_card("Gastos", usd(actual['egresos']), gastos_var, kpi_sub),
          kpi_card("Resultado", usd(actual['resultado']), result_var, kpi_sub)]],
        colWidths=[CONTENT_W / 3] * 3,
    )
    kpis.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(Spacer(1, 4))
    story.append(kpis)

    # ── Resultado acumulado del año en curso ──
    if len(trend) > 1:
        resultado_acum = sum(m['resultado'] for m in trend)
        primer_mes = trend[0]['mes']
        with keep_together():
            story.append(Spacer(1, 6))
            story.append(accum_card(f"Resultado acumulado {primer_mes} - {actual['mes']} · Capital N", resultado_acum))

    # ── Alertas del mes ──
    alertas = []
    if actual['resultado'] < 0:
        alertas.append(f"Resultado del mes fue negativo ({usd(actual['resultado'])}).")
    if actual['ingresos'] <= 0:
        alertas.append("Sin facturación (o facturación negativa) este mes.")
    if anterior and actual['ingresos'] > 0 and anterior['ingresos'] > 0:
        margen_actual = actual['resultado'] / actual['ingresos']
        margen_anterior = anterior['resultado'] / anterior['ingresos']
        if margen_actual < 0 and margen_anterior >= 0:
            alertas.append("Pasó a margen negativo este mes (el mes anterior había sido positivo).")
    if rubros_suben and rubros_suben[0].get('esAtipico'):
        top_alerta = rubros_suben[0]
        direccion = 'por encima' if top_alerta['ratioVsHistorico'] > 1 else 'por debajo'
        desvio_pct = abs(top_alerta['ratioVsHistorico'] - 1) * 100
        alertas.append(
            f"{top_alerta['nombre']} tuvo un salto atípico este mes: está {desvio_pct:.0f}% {direccion} de su "
            f"propio promedio histórico."
        )
    with keep_together():
        story.append(Spacer(1, 6))
        alertas_t = Table([[Paragraph("ALERTAS DEL MES", styles['H2White'])]], colWidths=[CONTENT_W], rowHeights=[8 * mm])
        alertas_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BORDEAUX if alertas else VERDE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (0, 0), 10),
        ]))
        story.append(alertas_t)
        story.append(Spacer(1, 6))
        if alertas:
            for a in alertas:
                story.append(Paragraph(f"•  {a}", styles['BulletCustom']))
                story.append(Spacer(1, 3))
        else:
            story.append(Paragraph(
                "Sin alertas relevantes este mes para Capital N: resultado positivo, hubo facturación, sin cambio "
                "a margen negativo ni rubros con saltos atípicos.",
                styles['BulletCustom'],
            ))

    # ── Análisis del mes: igual criterio que los reportes por área -- el
    # rubro que más subió en % + hasta 3 rubros atípicos adicionales por
    # materialidad (USD), sin repetir el mismo dos veces. ──
    atipicos = sorted(
        (r for r in rubros if r.get('esAtipico')),
        key=lambda r: abs(r['actual'] - r['anterior']),
        reverse=True,
    )[:3]
    if rubros_suben or atipicos:
        with keep_together():
            section_title(f"ANÁLISIS DEL MES · {mes_label.upper()}")
            bullets = []
            ya_mencionado = set()
            if rubros_suben:
                top = rubros_suben[0]
                signo = '+' if top['deltaPct'] >= 0 else ''
                bullet = f"{top['nombre']}, el rubro que más subió: {signo}{top['deltaPct']:.1f}% ({num(top['anterior'])} → {num(top['actual'])})."
                bullet += nota_historico(top)
                bullets.append(bullet)
                ya_mencionado.add(top['nombre'])
            for item in atipicos:
                if item['nombre'] in ya_mencionado:
                    continue
                ya_mencionado.add(item['nombre'])
                signo = '+' if item['deltaPct'] >= 0 else ''
                bullets.append(
                    f"{item['nombre']}: {signo}{item['deltaPct']:.1f}% ({num(item['anterior'])} → {num(item['actual'])})."
                    f"{nota_historico(item)}"
                )
            for b in bullets:
                story.append(Paragraph(f"•  {b}", styles['BulletCustom']))
                story.append(Spacer(1, 4))

    # ── Evolución últimos meses, en gráfico ──
    if len(trend) > 1:
        with keep_together():
            section_title("EVOLUCIÓN ÚLTIMOS MESES")
            meses_trend = [m['mes'][:3] for m in trend]
            series = [
                ("Facturación", AZUL, [m['ingresos'] for m in trend]),
                ("Gastos", BORDEAUX, [m['egresos'] for m in trend]),
                ("Resultado", VERDE, [m['resultado'] for m in trend]),
            ]
            trend_chart(meses_trend, series)

    # ── Top rubros que más subieron ──
    if rubros_suben:
        with keep_together():
            section_title("TOP RUBROS QUE MÁS SUBIERON")
            mes_ant_label = anterior['mes'] if anterior else ''
            mes_act_label = actual['mes']
            rows = [[r['nombre'], num(r['anterior']), num(r['actual']), var_cell(r['deltaPct']), historico_cell(r)] for r in rubros_suben]
            data_table(["Rubro", mes_ant_label, mes_act_label, "Variación", "vs. Histórico"], rows,
                       [CONTENT_W - 24 * mm - 24 * mm - 28 * mm - 44 * mm, 24 * mm, 24 * mm, 28 * mm, 44 * mm], var_colidx=3)

    # ── Fijos vs. Variables -- en vez de Unit Economics (Capital N no tiene
    # datos propios de comitentes/empleados): mismo desglose que la pestaña
    # "Análisis Capital N" del dashboard (Alquiler/Sueldos y CS/Contabilidad/
    # MTI = fijos, el resto = variables), pero con el filtro correcto que
    # excluye las filas "Aranceles ..." (ver nota en extract_data.js). ──
    fv_actual = fv_trend[-1] if fv_trend else {'fijos': 0, 'variables': 0}
    ingresos_actual = actual['ingresos']
    sueldos_actual = conceptos_actual.get('Sueldos y CS', 0)
    margen_pct = (actual['resultado'] / ingresos_actual * 100) if ingresos_actual else 0
    fijos_pct = (fv_actual['fijos'] / ingresos_actual * 100) if ingresos_actual else 0
    sueldos_pct = (sueldos_actual / ingresos_actual * 100) if ingresos_actual else 0
    with keep_together():
        section_title("FIJOS VS. VARIABLES")
        ratios = Table(
            [[ratio_card("Margen neto", f"{margen_pct:.1f}%"),
              ratio_card("Fijos / Fact.", f"{fijos_pct:.1f}%"),
              ratio_card("Sueldos / Fact.", f"{sueldos_pct:.1f}%")]],
            colWidths=[CONTENT_W / 3] * 3,
        )
        ratios.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(ratios)
        story.append(Spacer(1, 10))
        variables_pct = (fv_actual['variables'] / ingresos_actual * 100) if ingresos_actual else 0
        rows = [
            ["Fijos", usd(fv_actual['fijos']), f"{fijos_pct:.1f}%"],
            ["Variables", usd(fv_actual['variables']), f"{variables_pct:.1f}%"],
        ]
        plain_table(["Concepto", actual['mes'], "% sobre Facturación"], rows,
                    [CONTENT_W - 50 * mm - 50 * mm, 50 * mm, 50 * mm])
        story.append(Paragraph(
            "Fijos: Alquiler, Sueldos y CS, Contabilidad, MTI. Variables: el resto de los conceptos de gasto "
            "(no incluye el desglose de Facturación Bruta por bróker).",
            styles['NotaChica'],
        ))

    # ── Evolución Fijos vs. Variables ──
    if len(fv_trend) > 1:
        with keep_together():
            section_title("EVOLUCIÓN FIJOS VS. VARIABLES")
            meses_fv = [m['mes'][:3] for m in fv_trend]
            series = [
                ("Fijos", FIJOS_COLOR, [m['fijos'] for m in fv_trend]),
                ("Variables", VARIABLES_COLOR, [m['variables'] for m in fv_trend]),
            ]
            trend_chart(meses_fv, series)

    doc = SimpleDocTemplate(
        out_path, pagesize=(PAGE_W, PAGE_H),
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=HEADER_H + 6 * mm, bottomMargin=16 * mm,
        title=f"Reporte Mensual NEIX · Capital N · {mes_label}", author="NEIX",
    )
    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='real_data.json')
    ap.add_argument('--out', default='reporte_capital_n.pdf')
    ap.add_argument('--mes-label', default=None, help='Ej. "Agosto 2026" -- si no se pasa, se arma de mesActual + --anio')
    ap.add_argument('--anio', default=None)
    args = ap.parse_args()

    with open(args.data, encoding='utf-8') as f:
        data = json.load(f)

    mes_label = args.mes_label or (f"{data['mesActual']} {args.anio}" if args.anio else data['mesActual'])
    build_capn(data, mes_label, args.out)
    print(f"OK: {args.out}")
