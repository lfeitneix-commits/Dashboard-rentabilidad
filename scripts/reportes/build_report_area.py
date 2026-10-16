"""Arma el PDF de "Reporte Mensual por Área" a partir de real_data.json
(generado por extract_data.js) para una de las 4 áreas de staff (Mesa,
FAs, Banca Corporativa, Banca Privada).

Uso:
    python3 build_report_area.py --data real_data.json --area Mesa \
        --out reporte_mesa.pdf --mes-label "Junio 2026"

Es un reporte más chico que el de build_report.py (ese es el consolidado
de toda la empresa) -- acá va solo lo que ya está calculado por área en
real_data.json: KPIs, evolución de los últimos meses, los rubros que más
subieron en esa área puntual, y Unit Economics de esa área. Sin Anexo, sin
Análisis del mes automático ni ALERTAS -- esas features son del reporte
consolidado y dependen de datos que no están abiertos por área (el mayor
contable, los proveedores, etc.).
"""
import argparse
import json

from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.graphics import renderPDF

from build_report import (
    num, usd, usd2, AREA_COLOR, AREAS,
    GRAFITO, BORDEAUX, VERDE, MUTED, AZUL, CREMA, BORDER,
    VERDE_TINT, BORDEAUX_TINT, MUTED_TINT,
    PAGE_W, PAGE_H, HEADER_H, MARGIN, CONTENT_W, logo, logo_target_h,
)


