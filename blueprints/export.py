from flask import Blueprint, request, make_response, send_file
from flask_login import login_required, current_user
from models.database import get_db
from models.tariff import get_tariffs
from models.settings import get_setting
from utils import apply_user_filter
from models.audit import log_action
from io import StringIO, BytesIO
import csv
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from urllib.request import urlopen
import tempfile
import os

export_bp = Blueprint('export', __name__)

# ---------- Branding & user info ----------
def get_export_meta():
    """Return (company_name, logo_url, exported_by) from settings / current user."""
    company = get_setting('company_name') or 'Avaya CDR'
    logo = get_setting('company_logo_url') or ''
    exported_by = current_user.username if current_user.is_authenticated else 'Unknown'
    return company, logo, exported_by

# ---------- Shared helper to build WHERE clause ----------
def build_where_from_args(args, extra_conditions=None, extra_params=None):
    start_date = args.get('start_date', '')
    end_date = args.get('end_date', '')
    direction = args.get('direction', '')
    is_internal = args.get('is_internal', '')
    search = args.get('search', '')
    specific_date = args.get('date', '')
    month = args.get('month', '')
    year = args.get('year', '')
    extension = args.get('extension', '')
    call_id = args.get('call_id', '')
    external_number = args.get('external_number', '')

    conditions = extra_conditions[:] if extra_conditions else []
    params = extra_params[:] if extra_params else []

    if specific_date:
        start_fmt = specific_date.replace('-', '/')
        conditions.append("call_start >= ?")
        params.append(start_fmt + " 00:00:00")
        conditions.append("call_start <= ?")
        params.append(start_fmt + " 23:59:59")
    else:
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")

    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if is_internal:
        if is_internal == 'internal':
            conditions.append("is_internal = 1")
        elif is_internal == 'external':
            conditions.append("is_internal = 0")
    if search:
        conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    if month and year:
        conditions.append("CAST(strftime('%m', replace(call_start, '/', '-')) AS INTEGER) = ?")
        params.append(int(month))
        conditions.append("CAST(strftime('%Y', replace(call_start, '/', '-')) AS INTEGER) = ?")
        params.append(int(year))

    if extension:
        exts = [e.strip() for e in extension.split(',') if e.strip()]
        if exts:
            parts = []
            for ext in exts:
                parts.append("caller = ?")
                params.append(ext)
                parts.append("called_num = ?")
                params.append(ext)
            conditions.append("(" + " OR ".join(parts) + ")")

    if call_id:
        conditions.append("call_id = ?")
        params.append(int(call_id))

    if external_number:
        conditions.append("(caller = ? OR called_num = ?)")
        params.append(external_number)
        params.append(external_number)

    conditions, params = apply_user_filter(conditions, params)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


# ---------- Filter description ----------
def get_filter_description(args, extra_info=""):
    parts = []
    if args.get('start_date'):
        parts.append(f"From {args['start_date']}")
    if args.get('end_date'):
        parts.append(f"To {args['end_date']}")
    if args.get('date'):
        parts.append(f"Date: {args['date']}")
    if args.get('month') or args.get('year'):
        m = args.get('month', '')
        y = args.get('year', '')
        if m and y:
            parts.append(f"Month: {m}/{y}")
        elif y:
            parts.append(f"Year: {y}")
    if args.get('direction'):
        parts.append(f"Direction: {args['direction']}")
    if args.get('is_internal'):
        type_label = 'Internal' if args.get('is_internal') == 'internal' else 'External'
        parts.append(f"Type: {type_label}")
    if args.get('search'):
        parts.append(f"Search: \"{args['search']}\"")
    if args.get('extension'):
        parts.append(f"Extensions: {args['extension']}")
    if args.get('external_number'):
        parts.append(f"External: {args['external_number']}")
    if args.get('call_id'):
        parts.append(f"Call ID: {args['call_id']}")
    if args.get('start_date2'):
        parts.append(f"Period2 from {args['start_date2']}")
    if args.get('end_date2'):
        parts.append(f"Period2 to {args['end_date2']}")
    if extra_info:
        parts.append(extra_info)
    return "; ".join(parts) if parts else "None"


