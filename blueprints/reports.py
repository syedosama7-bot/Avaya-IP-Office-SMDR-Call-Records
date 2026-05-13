from flask_login import current_user
from flask import Blueprint, render_template, request
from flask_login import login_required
from models.database import get_db
from models.tariff import get_tariffs
from utils import apply_user_filter
from models.audit import log_action
from datetime import datetime

reports_bp = Blueprint('reports', __name__)

# ---------- Time formatting helper ----------
def fmt_seconds(sec):
    """Convert seconds (int/float) to HH:MM:SS string, or empty if None."""
    if sec is None:
        return ''
    try:
        s = int(sec)
    except (ValueError, TypeError):
        return str(sec)
    if s == 0:
        return '0:00'
    hours, remainder = divmod(s, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

@reports_bp.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

@reports_bp.route('/report/<report_type>')
@login_required
def generate_report(report_type):
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')
    specific_date = request.args.get('date', '')
    month = request.args.get('month', '')
    year = request.args.get('year', '')
    extension = request.args.get('extension', '')
    start_date2 = request.args.get('start_date2', '')
    end_date2 = request.args.get('end_date2', '')

    call_id = request.args.get('call_id', '')
    external_number = request.args.get('external_number', '')

    # ---------- Pagination setup ----------
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(25, min(500, int(request.args.get('per_page', 100))))
    except (ValueError, TypeError):
        per_page = 100

    # Clean filters for template (remove pagination keys)
    clean_filters = {k: v for k, v in request.args.items() if k not in ('page', 'per_page')}

    def build_where(base_conditions=None, base_params=None):
        if base_conditions is None: base_conditions = []
        if base_params is None: base_params = []
        conditions = base_conditions[:]
        params = base_params[:]
        if start_date:
            start_fmt = start_date.replace('-', '/')
            conditions.append("call_start >= ?")
            params.append(start_fmt + " 00:00:00")
        if end_date:
            end_fmt = end_date.replace('-', '/')
            conditions.append("call_start <= ?")
            params.append(end_fmt + " 23:59:59")
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if is_internal:
            if is_internal == 'internal': conditions.append("is_internal = 1")
            elif is_internal == 'external': conditions.append("is_internal = 0")
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        return where, params

    conn = get_db()
    cursor = conn.cursor()

    # ======================== DAILY SUMMARY ========================
    if report_type == 'daily_summary':
        if specific_date:
            start_fmt = specific_date.replace('-', '/')
            conditions = ["call_start >= ?", "call_start <= ?"]
            params = [start_fmt+" 00:00:00", start_fmt+" 23:59:59"]
            if direction: conditions.append("direction = ?"); params.append(direction)
            if is_internal:
                if is_internal == 'internal': conditions.append("is_internal = 1")
                elif is_internal == 'external': conditions.append("is_internal = 0")
            if search:
                conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
                like = f"%{search}%"
                params.extend([like, like, like])
            conditions, params = apply_user_filter(conditions, params)
            where = "WHERE " + " AND ".join(conditions)
        else:
            where, params = build_where()

        cursor.execute(f"SELECT COUNT(*) FROM (SELECT 1 FROM calls {where} GROUP BY DATE(replace(call_start, '/', '-')))", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""
            SELECT DATE(replace(call_start, '/', '-')) as date, COUNT(*), SUM(duration_seconds),
                   SUM(ring_time), SUM(hold_time), SUM(cost)
            FROM calls {where}
            GROUP BY date ORDER BY date DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        # Format times
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0],
                row[1],
                fmt_seconds(row[2]),
                fmt_seconds(row[3]),
                fmt_seconds(row[4]),
                f"${round(row[5], 2)}" if row[5] else '$0.00'
            ))
        headers = ['Date', 'Total Calls', 'Talk Time', 'Ring Time', 'Hold Time', 'Cost']
        title = 'Daily Call Summary'
        rows = formatted_rows

    # ======================== TOP CALLERS ========================
    elif report_type == 'top_callers':
        where, params = build_where()
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT caller FROM calls {where} GROUP BY caller)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY caller ORDER BY COUNT(*) DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0],
                row[1],
                fmt_seconds(row[2]),
                f"${round(row[3], 2)}" if row[3] else '$0.00'
            ))
        headers = ['Caller', 'Call Count', 'Total Talk Time', 'Total Cost']
        title = 'Top Callers'
        rows = formatted_rows

    # ======================== TOP CALLED NUMBERS ========================
    elif report_type == 'top_called':
        where, params = build_where()
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT called_num FROM calls {where} GROUP BY called_num)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY called_num ORDER BY COUNT(*) DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0],
                row[1],
                fmt_seconds(row[2]),
                f"${round(row[3], 2)}" if row[3] else '$0.00'
            ))
        headers = ['Called Number', 'Call Count', 'Total Talk Time', 'Total Cost']
        title = 'Top Called Numbers'
        rows = formatted_rows

    # ======================== HOURLY DISTRIBUTION ========================
    elif report_type == 'hourly_distribution':
        if specific_date:
            start_fmt = specific_date.replace('-', '/')
            where = "WHERE call_start >= ? AND call_start <= ?"
            params = [start_fmt+" 00:00:00", start_fmt+" 23:59:59"]
            if direction:
                where += " AND direction = ?"; params.append(direction)
            if is_internal == 'internal':
                where += " AND is_internal = 1"
            elif is_internal == 'external':
                where += " AND is_internal = 0"
            if search:
                where += " AND (caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)"
                like = f"%{search}%"
                params.extend([like, like, like])
            conditions, params = apply_user_filter(["call_start >= ?", "call_start <= ?"], params[:2])
        else:
            where, params = build_where()

        cursor.execute(f"SELECT COUNT(*) FROM (SELECT strftime('%H', replace(call_start, '/', '-')) FROM calls {where} GROUP BY 1)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT strftime('%H', replace(call_start, '/', '-')) AS hour, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY hour ORDER BY COUNT(*) DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((row[0], row[1], fmt_seconds(row[2])))
        headers = ['Hour', 'Total Calls', 'Total Talk Time']
        title = 'Busiest Hour Distribution'
        rows = formatted_rows

    # ======================== COST BY TARIFF PREFIX ========================
    elif report_type == 'cost_by_prefix':
        conditions = ["is_internal = 0"]
        params = []
        if month and year:
            conditions.append("CAST(strftime('%m', replace(call_start, '/', '-')) AS INTEGER) = ?")
            params.append(int(month))
            conditions.append("CAST(strftime('%Y', replace(call_start, '/', '-')) AS INTEGER) = ?")
            params.append(int(year))
        else:
            if start_date:
                conditions.append("call_start >= ?")
                params.append(start_date.replace('-', '/') + " 00:00:00")
            if end_date:
                conditions.append("call_start <= ?")
                params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction: conditions.append("direction = ?"); params.append(direction)
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions)
        cursor.execute(f"SELECT called_num, duration_seconds FROM calls {where}", params)
        call_rows = cursor.fetchall()
        tariffs = get_tariffs()
        prefix_costs = {}
        for called_num, dur_sec in call_rows:
            matched_prefix = 'local'
            max_len = 0
            for prefix, rate in tariffs:
                if called_num.startswith(prefix) and len(prefix) > max_len:
                    matched_prefix = prefix; max_len = len(prefix)
            minutes = dur_sec / 60.0
            cost = minutes * (dict(tariffs).get(matched_prefix, 1.0))
            prefix_costs[matched_prefix] = prefix_costs.get(matched_prefix, 0) + cost
        rows = [(prefix, f"${round(cost, 2)}") for prefix, cost in prefix_costs.items()]
        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page
        rows = rows[offset:offset+per_page]
        headers = ['Prefix', 'Total Cost']
        title = f'Cost by Tariff Prefix ({month}/{year if month else "All"})'
        conn.close()
        log_action(current_user.id, f"Viewed report: {title}")
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=rows,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== EXTENSION USAGE ========================
    elif report_type == 'extension_usage':
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction: conditions.append("direction = ?"); params.append(direction)
        if is_internal:
            if is_internal == 'internal': conditions.append("is_internal = 1")
            elif is_internal == 'external': conditions.append("is_internal = 0")
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if extension:
            exts = [e.strip() for e in extension.split(',') if e.strip()]
            if exts:
                parts = []
                for ext in exts:
                    parts.append("caller = ?"); params.append(ext)
                    parts.append("called_num = ?"); params.append(ext)
                conditions.append("(" + " OR ".join(parts) + ")")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM (SELECT extension FROM (SELECT caller AS extension FROM calls {where} UNION ALL SELECT called_num AS extension FROM calls {where}) GROUP BY extension)", params + params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

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
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0], row[1], row[2],
                fmt_seconds(row[3]), fmt_seconds(row[4]),
                f"${round(row[5], 2)}" if row[5] else '$0.00',
                f"${round(row[6], 2)}" if row[6] else '$0.00'
            ))
        headers = ['Extension', 'Calls Made', 'Calls Received', 'Talk Made', 'Talk Received', 'Cost Made', 'Cost Received']
        title = 'Extension Usage Summary'
        rows = formatted_rows

    # ======================== RING TIME ========================
    elif report_type == 'ring_time':
        where, params = build_where()
        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT call_start, duration_raw, ring_time, caller, direction, called_num, party1_name
                  FROM calls {where} ORDER BY ring_time DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0], row[1], fmt_seconds(row[2]), row[3], row[4], row[5], row[6]
            ))
        headers = ['Call Start', 'Duration', 'Ring Time', 'Caller', 'Direction', 'Called Number', 'Party1 Name']
        title = 'Longest Ring Times'
        rows = formatted_rows

    # ======================== ABANDONED / SHORT CALLS ========================
    elif report_type == 'abandoned':
        where, params = build_where(["duration_seconds = 0"], [])
        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT call_start, ring_time, caller, direction, called_num, party1_name, party2_name
                  FROM calls {where} ORDER BY call_start DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0], fmt_seconds(row[1]), row[2], row[3], row[4], row[5], row[6]
            ))
        headers = ['Call Start', 'Ring Time', 'Caller', 'Direction', 'Called Number', 'From', 'To']
        title = 'Abandoned / Short Calls'
        rows = formatted_rows

        # ======================== HEATMAP ========================
    elif report_type == 'heatmap':
        where, params = build_where()
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT strftime('%w', replace(call_start, '/', '-')) as dow, strftime('%H', replace(call_start, '/', '-')) as hour FROM calls {where} GROUP BY dow, hour)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT strftime('%w', replace(call_start, '/', '-')) as dow,
                         strftime('%H', replace(call_start, '/', '-')) as hour,
                         COUNT(*) as cnt
                  FROM calls {where} GROUP BY dow, hour ORDER BY dow, hour
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()

        # Convert day-of-week numbers to names
        day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        formatted_rows = []
        for row in rows:
            dow = int(row[0]) if row[0] is not None else 0
            day_label = day_names[dow] if 0 <= dow <= 6 else str(row[0])
            formatted_rows.append((day_label, row[1], row[2]))

        headers = ['Day of Week', 'Hour', 'Call Count']
        title = 'Call Heatmap (Day of Week vs Hour)'
        description = 'Each cell shows the total number of calls for that day and hour. Use this to identify peak calling times.'
        
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               description=description,
                               headers=headers,
                               rows=formatted_rows,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== TRUNK USAGE ========================
    elif report_type == 'trunk_usage':
        where, params = build_where()
        if where: where += " AND party2_device LIKE 'T%'"
        else: where = "WHERE party2_device LIKE 'T%'"
        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT party2_device AS trunk, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY trunk ORDER BY COUNT(*) DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((row[0], row[1], fmt_seconds(row[2])))
        headers = ['Trunk', 'Call Count', 'Total Talk Time']
        title = 'Trunk Usage'
        rows = formatted_rows

    # ======================== PERIOD COMPARISON ========================
    elif report_type == 'period_comparison':
        where1, params1 = build_where()
        cursor.execute(f"SELECT COUNT(*), SUM(duration_seconds), SUM(cost) FROM calls {where1}", params1)
        res1 = cursor.fetchone()
        conditions2 = []
        params2 = []
        if start_date2: conditions2.append("call_start >= ?"); params2.append(start_date2.replace('-','/') + " 00:00:00")
        if end_date2: conditions2.append("call_start <= ?"); params2.append(end_date2.replace('-','/') + " 23:59:59")
        if direction: conditions2.append("direction = ?"); params2.append(direction)
        if is_internal:
            if is_internal == 'internal': conditions2.append("is_internal = 1")
            elif is_internal == 'external': conditions2.append("is_internal = 0")
        if search:
            conditions2.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params2.extend([like, like, like])
        conditions2, params2 = apply_user_filter(conditions2, params2)
        where2 = "WHERE " + " AND ".join(conditions2) if conditions2 else ""
        cursor.execute(f"SELECT COUNT(*), SUM(duration_seconds), SUM(cost) FROM calls {where2}", params2)
        res2 = cursor.fetchone()
        rows = [
            ('Metric', 'Period 1', 'Period 2'),
            ('Total Calls', res1[0] or 0, res2[0] or 0),
            ('Total Talk Time', fmt_seconds(res1[1] or 0), fmt_seconds(res2[1] or 0)),
            ('Total Cost', f"${round(res1[2] or 0, 2)}", f"${round(res2[2] or 0, 2)}")
        ]
        headers = ['Metric', 'Period 1', 'Period 2']
        title = 'Period Comparison'
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=clean_filters)

    # ======================== DETAIL CALL RECORDS ========================
    elif report_type == 'detail_call_report':
        if not start_date and not end_date:
            today_str = datetime.now().strftime('%Y-%m-%d')
            start_date = today_str
            end_date = today_str
        conditions = []
        params = []
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
            if is_internal == 'internal': conditions.append("is_internal = 1")
            elif is_internal == 'external': conditions.append("is_internal = 0")
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"SELECT * FROM calls {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        output_rows = []
        for r in rows:
            r = list(r)
            while len(r) < 30:
                r.append('')
            output_rows.append((
                r[1], r[2], fmt_seconds(r[4]), r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                fmt_seconds(r[17]), fmt_seconds(r[18]), r[19], r[20],
                f"${round(r[21], 2)}" if r[21] else '$0.00',
                r[27] if len(r) > 27 else '',
                r[28] if len(r) > 28 else '',
                r[29] if len(r) > 29 else '',
                'Yes' if r[12] == 1 else 'No'   # multi-leg flag (continuation)
            ))
        headers = [
            'Start Time', 'Duration', 'Ring', 'Caller', 'Direction',
            'Called', 'Dialed', 'Account', 'Internal', 'Call ID',
            'Cont', 'P1 Device', 'P1 Name', 'P2 Device', 'P2 Name',
            'Hold', 'Park', 'Auth Valid', 'Auth Code', 'Cost',
            'Fwd Cause', 'Fwd Targeter', 'Fwd Number', 'Multi-Leg'
        ]
        title = 'Detail Call Records Report'
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=output_rows,
                               filters=clean_filters,
                               pagination={
                                   'page': page,
                                   'total_pages': total_pages,
                                   'total': total,
                                   'per_page': per_page,
                                   'query_params': clean_filters
                               })


    # ======================== CALL JOURNEY (no pagination) ========================
    elif report_type == 'call_journey':
        if not call_id:
            conn.close()
            return "Please provide a Call ID.", 400
        row_id = request.args.get('row_id', '')
        if row_id:
            cursor.execute("SELECT call_start, call_id FROM calls WHERE id = ?", (int(row_id),))
            ref_row = cursor.fetchone()
            if ref_row:
                ref_start = ref_row['call_start']
                ref_call_id = ref_row['call_id']
                conn.close()
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
                all_rows = cursor.fetchall()
                journey_rows = []
                selected_idx = None
                for i, r in enumerate(all_rows):
                    if r['id'] == int(row_id):
                        selected_idx = i
                        break
                if selected_idx is not None:
                    legs = [all_rows[selected_idx]]
                    prev_start = ref_start
                    for j in range(selected_idx - 1, -1, -1):
                        curr = all_rows[j]
                        curr_start = curr['call_start']
                        if (datetime.strptime(prev_start, '%Y/%m/%d %H:%M:%S') -
                            datetime.strptime(curr_start, '%Y/%m/%d %H:%M:%S')).total_seconds() <= 300:
                            legs.insert(0, curr)
                            prev_start = curr_start
                        else:
                            break
                    next_start = ref_start
                    for j in range(selected_idx + 1, len(all_rows)):
                        curr = all_rows[j]
                        curr_start = curr['call_start']
                        if (datetime.strptime(curr_start, '%Y/%m/%d %H:%M:%S') -
                            datetime.strptime(next_start, '%Y/%m/%d %H:%M:%S')).total_seconds() <= 300:
                            legs.append(curr)
                            next_start = curr_start
                        else:
                            break
                    journey_rows = legs
                else:
                    journey_rows = all_rows
            else:
                cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
                journey_rows = cursor.fetchall()
        else:
            cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
            journey_rows = cursor.fetchall()

        output_rows = []
        for r in journey_rows:
            r = list(r) + [''] * 15
            output_rows.append((
                r[0], r[1], r[2], fmt_seconds(r[4]), r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                fmt_seconds(r[17]), fmt_seconds(r[18]), r[19], r[20],
                f"${round(r[21], 2)}" if r[21] else '$0.00',
                r[27] if len(r) > 27 else '',
                r[28] if len(r) > 28 else '',
                r[29] if len(r) > 29 else '',
                'Yes' if r[12] == 1 else 'No'
            ))
        headers = [
            'ID', 'Start Time', 'Duration', 'Ring', 'Caller', 'Direction',
            'Called', 'Dialed', 'Account', 'Internal', 'Call ID', 'Cont',
            'P1 Device', 'P1 Name', 'P2 Device', 'P2 Name',
            'Hold', 'Park', 'Auth Valid', 'Auth Code', 'Cost',
            'Fwd Cause', 'Fwd Targeter', 'Fwd Number', 'Multi-Leg'
        ]
        title = f'Call Journey (Call ID: {call_id})'
        log_action(current_user.id, f"Viewed report: {title}")
        show_diagram = request.args.get('diagram', '0') == '1'
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=output_rows,
                               filters=clean_filters,
                               show_diagram=show_diagram,
                               call_id=call_id)



    # ======================== DURATION DISTRIBUTION ========================
    elif report_type == 'duration_distribution':
        where, params = build_where()
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT CASE WHEN duration_seconds BETWEEN 0 AND 10 THEN '0-10s' WHEN duration_seconds BETWEEN 11 AND 30 THEN '10-30s' WHEN duration_seconds BETWEEN 31 AND 60 THEN '30-60s' WHEN duration_seconds BETWEEN 61 AND 120 THEN '1-2min' WHEN duration_seconds BETWEEN 121 AND 300 THEN '2-5min' WHEN duration_seconds BETWEEN 301 AND 600 THEN '5-10min' WHEN duration_seconds BETWEEN 601 AND 1800 THEN '10-30min' ELSE '30min+' END AS bucket FROM calls {where} GROUP BY bucket)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

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
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        headers = ['Duration Bucket', 'Call Count']
        title = 'Call Duration Distribution'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=rows,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== ABANDONED TREND ========================
    elif report_type == 'abandoned_trend':
        where, params = build_where(["duration_seconds = 0"], [])
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT DATE(replace(call_start, '/', '-')) as date FROM calls {where} GROUP BY date)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""
            SELECT DATE(replace(call_start, '/', '-')) as date, COUNT(*) as count
            FROM calls {where}
            GROUP BY date
            ORDER BY date DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        headers = ['Date', 'Abandoned Calls']
        title = 'Abandoned Call Trend'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=rows,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== CALLER PROFILE ========================
    elif report_type == 'caller_profile':
        if not external_number:
            conn.close()
            return "Please provide an external number.", 400
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        conditions.append("(caller = ? OR called_num = ?)")
        params.append(external_number)
        params.append(external_number)
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if is_internal:
            if is_internal == 'internal': conditions.append("is_internal = 1")
            elif is_internal == 'external': conditions.append("is_internal = 0")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"SELECT * FROM calls {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()

        stats_query = f"SELECT COUNT(*), SUM(duration_seconds), AVG(duration_seconds), SUM(cost) FROM calls {where}"
        cursor.execute(stats_query, params)
        stats = cursor.fetchone()
        summary = {
            'total_calls': stats[0] or 0,
            'total_talk': fmt_seconds(stats[1] or 0),
            'avg_duration': fmt_seconds(int(stats[2] or 0)),
            'total_cost': f"${round(stats[3] or 0, 2)}"
        }
        output_rows = []
        for r in rows:
            r = list(r) + ['']*15
            output_rows.append((
                r[1], r[2],
                r[5], r[6], r[7],
                r[14], r[16]
            ))
        headers = ['Start Time', 'Duration', 'Caller', 'Direction', 'Called', 'Party1 Name', 'Party2 Name']
        title = f'Caller Profile: {external_number}'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=output_rows,
                               summary=summary,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== EXTENSION SCORECARD ========================
    elif report_type == 'extension_scorecard':
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction: conditions.append("direction = ?"); params.append(direction)
        if is_internal:
            if is_internal == 'internal': conditions.append("is_internal = 1")
            elif is_internal == 'external': conditions.append("is_internal = 0")
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if extension:
            exts = [e.strip() for e in extension.split(',') if e.strip()]
            if exts:
                parts = []
                for ext in exts:
                    parts.append("caller = ?"); params.append(ext)
                    parts.append("called_num = ?"); params.append(ext)
                conditions.append("(" + " OR ".join(parts) + ")")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM (SELECT extension FROM (SELECT caller AS extension FROM calls {where} UNION ALL SELECT called_num AS extension FROM calls {where}) GROUP BY extension)", params + params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

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
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            formatted_rows.append((
                row[0], row[1], row[2],
                fmt_seconds(row[3]), fmt_seconds(row[4]),
                f"${round(row[5], 2)}" if row[5] else '$0.00',
                f"${round(row[6], 2)}" if row[6] else '$0.00',
                round(row[7], 1) if row[7] else 0
            ))
        headers = ['Extension', 'Calls Made', 'Calls Received', 'Talk Made', 'Talk Received', 'Cost Made', 'Cost Received', 'Activity Score']
        title = 'Extension Activity Scorecard'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=formatted_rows,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== TRUNK PEAK UTILISATION ========================
    elif report_type == 'trunk_peak_utilisation':
        where, params = build_where()
        inner_where = where + (" AND party2_device LIKE 'T%'" if where else "WHERE party2_device LIKE 'T%'")
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT party2_device AS trunk FROM calls {inner_where} GROUP BY trunk)", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

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
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        headers = ['Trunk', 'Peak Calls', 'Peak Hour']
        title = 'Trunk Peak Utilisation'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=rows,
                               filters=clean_filters,
                               pagination={'page': page, 'total_pages': total_pages, 'total': total})

    # ======================== OUTCOME SUMMARY ========================
    elif report_type == 'outcome_summary':
        where, params = build_where()
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
        title = 'Call Outcome Summary'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=rows,
                               filters=clean_filters)



    elif report_type == 'auth_audit':
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        # optional auth status filter
        auth_status = request.args.get('auth_status', '')
        if auth_status == 'valid':
            conditions.append("auth_valid = 1")
        elif auth_status == 'invalid':
            conditions.append("auth_valid = 0")
        conditions.append("auth_code IS NOT NULL AND auth_code != '' AND auth_code != 'n/a'")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT call_start, caller, called_num, direction, auth_valid, auth_code, cost
                  FROM calls {where}
                  ORDER BY id DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = []
        for row in rows:
            auth_label = 'Valid' if row[4] == 1 else 'Invalid'
            formatted_rows.append((
                row[0], row[1], row[2], row[3],
                auth_label, row[5] or '—', f"${round(row[6], 2)}" if row[6] else '$0.00'
            ))
        headers = ['Start Time', 'Caller', 'Called', 'Direction', 'Auth Status', 'Auth Code', 'Cost']
        title = 'Authorization Code Audit'
        description = 'Lists calls that used an authorization code and whether it was valid.'





    elif report_type == 'forwarding_analysis':
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        # Filter by cause (optional)
        cause_filter = request.args.get('cause', '').strip()
        if cause_filter:
            conditions.append("external_targeting_cause LIKE ?")
            params.append(f"%{cause_filter}%")
        conditions.append("external_targeting_cause IS NOT NULL AND external_targeting_cause != ''")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT call_start, caller, direction, external_targeting_cause,
                         external_targeter_id, external_targeted_number, party1_name, party2_name
                  FROM calls {where}
                  ORDER BY id DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = [(row[0], row[1], row[2], row[3], row[4] or '—', row[5] or '—', row[6] or '', row[7] or '') for row in rows]
        headers = ['Start Time', 'Caller', 'Direction', 'Cause', 'Targeter', 'Targeted Number', 'Party1 Name', 'Party2 Name']
        title = 'Forwarding & Redirect Analysis'
        description = 'Shows calls that were redirected externally and why.'



    elif report_type == 'hunt_group_activity':
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        conditions.append("external_targeting_cause LIKE 'HG%'")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT call_start, caller, called_num, direction, external_targeting_cause,
                         external_targeter_id, party1_name, party2_name, duration_raw
                  FROM calls {where}
                  ORDER BY id DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = [(row[0], row[1], row[2], row[3], row[4], row[5] or '—', row[6] or '', row[7] or '', row[8]) for row in rows]
        headers = ['Start Time', 'Caller', 'Called', 'Direction', 'Cause', 'Targeter', 'Agent (P1)', 'P2', 'Duration']
        title = 'Hunt Group Activity'
        description = 'Calls routed through hunt groups, showing the targeter and agents involved.'


    elif report_type == 'conferenced_calls':
        conditions = []
        params = []
        if start_date:
            conditions.append("call_start >= ?")
            params.append(start_date.replace('-', '/') + " 00:00:00")
        if end_date:
            conditions.append("call_start <= ?")
            params.append(end_date.replace('-', '/') + " 23:59:59")
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if search:
            conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        conditions.append("(party1_device LIKE 'V1%' OR party2_device LIKE 'V1%')")
        conditions, params = apply_user_filter(conditions, params)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) FROM calls {where}", params)
        total = cursor.fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        query = f"""SELECT call_start, caller, called_num, direction, party1_name, party2_name,
                         party1_device, party2_device, duration_raw
                  FROM calls {where}
                  ORDER BY id DESC
                  LIMIT ? OFFSET ?"""
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        formatted_rows = [(row[0], row[1], row[2], row[3], row[4] or '', row[5] or '', row[6], row[7], row[8]) for row in rows]
        headers = ['Start Time', 'Caller', 'Called', 'Direction', 'P1 Name', 'P2 Name', 'P1 Device', 'P2 Device', 'Duration']
        title = 'Conferenced Calls'
        description = 'Calls involving a conference bridge (V1 devices).'





    else:
        conn.close()
        return "Invalid report type", 400

    conn.close()

    pagination = None
    if 'total_pages' in locals():
        pagination = {
            'page': page,
            'total_pages': total_pages,
            'total': total,
            'per_page': per_page,
            'query_params': clean_filters
        }
    return render_template('report_view.html',
                           report_type=report_type,
                           report_title=title,
                           headers=headers,
                           rows=rows,
                           filters=clean_filters,
                           pagination=pagination)