def build_area(data, area, mes_label, out_path):
    story = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('KpiLabel', fontName='DMSans-Bold', fontSize=8, textColor=GRAFITO, alignment=TA_CENTER))
    styles.add(ParagraphStyle('KpiValue', fontName='DMMono-Medium', fontSize=16, leading=21, textColor=GRAFITO, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('KpiVar', fontName='DMMono-Medium', fontSize=10, alignment=TA_CENTER, spaceBefore=4))
    styles.add(ParagraphStyle('VarCell', fontName='DMMono-Medium', fontSize=9.5, alignment=TA_CENTER))
    styles.add(ParagraphStyle('NotaChica', fontName='DMSans', fontSize=8, textColor=MUTED, leftIndent=0))

    area_color = AREA_COLOR.get(area, BORDEAUX)

    def draw_header(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(GRAFITO)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(area_color)
        p = canvas.beginPath()
        p.moveTo(PAGE_W * 0.56, PAGE_H - HEADER_H)
        p.lineTo(PAGE_W * 0.66, PAGE_H - HEADER_H)
        p.lineTo(PAGE_W * 0.60, PAGE_H)
        p.lineTo(PAGE_W * 0.50, PAGE_H)
        p.close()
        canvas.drawPath(p, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor('#2A2A2A'))
        canvas.rect(0, PAGE_H - HEADER_H - 2.2 * mm, PAGE_W, 2.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(area_color)
        canvas.rect(0, PAGE_H - HEADER_H - 2.2 * mm, PAGE_W * 0.35, 2.2 * mm, stroke=0, fill=1)
        renderPDF.draw(logo, canvas, MARGIN, PAGE_H - HEADER_H + (HEADER_H - logo_target_h) / 2 + 1 * mm)
        canvas.setFillColor(colors.white)
        canvas.setFont('DMSans-Bold', 15)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - HEADER_H / 2 - 1, f"Reporte · {area}")
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
        # Mismo criterio que el reporte consolidado: % sobre el valor
        # ABSOLUTO de la base, para que el signo siempre coincida con si
        # mejoró o empeoró, sin importar si la base era negativa.
        if anterior == 0:
            return var_cell_delta(actual - anterior)
        return var_cell((actual - anterior) / abs(anterior) * 100)

    def section_title(title):
        story.append(Spacer(1, 16))
        t = Table([[Paragraph(title, ParagraphStyle('H2White', fontName='DMSans-Bold', fontSize=11.5, textColor=colors.white))]],
                   colWidths=[CONTENT_W], rowHeights=[8 * mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GRAFITO),
            ('LINEBEFORE', (0, 0), (0, 0), 3.5, area_color),
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
            ('LINEABOVE', (0, 0), (-1, 0), 3, area_color),
            ('TOPPADDING', (0, 0), (0, 0), 12),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 12),
            ('TOPPADDING', (0, 1), (0, 1), 1),
            ('TOPPADDING', (0, 2), (0, 2), 1),
        ]
        if sub_label:
            style_cmds.append(('TOPPADDING', (0, 3), (0, 3), 1))
        cell.setStyle(TableStyle(style_cmds))
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

    # ============================================================
    # Contenido
    # ============================================================
    trend = data.get('kpiTrendPorArea', {}).get(area) or []
    if not trend:
        raise ValueError(f'No hay datos de "{area}" en kpiTrendPorArea -- revisar real_data.json')
    actual = trend[-1]
    anterior = trend[-2] if len(trend) > 1 else None

    fact_var = pct_or_delta(actual['ingresos'], anterior['ingresos']) if anterior else (Paragraph('', styles['VarCell']), MUTED_TINT)
    gastos_var = pct_or_delta(actual['egresos'], anterior['egresos']) if anterior else (Paragraph('', styles['VarCell']), MUTED_TINT)
    result_var = pct_or_delta(actual['resultado'], anterior['resultado']) if anterior else (Paragraph('', styles['VarCell']), MUTED_TINT)
    kpi_sub = f"vs. {anterior['mes']}" if anterior else None

    kpis = Table(
        [[kpi_card("Facturación", usd(actual['ingresos']), fact_var, kpi_sub),
          kpi_card("Gastos totales", usd(actual['egresos']), gastos_var, kpi_sub),
          kpi_card("Resultado", usd(actual['resultado']), result_var, kpi_sub)]],
        colWidths=[CONTENT_W / 3] * 3,
    )
    kpis.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(Spacer(1, 4))
    story.append(kpis)

    # ── Evolución últimos meses (tabla, no gráfico -- este reporte es más
    # chico que el consolidado) ──
    if len(trend) > 1:
        section_title("EVOLUCIÓN ÚLTIMOS MESES")
        rows = [[m['mes'], usd(m['ingresos']), usd(m['egresos']), usd(m['resultado'])] for m in trend]
        plain_table(["Mes", "Facturación", "Gastos", "Resultado"], rows,
                    [CONTENT_W - 3 * 40 * mm, 40 * mm, 40 * mm, 40 * mm])

    # ── Top rubros que más subieron en esta área (ya calculado por
    # extract_data.js en rubrosVariacionPorArea -- solo gastos directos del
    # área, ver el comentario de esa variable ahí para el porqué). ──
    rubros_area = (data.get('rubrosVariacionPorArea') or {}).get(area) or []
    rubros_suben_area = [r for r in rubros_area if r['deltaPct'] is not None and r['deltaPct'] > 0]
    if rubros_suben_area:
        section_title("TOP RUBROS QUE MÁS SUBIERON")
        mes_ant_label = anterior['mes'] if anterior else ''
        mes_act_label = actual['mes']
        rows = [[r['nombre'], num(r['anterior']), num(r['actual']), var_cell(r['deltaPct'])] for r in rubros_suben_area]
        data_table(["Rubro", mes_ant_label, mes_act_label, "Variación"], rows,
                   [CONTENT_W - 28 * mm - 28 * mm - 55 * mm, 28 * mm, 28 * mm, 55 * mm], var_colidx=3)
        story.append(Paragraph(
            "Solo gastos directos del área (no incluye indirectos prorrateados entre las 4 áreas).",
            styles['NotaChica'],
        ))

    # ── Unit Economics de esta área (comitentes, empleados, facturación y
    # costo por comitente/empleado) -- mismos datos que el reporte
    # consolidado, filtrados a esta área. ──
    ue = data.get('unitEconomics')
    ue_area = next((a for a in (ue or {}).get('porArea', []) if a['area'] == area), None) if ue else None
    if ue_area:
        section_title("UNIT ECONOMICS")
        story.append(Paragraph(
            f"Comitentes: cuentas abiertas de {ue['mes']} (Matriz) &nbsp;·&nbsp; Empleados: Matriz (fijo) "
            f"&nbsp;·&nbsp; Facturación y Costo total: datos de {ue['mes']}",
            styles['NotaChica'],
        ))
        story.append(Spacer(1, 4))
        col_a, col_rest = 48 * mm, (CONTENT_W - 48 * mm) / 2
        comit, emp = ue_area['comitentes'], ue_area['empleados']
        rows = [[
            num(comit) if comit else '—',
            usd2(ue_area['facturacionMes'] / comit) if comit else '—',
            usd2(ue_area['gastoTotal'] / comit) if comit else '—',
        ]]
        plain_table(["Comitentes", "Facturación / comitente", "Costo total / comitente"], rows,
                    [col_a, col_rest, col_rest])
        rows = [[
            num(emp) if emp else '—',
            usd2(ue_area['facturacionMes'] / emp) if emp else '—',
            usd2(ue_area['gastoTotal'] / emp) if emp else '—',
        ]]
        plain_table(["Empleados", "Facturación / empleado", "Costo total / empleado"], rows,
                    [col_a, col_rest, col_rest])

    doc = SimpleDocTemplate(
        out_path, pagesize=(PAGE_W, PAGE_H),
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=HEADER_H + 6 * mm, bottomMargin=16 * mm,
    )
    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='real_data.json')
    ap.add_argument('--area', required=True, choices=AREAS)
    ap.add_argument('--out', default='reporte_area.pdf')
    ap.add_argument('--mes-label', default=None, help='Ej. "Agosto 2026" -- si no se pasa, se arma de mesActual + --anio')
    ap.add_argument('--anio', default=None)
    args = ap.parse_args()

    with open(args.data, encoding='utf-8') as f:
        data = json.load(f)

    mes_label = args.mes_label or (f"{data['mesActual']} {args.anio}" if args.anio else data['mesActual'])
    build_area(data, args.area, mes_label, args.out)
    print(f"OK: {args.out}")
