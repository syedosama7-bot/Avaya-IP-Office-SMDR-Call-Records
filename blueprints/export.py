from flask import Blueprint, request, make_response, send_file
from flask_login import login_required, current_user
from models.database import get_db
from models.tariff import get_tariffs
from utils import apply_user_filter
from models.audit import log_action
from io import StringIO, BytesIO
import csv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

export_bp = Blueprint('export', __name__)

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
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    for row in rows:
        row_list = list(row)
        row_list[6] = 'Yes' if row[6] else 'No'
        cw.writerow(row_list)

    log_action(current_user.id, "Exported call details as CSV")
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=call_details.csv"
    output.headers["Content-type"] = "text/csv"
    return output


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
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Avaya Call Details Report", styles['Heading1']))
    elements.append(Spacer(1, 0.2*inch))
    filter_text = f"Filters: {request.args.get('start_date','Any')} to {request.args.get('end_date','Any')}"
    elements.append(Paragraph(filter_text, styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    t = Table([headers] + data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTSIZE', (0,1), (-1,-1), 7),
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
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
        query = f"""SELECT DATE(call_start) as date, COUNT(*), SUM(duration_seconds),
                         SUM(ring_time), SUM(hold_time), SUM(cost)
                  FROM calls {where} GROUP BY DATE(call_start) ORDER BY date DESC LIMIT 30"""
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
        query = f"""SELECT strftime('%H', call_start) AS hour, COUNT(*), SUM(duration_seconds)
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
        si = StringIO(); cw = csv.writer(si)
        cw.writerow(headers); cw.writerows(rows)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.csv"
        output.headers["Content-type"] = "text/csv"
        return output

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
        si = StringIO(); cw = csv.writer(si)
        cw.writerow(headers); cw.writerows(rows)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.csv"
        output.headers["Content-type"] = "text/csv"
        return output

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
        si = StringIO(); cw = csv.writer(si)
        cw.writerow(headers); cw.writerows(output_rows)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=detail_call_report.csv"
        output.headers["Content-type"] = "text/csv"
        return output

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
        si = StringIO(); cw = csv.writer(si)
        cw.writerow(headers); cw.writerows(output_rows)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=call_journey.csv"
        output.headers["Content-type"] = "text/csv"
        return output

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
        # fall through to generic writer at the end

    elif report_type == 'abandoned_trend':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""
            SELECT DATE(call_start) as date, COUNT(*) as count
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
                       strftime('%H', call_start) AS hour,
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
        # fall through to the generic CSV writer

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

    # For all reports that reach here (generic CSV output)
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    if rows:
        if hasattr(rows[0], 'keys'):
            cw.writerows([list(r) for r in rows])
        else:
            cw.writerows(rows)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@export_bp.route('/report/<report_type>/export/pdf')
@login_required
def export_pdf(report_type):
    args = request.args
    conn = get_db()
    cursor = conn.cursor()

    def build_pdf(title, headers, rows):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()
        elements.append(Paragraph(title, styles['Heading1']))
        elements.append(Spacer(1, 0.2*inch))
        filter_text = f"Filters: {args.get('start_date','Any')} to {args.get('end_date','Any')}"
        elements.append(Paragraph(filter_text, styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))
        if rows:
            if hasattr(rows[0], 'keys'):
                data = [list(r) for r in rows]
            else:
                data = [list(r) for r in rows]
            table_data = [headers] + data
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 8),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('FONTSIZE', (0,1), (-1,-1), 7),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No data found for the selected filters.", styles['Normal']))
        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    if report_type == 'daily_summary':
        where, params = build_where_from_args(args)
        query = f"""SELECT DATE(call_start) as date, COUNT(*), SUM(duration_seconds),
                         SUM(ring_time), SUM(hold_time), SUM(cost)
                  FROM calls {where} GROUP BY DATE(call_start) ORDER BY date DESC LIMIT 30"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring (sec)', 'Hold (sec)', 'Cost ($)']
        return build_pdf('Daily Call Summary', headers, rows)

    elif report_type == 'top_callers':
        where, params = build_where_from_args(args)
        query = f"""SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY caller ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Caller', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
        return build_pdf('Top Callers', headers, rows)

    elif report_type == 'top_called':
        where, params = build_where_from_args(args)
        query = f"""SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY called_num ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Called Number', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
        return build_pdf('Top Called Numbers', headers, rows)

    elif report_type == 'hourly_distribution':
        where, params = build_where_from_args(args)
        query = f"""SELECT strftime('%H', call_start) AS hour, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY hour ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Hour', 'Total Calls', 'Total Talk Time (sec)']
        return build_pdf('Busiest Hour Distribution', headers, rows)

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
        return build_pdf('Cost by Tariff Prefix', headers, rows)

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
        return build_pdf('Extension Usage Summary', headers, rows)

    elif report_type == 'ring_time':
        where, params = build_where_from_args(args)
        query = f"""SELECT call_start, duration_raw, ring_time, caller, direction, called_num, party1_name
                  FROM calls {where} ORDER BY ring_time DESC LIMIT 50"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Duration', 'Ring (sec)', 'Caller', 'Direction', 'Called Number', 'Party1 Name']
        return build_pdf('Longest Ring Times', headers, rows)

    elif report_type == 'abandoned':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""SELECT call_start, ring_time, caller, direction, called_num, party1_name, party2_name
                  FROM calls {where} ORDER BY call_start DESC LIMIT 100"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Ring Time (sec)', 'Caller', 'Direction', 'Called Number', 'From', 'To']
        return build_pdf('Abandoned / Short Calls', headers, rows)

    elif report_type == 'heatmap':
        where, params = build_where_from_args(args)
        query = f"""SELECT strftime('%w', replace(call_start, '/', '-')) as dow,
                         strftime('%H', replace(call_start, '/', '-')) as hour,
                         COUNT(*) as cnt
                  FROM calls {where} GROUP BY dow, hour ORDER BY dow, hour"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Day of Week', 'Hour', 'Call Count']
        return build_pdf('Call Heatmap (Day of Week vs Hour)', headers, rows)

    elif report_type == 'trunk_usage':
        where, params = build_where_from_args(args)
        if where: where += " AND party2_device LIKE 'T%'"
        else: where = "WHERE party2_device LIKE 'T%'"
        query = f"""SELECT party2_device AS trunk, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY trunk ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Trunk', 'Call Count', 'Total Talk Time (sec)']
        return build_pdf('Trunk Usage', headers, rows)

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
        return build_pdf('Period Comparison', headers, rows)

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
        return build_pdf('Detail Call Records Report', headers, data)

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
        return build_pdf('Call Journey', headers, data)

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
        return build_pdf('Duration Distribution', headers, rows)

    elif report_type == 'abandoned_trend':
        where, params = build_where_from_args(args, extra_conditions=["duration_seconds = 0"])
        query = f"""
            SELECT DATE(call_start) as date, COUNT(*) as count
            FROM calls {where}
            GROUP BY date
            ORDER BY date DESC
            LIMIT 30
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Abandoned Calls']
        return build_pdf('Abandoned Trend', headers, rows)

    elif report_type == 'caller_profile':
        where, params = build_where_from_args(args)
        query = f"SELECT call_start, duration_raw, caller, direction, called_num, party1_name, party2_name FROM calls {where} ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Start Time', 'Duration', 'Caller', 'Direction', 'Called', 'Party1 Name', 'Party2 Name']
        return build_pdf('Caller Profile', headers, rows)

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
        return build_pdf('Extension Scorecard', headers, rows)

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
                       strftime('%H', call_start) AS hour,
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
        return build_pdf('Trunk Peak Utilisation', headers, rows)

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
        return build_pdf('Outcome Summary', headers, rows)

    else:
        return "Invalid report type", 400