# ---------- Professional PDF builder ----------
def build_pdf(title, headers, rows, filter_text=""):
    company_name, logo_url, exported_by = get_export_meta()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.75 * inch
    )

    elements = []
    styles = getSampleStyleSheet()

    # ---- Branding block ----
    # Logo (if available)
    logo_image = None
    if logo_url:
        try:
            with urlopen(logo_url, timeout=5) as resp:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                tmp.write(resp.read())
                tmp.close()
                logo_image = Image(tmp.name, width=1.2 * inch, height=0.6 * inch)
                logo_image.hAlign = 'LEFT'
        except Exception:
            # If logo can't be fetched, silently ignore
            pass

    # Company name style
    company_style = ParagraphStyle(
        'CompanyStyle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    if logo_image:
        elements.append(logo_image)
    elements.append(Paragraph(company_name, company_style))
    elements.append(Paragraph("Call Analytics Report", subtitle_style))

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor('#1e293b'),
        alignment=TA_LEFT,
    )
    elements.append(Paragraph(title, title_style))

    # Export info line
    export_info_style = ParagraphStyle(
        'ExportInfo',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#475569'),
        spaceAfter=4,
    )
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    elements.append(Paragraph(f"Exported by: {exported_by} | Date: {now_str}", export_info_style))

    # Filter box
    if filter_text:
        filter_style = ParagraphStyle(
            'FilterBox',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#334155'),
            backColor=colors.HexColor('#f1f5f9'),
            borderPadding=6,
            borderRadius=6,
            spaceBefore=6,
            spaceAfter=12,
        )
        elements.append(Paragraph(f"Filters: {filter_text}", filter_style))

    # Data table
    if rows:
        if hasattr(rows[0], 'keys'):
            data = [list(r) for r in rows]
        else:
            data = [list(r) for r in rows]

        table_data = [headers] + data

        col_widths = []
        total_width = doc.width
        min_width = 0.5 * inch
        total_header_chars = sum(len(h) for h in headers) or 1
        for h in headers:
            w = max(min_width, (len(h) / total_header_chars) * total_width * 0.9)
            col_widths.append(w)

        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
    else:
        no_data_style = ParagraphStyle(
            'NoData', parent=styles['Normal'], fontSize=10,
            textColor=colors.HexColor('#64748b'), alignment=TA_CENTER
        )
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph("No data found for the selected filters.", no_data_style))

    # Page footer
    def add_page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawCentredString(doc.width / 2 + doc.leftMargin, 0.5 * inch,
                                 f"Page {canvas.getPageNumber()}")
        canvas.drawRightString(doc.width + doc.leftMargin, 0.5 * inch,
                               company_name)
        canvas.drawString(doc.leftMargin, 0.5 * inch,
                          f"Exported by {exported_by}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_page_footer, onLaterPages=add_page_footer)

    # Clean up temp logo file
    if logo_image and hasattr(logo_image, 'filename'):
        try:
            os.remove(logo_image.filename)
        except Exception:
            pass

    buffer.seek(0)
    return buffer


# ---------- CSV builder with header comments ----------
def write_csv(filename, headers, rows, filter_desc=None):
    company_name, _, exported_by = get_export_meta()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow([f"# Company: {company_name}"])
    cw.writerow([f"# Exported by: {exported_by}"])
    cw.writerow([f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
    if filter_desc:
        cw.writerow([f"# Filters: {filter_desc}"])
    cw.writerow(headers)
    cw.writerows(rows)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output


# ========== CALL DETAIL EXPORTS (main dashboard) ==========
@export_bp.route('/export/calls/csv')
@login_required
def export_calls_csv():
    where, params = build_where_from_args(request.args)
    conn = get_db()
    cursor = conn.cursor()
    query = f"""
        SELECT call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost
        FROM calls {where} ORDER BY id DESC
    """
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    headers = ['Call Start', 'Duration', 'Ring (sec)', 'Caller', 'Direction',
               'Called Number', 'Internal?', 'Party1 Name', 'Party2 Name', 'Hold (sec)', 'Cost ($)']
    output_rows = []
    for row in rows:
        row_list = list(row)
        row_list[6] = 'Yes' if row[6] else 'No'
        output_rows.append(row_list)

    filter_desc = get_filter_description(request.args)
    log_action(current_user.id, "Exported call details as CSV")
    return write_csv('call_details.csv', headers, output_rows, filter_desc)


@export_bp.route('/export/calls/pdf')
@login_required
def export_calls_pdf():
    where, params = build_where_from_args(request.args)
    conn = get_db()
    cursor = conn.cursor()
    query = f"""SELECT call_start, duration_raw, ring_time, caller, direction,
                called_num, is_internal, party1_name, party2_name, hold_time, cost
                FROM calls {where} ORDER BY id DESC"""
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    data = []
    for row in rows:
        row_list = list(row)
        row_list[6] = 'Yes' if row[6] else 'No'
        data.append(row_list)

    headers = ['Call Start', 'Duration', 'Ring (s)', 'Caller', 'Dir',
               'Called Num', 'Internal?', 'Party1', 'Party2', 'Hold (s)', 'Cost']
    filter_desc = get_filter_description(request.args)
    buffer = build_pdf('Call Details Report', headers, data, filter_desc)
    log_action(current_user.id, "Exported call details as PDF")
    return send_file(buffer, as_attachment=True, download_name="call_details.pdf", mimetype='application/pdf')


# ========== REPORT EXPORTS (CSV & PDF) ==========
@export_bp.route('/report/<report_type>/export/csv')
@login_required
def export_csv(report_type):
    args = request.args
    conn = get_db()
    cursor = conn.cursor()

    if report_type == 'daily_summary':
        where, params = build_where_from_args(args)
        query = f"""SELECT DATE(replace(call_start, '/', '-')) as date, COUNT(*), SUM(duration_seconds),
                         SUM(ring_time), SUM(hold_time), SUM(cost)
                  FROM calls {where} GROUP BY date ORDER BY date DESC LIMIT 30"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring Time (sec)', 'Hold Time (sec)', 'Cost ($)']

    elif report_type == 'top_callers':
        where, params = build_where_from_args(args)
        query = f"""SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY caller ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Caller', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']

    elif report_type == 'top_called':
        where, params = build_where_from_args(args)
        query = f"""SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY called_num ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Called Number', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']

    elif report_type == 'hourly_distribution':
        where, params = build_where_from_args(args)
        query = f"""SELECT strftime('%H', replace(call_start, '/', '-')) AS hour, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY hour ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Hour', 'Total Calls', 'Total Talk Time (sec)']

    elif report_type == 'cost_by_prefix':
        where, params = build_where_from_args(args, extra_conditions=["is_internal = 0"])
        cursor.execute(f"SELECT called_num, duration_seconds FROM calls {where}", params)
        call_rows = cursor.fetchall()
        tariffs = get_tariffs()
        prefix_costs = {}
        for called_num, dur_sec in call_rows:
            matched_prefix = 'local'
            max_len = 0
            for prefix, rate in tariffs:
                if called_num.startswith(prefix) and len(prefix) > max_len:
                    matched_prefix = prefix
                    max_len = len(prefix)
            minutes = dur_sec / 60.0
            cost = minutes * (dict(tariffs).get(matched_prefix, 1.0))
            prefix_costs[matched_prefix] = prefix_costs.get(matched_prefix, 0) + cost
        rows = [(prefix, round(cost, 2)) for prefix, cost in prefix_costs.items()]
        headers = ['Prefix', 'Total Cost ($)']
        filter_desc = get_filter_description(args)
        return write_csv(f"{report_type}_report.csv", headers, rows, filter_desc)

    elif report_type == 'extension_usage':
        where, params = build_where_from_args(args)
        params = params + params
        query = f"""
            SELECT extension, SUM(calls_made), SUM(calls_received),
                   SUM(talk_time_made), SUM(talk_time_received),
                   SUM(cost_made), SUM(cost_received)
            FROM (
                SELECT caller AS extension, COUNT(*) AS calls_made, 0 AS calls_received,
                       SUM(duration_seconds) AS talk_time_made, 0 AS talk_time_received,
                       SUM(cost) AS cost_made, 0 AS cost_received
                FROM calls {where} GROUP BY caller
                UNION ALL
                SELECT called_num AS extension, 0 AS calls_made, COUNT(*) AS calls_received,
                       0 AS talk_time_made, SUM(duration_seconds) AS talk_time_received,
                       0 AS cost_made, SUM(cost) AS cost_received
                FROM calls {where} GROUP BY called_num
            ) combined GROUP BY extension ORDER BY (SUM(calls_made) + SUM(calls_received)) DESC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Extension', 'Calls Made', 'Calls Received', 'Talk Time Made (sec)', 'Talk Time Received (sec)', 'Cost Made ($)', 'Cost Received ($)']

    elif report_type == 'ring_time':
        where, params = build_where_from_args(args)
        query = f"""SELECT call_start, duration_raw, ring_time, caller, direction, called_num, party1_name
                  FROM calls {where} ORDER BY ring_time DESC LIMIT 50"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Duration', 'Ring (sec)', 'Caller', 'Direction', 'Called Number', 'Party1 Name']

    elif report_type == 'abandoned':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""SELECT call_start, ring_time, caller, direction, called_num, party1_name, party2_name
                  FROM calls {where} ORDER BY call_start DESC LIMIT 100"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Ring Time (sec)', 'Caller', 'Direction', 'Called Number', 'From', 'To']

    elif report_type == 'heatmap':
        where, params = build_where_from_args(args)
        query = f"""SELECT strftime('%w', replace(call_start, '/', '-')) as dow,
                         strftime('%H', replace(call_start, '/', '-')) as hour,
                         COUNT(*) as cnt
                  FROM calls {where} GROUP BY dow, hour ORDER BY dow, hour"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Day of Week', 'Hour', 'Call Count']

    elif report_type == 'trunk_usage':
        where, params = build_where_from_args(args)
        if where: where += " AND party2_device LIKE 'T%'"
        else: where = "WHERE party2_device LIKE 'T%'"
        query = f"""SELECT party2_device AS trunk, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY trunk ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Trunk', 'Call Count', 'Total Talk Time (sec)']

    elif report_type == 'period_comparison':
        where1, params1 = build_where_from_args(args)
        cursor.execute(f"SELECT COUNT(*), SUM(duration_seconds), SUM(cost) FROM calls {where1}", params1)
        res1 = cursor.fetchone()
        conditions2 = []
        params2 = []
        start_date2 = args.get('start_date2', '')
        end_date2 = args.get('end_date2', '')
        if start_date2:
            conditions2.append("call_start >= ?")
            params2.append(start_date2.replace('-', '/') + " 00:00:00")
        if end_date2:
            conditions2.append("call_start <= ?")
            params2.append(end_date2.replace('-', '/') + " 23:59:59")
        if args.get('direction'):
            conditions2.append("direction = ?"); params2.append(args['direction'])
        if args.get('is_internal'):
            if args['is_internal'] == 'internal': conditions2.append("is_internal = 1")
            elif args['is_internal'] == 'external': conditions2.append("is_internal = 0")
        if args.get('search'):
            conditions2.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{args['search']}%"
            params2.extend([like, like, like])
        conditions2, params2 = apply_user_filter(conditions2, params2)
        where2 = "WHERE " + " AND ".join(conditions2) if conditions2 else ""
        cursor.execute(f"SELECT COUNT(*), SUM(duration_seconds), SUM(cost) FROM calls {where2}", params2)
        res2 = cursor.fetchone()
        rows = [('Metric', 'Period 1', 'Period 2'),
                ('Total Calls', res1[0] or 0, res2[0] or 0),
                ('Total Talk Time (sec)', res1[1] or 0, res2[1] or 0),
                ('Total Cost ($)', round(res1[2] or 0, 2), round(res2[2] or 0, 2))]
        headers = ['Metric', 'Period 1', 'Period 2']
        filter_desc = get_filter_description(args)
        return write_csv(f"{report_type}_report.csv", headers, rows, filter_desc)

    elif report_type == 'detail_call_report':
        where, params = build_where_from_args(args)
        query = f"SELECT * FROM calls {where} ORDER BY id DESC LIMIT 5000"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Start Time', 'Duration', 'Ring (sec)', 'Caller', 'Direction',
                   'Called', 'Dialed', 'Account', 'Internal', 'Call ID',
                   'Cont', 'P1 Device', 'P1 Name', 'P2 Device', 'P2 Name',
                   'Hold (sec)', 'Park (sec)', 'Auth Valid', 'Auth Code', 'Cost']
        output_rows = []
        for row in rows:
            r = list(row) + [''] * 15
            output_rows.append((
                r[1], r[2], r[4], r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                r[17], r[18], r[19], r[20], r[21]
            ))
        filter_desc = get_filter_description(args)
        return write_csv('detail_call_report.csv', headers, output_rows, filter_desc)

    # ======================== NEW REPORTS ========================
    elif report_type == 'call_journey':
        where, params = build_where_from_args(args)
        query = f"SELECT * FROM calls {where} ORDER BY id ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['ID', 'Start Time', 'Duration', 'Ring (s)', 'Caller', 'Direction',
                   'Called', 'Dialed', 'Account', 'Internal', 'Call ID', 'Cont',
                   'P1 Device', 'P1 Name', 'P2 Device', 'P2 Name',
                   'Hold (s)', 'Park (s)', 'Auth Valid', 'Auth Code', 'Cost']
        output_rows = []
        for r in rows:
            r = list(r) + [''] * 15
            output_rows.append((
                r[0], r[1], r[2], r[4], r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                r[17], r[18], r[19], r[20], r[21]
            ))
        filter_desc = get_filter_description(args)
        return write_csv('call_journey.csv', headers, output_rows, filter_desc)

    elif report_type == 'duration_distribution':
        where, params = build_where_from_args(args)
        query = f"""
            SELECT
                CASE
                    WHEN duration_seconds BETWEEN 0 AND 10 THEN '0-10s'
                    WHEN duration_seconds BETWEEN 11 AND 30 THEN '10-30s'
                    WHEN duration_seconds BETWEEN 31 AND 60 THEN '30-60s'
                    WHEN duration_seconds BETWEEN 61 AND 120 THEN '1-2min'
                    WHEN duration_seconds BETWEEN 121 AND 300 THEN '2-5min'
                    WHEN duration_seconds BETWEEN 301 AND 600 THEN '5-10min'
                    WHEN duration_seconds BETWEEN 601 AND 1800 THEN '10-30min'
                    ELSE '30min+'
                END AS bucket,
                COUNT(*) as count
            FROM calls {where}
            GROUP BY bucket
            ORDER BY MIN(duration_seconds)
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Duration Bucket', 'Call Count']

    elif report_type == 'abandoned_trend':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""
            SELECT DATE(replace(call_start, '/', '-')) as date, COUNT(*) as count
            FROM calls {where}
            GROUP BY date
            ORDER BY date DESC
            LIMIT 30
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Abandoned Calls']

    elif report_type == 'caller_profile':
        where, params = build_where_from_args(args)
        query = f"SELECT call_start, duration_raw, caller, direction, called_num, party1_name, party2_name FROM calls {where} ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Start Time', 'Duration', 'Caller', 'Direction', 'Called', 'Party1 Name', 'Party2 Name']

    elif report_type == 'extension_scorecard':
        where, params = build_where_from_args(args)
        params = params + params
        query = f"""
            SELECT extension, SUM(calls_made), SUM(calls_received),
                   SUM(talk_time_made), SUM(talk_time_received),
                   SUM(cost_made), SUM(cost_received),
                   (SUM(calls_made) + SUM(calls_received) + SUM(talk_time_made)/60) AS score
            FROM (
                SELECT caller AS extension, COUNT(*) AS calls_made, 0 AS calls_received,
                       SUM(duration_seconds) AS talk_time_made, 0 AS talk_time_received,
                       SUM(cost) AS cost_made, 0 AS cost_received
                FROM calls {where} GROUP BY caller
                UNION ALL
                SELECT called_num AS extension, 0 AS calls_made, COUNT(*) AS calls_received,
                       0 AS talk_time_made, SUM(duration_seconds) AS talk_time_received,
                       0 AS cost_made, SUM(cost) AS cost_received
                FROM calls {where} GROUP BY called_num
            ) combined GROUP BY extension ORDER BY score DESC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Extension', 'Calls Made', 'Calls Received', 'Talk Made (s)', 'Talk Received (s)', 'Cost Made ($)', 'Cost Received ($)', 'Activity Score']

    elif report_type == 'trunk_peak_utilisation':
        where, params = build_where_from_args(args)
        inner_where = where
        if inner_where:
            inner_where += " AND party2_device LIKE 'T%'"
        else:
            inner_where = "WHERE party2_device LIKE 'T%'"
        query = f"""
            SELECT trunk, MAX(calls) as peak_calls, hour
            FROM (
                SELECT party2_device AS trunk,
                       strftime('%H', replace(call_start, '/', '-')) AS hour,
                       COUNT(*) AS calls
                FROM calls {inner_where}
                GROUP BY trunk, hour
            )
            GROUP BY trunk
            ORDER BY peak_calls DESC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Trunk', 'Peak Calls', 'Peak Hour']

    elif report_type == 'outcome_summary':
        where, params = build_where_from_args(args)
        query = f"""
            SELECT
                CASE
                    WHEN duration_seconds > 0 THEN 'Answered'
                    WHEN duration_seconds = 0 AND direction = 'Inbound' AND ring_time > 0 THEN 'Abandoned'
                    WHEN party2_device LIKE 'V%' THEN 'Voicemail'
                    ELSE 'Other'
                END AS outcome,
                COUNT(*) AS count
            FROM calls {where}
            GROUP BY outcome
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Outcome', 'Call Count']

    else:
        return "Invalid report type", 400

    # Generic CSV fallback
    filter_desc = get_filter_description(args)
    if hasattr(rows[0], 'keys'):
        rows_list = [list(r) for r in rows]
    else:
        rows_list = [list(r) for r in rows]
    return write_csv(f"{report_type}_report.csv", headers, rows_list, filter_desc)