# ========== JSON endpoint for Call Journey diagram ==========
@reports_bp.route('/report/call_journey/json')
@login_required
def call_journey_json():
    call_id = request.args.get('call_id', '')
    row_id = request.args.get('row_id', '')

    if not call_id:
        return {"error": "call_id is required"}, 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
    all_rows = cursor.fetchall()

    if not row_id:
        journey_rows = all_rows
    else:
        ref = None
        for r in all_rows:
            if r['id'] == int(row_id):
                ref = r
                break
        if not ref:
            journey_rows = all_rows
        else:
            ref_start = ref['call_start']
            legs = [ref]
            prev = ref_start
            for r in reversed(all_rows[:all_rows.index(ref)]):
                curr_start = r['call_start']
                if (datetime.strptime(prev, '%Y/%m/%d %H:%M:%S') -
                    datetime.strptime(curr_start, '%Y/%m/%d %H:%M:%S')).total_seconds() <= 300:
                    legs.insert(0, r)
                    prev = curr_start
                else:
                    break
            next_start = ref_start
            for r in all_rows[all_rows.index(ref)+1:]:
                curr_start = r['call_start']
                if (datetime.strptime(curr_start, '%Y/%m/%d %H:%M:%S') -
                    datetime.strptime(next_start, '%Y/%m/%d %H:%M:%S')).total_seconds() <= 300:
                    legs.append(r)
                    next_start = curr_start
                else:
                    break
            journey_rows = legs

    conn.close()

    result = []
    for r in journey_rows:
        r = list(r) + [''] * 15
        result.append({
            'id': r[0],
            'start_time': r[1],
            'duration': r[2],
            'ring': r[4],
            'caller': r[5],
            'direction': r[6],
            'called': r[7],
            'dialed': r[8],
            'account': r[9],
            'internal': r[10],
            'call_id': r[11],
            'continuation': r[12],
            'p1_device': r[13],
            'p1_name': r[14],
            'p2_device': r[15],
            'p2_name': r[16],
            'hold': r[17],
            'park': r[18],
            'auth_valid': r[19],
            'auth_code': r[20],
            'cost': r[21]
        })
    return {'legs': result}