@export_bp.route('/report/<report_type>/export/pdf')
@login_required
def export_pdf(report_type):
    args = request.args
    conn = get_db()
    cursor = conn.cursor()

    filter_desc = get_filter_description(args)

    if report_type == 'daily_summary':
        where, params = build_where_from_args(args)
        query = f"""SELECT DATE(replace(call_start, '/', '-')) as date, COUNT(*), SUM(duration_seconds),
                         SUM(ring_time), SUM(hold_time), SUM(cost)
                  FROM calls {where} GROUP BY date ORDER BY date DESC LIMIT 30"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring (sec)', 'Hold (sec)', 'Cost ($)']

    elif report_type == 'top_callers':
        where, params = build_where_from_args(args)
        query = f"""SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY caller ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Caller', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']

    elif report_type == 'top_called':
        where, params = build_where_from_args(args)
        query = f"""SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY called_num ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Called Number', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']

    elif report_type == 'hourly_distribution':
        where, params = build_where_from_args(args)
        query = f"""SELECT strftime('%H', replace(call_start, '/', '-')) AS hour, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY hour ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Hour', 'Total Calls', 'Total Talk Time (sec)']

    elif report_type == 'cost_by_prefix':
        where, params = build_where_from_args(args, extra_conditions=["is_internal = 0"])
        cursor.execute(f"SELECT called_num, duration_seconds FROM calls {where}", params)
        call_rows = cursor.fetchall()
        tariffs = get_tariffs()
        prefix_costs = {}
        for called_num, dur_sec in call_rows:
            matched_prefix = 'local'; max_len = 0
            for prefix, rate in tariffs:
                if called_num.startswith(prefix) and len(prefix) > max_len:
                    matched_prefix = prefix; max_len = len(prefix)
            minutes = dur_sec / 60.0
            cost = minutes * (dict(tariffs).get(matched_prefix, 1.0))
            prefix_costs[matched_prefix] = prefix_costs.get(matched_prefix, 0) + cost
        rows = [(prefix, f"${round(cost,2)}") for prefix, cost in prefix_costs.items()]
        headers = ['Prefix', 'Total Cost']
        buffer = build_pdf('Cost by Tariff Prefix', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'extension_usage':
        where, params = build_where_from_args(args)
        params = params + params
        query = f"""
            SELECT extension, SUM(calls_made), SUM(calls_received),
                   SUM(talk_time_made), SUM(talk_time_received),
                   SUM(cost_made), SUM(cost_received)
            FROM (
                SELECT caller AS extension, COUNT(*) AS calls_made, 0 AS calls_received,
                       SUM(duration_seconds) AS talk_time_made, 0 AS talk_time_received,
                       SUM(cost) AS cost_made, 0 AS cost_received
                FROM calls {where} GROUP BY caller
                UNION ALL
                SELECT called_num AS extension, 0 AS calls_made, COUNT(*) AS calls_received,
                       0 AS talk_time_made, SUM(duration_seconds) AS talk_time_received,
                       0 AS cost_made, SUM(cost) AS cost_received
                FROM calls {where} GROUP BY called_num
            ) combined GROUP BY extension ORDER BY (SUM(calls_made) + SUM(calls_received)) DESC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Extension', 'Calls Made', 'Calls Received', 'Talk Made (sec)', 'Talk Received (sec)', 'Cost Made ($)', 'Cost Received ($)']

    elif report_type == 'ring_time':
        where, params = build_where_from_args(args)
        query = f"""SELECT call_start, duration_raw, ring_time, caller, direction, called_num, party1_name
                  FROM calls {where} ORDER BY ring_time DESC LIMIT 50"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Duration', 'Ring (sec)', 'Caller', 'Direction', 'Called Number', 'Party1 Name']

    elif report_type == 'abandoned':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""SELECT call_start, ring_time, caller, direction, called_num, party1_name, party2_name
                  FROM calls {where} ORDER BY call_start DESC LIMIT 100"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Ring Time (sec)', 'Caller', 'Direction', 'Called Number', 'From', 'To']

    elif report_type == 'heatmap':
        where, params = build_where_from_args(args)
        query = f"""SELECT strftime('%w', replace(call_start, '/', '-')) as dow,
                         strftime('%H', replace(call_start, '/', '-')) as hour,
                         COUNT(*) as cnt
                  FROM calls {where} GROUP BY dow, hour ORDER BY dow, hour"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Day of Week', 'Hour', 'Call Count']

    elif report_type == 'trunk_usage':
        where, params = build_where_from_args(args)
        if where: where += " AND party2_device LIKE 'T%'"
        else: where = "WHERE party2_device LIKE 'T%'"
        query = f"""SELECT party2_device AS trunk, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY trunk ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Trunk', 'Call Count', 'Total Talk Time (sec)']

    elif report_type == 'period_comparison':
        where1, params1 = build_where_from_args(args)
        cursor.execute(f"SELECT COUNT(*), SUM(duration_seconds), SUM(cost) FROM calls {where1}", params1)
        res1 = cursor.fetchone()
        conditions2, params2 = [], []
        start_date2 = args.get('start_date2', '')
        end_date2 = args.get('end_date2', '')
        if start_date2:
            conditions2.append("call_start >= ?")
            params2.append(start_date2.replace('-', '/') + " 00:00:00")
        if end_date2:
            conditions2.append("call_start <= ?")
            params2.append(end_date2.replace('-', '/') + " 23:59:59")
        if args.get('direction'):
            conditions2.append("direction = ?"); params2.append(args['direction'])
        if args.get('is_internal'):
            if args['is_internal'] == 'internal': conditions2.append("is_internal = 1")
            elif args['is_internal'] == 'external': conditions2.append("is_internal = 0")
        if args.get('search'):
            conditions2.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{args['search']}%"
            params2.extend([like, like, like])
        conditions2, params2 = apply_user_filter(conditions2, params2)
        where2 = "WHERE " + " AND ".join(conditions2) if conditions2 else ""
        cursor.execute(f"SELECT COUNT(*), SUM(duration_seconds), SUM(cost) FROM calls {where2}", params2)
        res2 = cursor.fetchone()
        rows = [('Metric', 'Period 1', 'Period 2'),
                ('Total Calls', res1[0] or 0, res2[0] or 0),
                ('Total Talk Time (sec)', res1[1] or 0, res2[1] or 0),
                ('Total Cost ($)', round(res1[2] or 0, 2), round(res2[2] or 0, 2))]
        headers = ['Metric', 'Period 1', 'Period 2']
        buffer = build_pdf('Period Comparison', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'detail_call_report':
        where, params = build_where_from_args(args)
        query = f"SELECT * FROM calls {where} ORDER BY id DESC LIMIT 5000"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Start Time', 'Duration', 'Ring (s)', 'Caller', 'Dir',
                   'Called', 'Dialed', 'Account', 'Internal', 'Call ID',
                   'Cont', 'P1 Dev', 'P1 Name', 'P2 Dev', 'P2 Name',
                   'Hold (s)', 'Park (s)', 'Auth Valid', 'Auth Code', 'Cost']
        data = []
        for r in rows:
            r = list(r) + [''] * 15
            data.append([
                r[1], r[2], r[4], r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                r[17], r[18], r[19], r[20], r[21]
            ])
        buffer = build_pdf('Detail Call Records Report', headers, data, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    # ======================== NEW REPORTS (PDF) ========================
    elif report_type == 'call_journey':
        where, params = build_where_from_args(args)
        query = f"SELECT * FROM calls {where} ORDER BY id ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['ID', 'Start Time', 'Duration', 'Ring (s)', 'Caller', 'Direction',
                   'Called', 'Dialed', 'Account', 'Internal', 'Call ID', 'Cont',
                   'P1 Dev', 'P1 Name', 'P2 Dev', 'P2 Name',
                   'Hold (s)', 'Park (s)', 'Auth Valid', 'Auth Code', 'Cost']
        data = []
        for r in rows:
            r = list(r) + [''] * 15
            data.append([
                r[0], r[1], r[2], r[4], r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                r[17], r[18], r[19], r[20], r[21]
            ])
        buffer = build_pdf('Call Journey', headers, data, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'duration_distribution':
        where, params = build_where_from_args(args)
        query = f"""
            SELECT
                CASE
                    WHEN duration_seconds BETWEEN 0 AND 10 THEN '0-10s'
                    WHEN duration_seconds BETWEEN 11 AND 30 THEN '10-30s'
                    WHEN duration_seconds BETWEEN 31 AND 60 THEN '30-60s'
                    WHEN duration_seconds BETWEEN 61 AND 120 THEN '1-2min'
                    WHEN duration_seconds BETWEEN 121 AND 300 THEN '2-5min'
                    WHEN duration_seconds BETWEEN 301 AND 600 THEN '5-10min'
                    WHEN duration_seconds BETWEEN 601 AND 1800 THEN '10-30min'
                    ELSE '30min+'
                END AS bucket,
                COUNT(*) as count
            FROM calls {where}
            GROUP BY bucket
            ORDER BY MIN(duration_seconds)
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Duration Bucket', 'Call Count']
        buffer = build_pdf('Duration Distribution', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'abandoned_trend':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""
            SELECT DATE(replace(call_start, '/', '-')) as date, COUNT(*) as count
            FROM calls {where}
            GROUP BY date
            ORDER BY date DESC
            LIMIT 30
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Abandoned Calls']
        buffer = build_pdf('Abandoned Trend', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'caller_profile':
        where, params = build_where_from_args(args)
        query = f"SELECT call_start, duration_raw, caller, direction, called_num, party1_name, party2_name FROM calls {where} ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Start Time', 'Duration', 'Caller', 'Direction', 'Called', 'Party1 Name', 'Party2 Name']
        buffer = build_pdf('Caller Profile', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'extension_scorecard':
        where, params = build_where_from_args(args)
        params = params + params
        query = f"""
            SELECT extension, SUM(calls_made), SUM(calls_received),
                   SUM(talk_time_made), SUM(talk_time_received),
                   SUM(cost_made), SUM(cost_received),
                   (SUM(calls_made) + SUM(calls_received) + SUM(talk_time_made)/60) AS score
            FROM (
                SELECT caller AS extension, COUNT(*) AS calls_made, 0 AS calls_received,
                       SUM(duration_seconds) AS talk_time_made, 0 AS talk_time_received,
                       SUM(cost) AS cost_made, 0 AS cost_received
                FROM calls {where} GROUP BY caller
                UNION ALL
                SELECT called_num AS extension, 0 AS calls_made, COUNT(*) AS calls_received,
                       0 AS talk_time_made, SUM(duration_seconds) AS talk_time_received,
                       0 AS cost_made, SUM(cost) AS cost_received
                FROM calls {where} GROUP BY called_num
            ) combined GROUP BY extension ORDER BY score DESC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Extension', 'Calls Made', 'Calls Received', 'Talk Made (s)', 'Talk Received (s)', 'Cost Made ($)', 'Cost Received ($)', 'Activity Score']
        buffer = build_pdf('Extension Scorecard', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'trunk_peak_utilisation':
        where, params = build_where_from_args(args)
        inner_where = where
        if inner_where:
            inner_where += " AND party2_device LIKE 'T%'"
        else:
            inner_where = "WHERE party2_device LIKE 'T%'"
        query = f"""
            SELECT trunk, MAX(calls) as peak_calls, hour
            FROM (
                SELECT party2_device AS trunk,
                       strftime('%H', replace(call_start, '/', '-')) AS hour,
                       COUNT(*) AS calls
                FROM calls {inner_where}
                GROUP BY trunk, hour
            )
            GROUP BY trunk
            ORDER BY peak_calls DESC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Trunk', 'Peak Calls', 'Peak Hour']
        buffer = build_pdf('Trunk Peak Utilisation', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    elif report_type == 'outcome_summary':
        where, params = build_where_from_args(args)
        query = f"""
            SELECT
                CASE
                    WHEN duration_seconds > 0 THEN 'Answered'
                    WHEN duration_seconds = 0 AND direction = 'Inbound' AND ring_time > 0 THEN 'Abandoned'
                    WHEN party2_device LIKE 'V%' THEN 'Voicemail'
                    ELSE 'Other'
                END AS outcome,
                COUNT(*) AS count
            FROM calls {where}
            GROUP BY outcome
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Outcome', 'Call Count']
        buffer = build_pdf('Outcome Summary', headers, rows, filter_desc)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')


    else:
        return "Invalid report type", 400

    # Generic PDF fallback
    buffer = build_pdf(report_type.replace('_', ' ').title(), headers, rows, filter_desc)
    return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

# ---------- Internal report generator (no auth) ----------
def generate_report_internal(report_type, filters, format='pdf'):
    """
    Generate a report file as a BytesIO buffer WITHOUT requiring authentication.
    filters: dict like {'start_date':'2026-05-01', ...}
    """
    from flask import request
    # Store the original request arguments (if any) and replace with our filters
    # We'll temporarily overwrite request.args to mimic a real call.
    # This is safe because we are inside a background thread with its own request context.
    # We'll just use the existing build_where_from_args and build_pdf / write_csv helpers.
    # We need a where clause and params.
    # For each report type, we'll call the appropriate query from reports.py, but that's duplicated.
    # Instead, we can call the export endpoint's underlying logic using a test request context with login disabled.
    # Actually, we can call the export_pdf function directly after temporarily removing login_required.
    # That's hacky. Simpler: duplicate the minimal logic needed.
    # I'll implement a basic version that handles the common report types by re-using the build_pdf/write_csv helpers.
    pass