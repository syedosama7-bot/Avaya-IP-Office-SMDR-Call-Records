from flask_login import current_user
from flask import Blueprint, render_template, request
from flask_login import login_required
from models.database import get_db
from models.tariff import get_tariffs
from utils import apply_user_filter
from models.audit import log_action
from datetime import datetime

reports_bp = Blueprint('reports', __name__)

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

    # ======================== EXISTING REPORTS ========================
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
        query = f"""
            SELECT DATE(call_start) as date, COUNT(*), SUM(duration_seconds),
                   SUM(ring_time), SUM(hold_time), SUM(cost)
            FROM calls {where}
            GROUP BY DATE(call_start) ORDER BY date DESC LIMIT 30
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring Time (sec)', 'Hold Time (sec)', 'Cost ($)']
        title = 'Daily Call Summary'

    elif report_type == 'top_callers':
        where, params = build_where()
        query = f"""SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY caller ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Caller', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
        title = 'Top Callers'

    elif report_type == 'top_called':
        where, params = build_where()
        query = f"""SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
                  FROM calls {where} GROUP BY called_num ORDER BY COUNT(*) DESC LIMIT 20"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Called Number', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
        title = 'Top Called Numbers'

    elif report_type == 'hourly_distribution':
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
        query = f"""SELECT strftime('%H', call_start) AS hour, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY hour ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Hour', 'Total Calls', 'Total Talk Time (sec)']
        title = 'Busiest Hour Distribution'

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
        rows = [(prefix, round(cost, 2)) for prefix, cost in prefix_costs.items()]
        headers = ['Prefix', 'Total Cost ($)']
        title = f'Cost by Tariff Prefix ({month}/{year if month else "All"})'
        conn.close()
        log_action(current_user.id, f"Viewed report: {title}")
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

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
        title = 'Extension Usage Summary'

    elif report_type == 'ring_time':
        where, params = build_where()
        query = f"""SELECT call_start, duration_raw, ring_time, caller, direction, called_num, party1_name
                  FROM calls {where} ORDER BY ring_time DESC LIMIT 50"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Duration', 'Ring (sec)', 'Caller', 'Direction', 'Called Number', 'Party1 Name']
        title = 'Longest Ring Times'

    elif report_type == 'abandoned':
        where, params = build_where(["duration_seconds = 0"], [])
        query = f"""SELECT call_start, ring_time, caller, direction, called_num, party1_name, party2_name
                  FROM calls {where} ORDER BY call_start DESC LIMIT 100"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Call Start', 'Ring Time (sec)', 'Caller', 'Direction', 'Called Number', 'From', 'To']
        title = 'Abandoned / Short Calls'

    elif report_type == 'heatmap':
        where, params = build_where()
        query = f"""SELECT strftime('%w', replace(call_start, '/', '-')) as dow,
                         strftime('%H', replace(call_start, '/', '-')) as hour,
                         COUNT(*) as cnt
                  FROM calls {where} GROUP BY dow, hour ORDER BY dow, hour"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Day of Week', 'Hour', 'Call Count']
        title = 'Call Heatmap (Day of Week vs Hour)'

    elif report_type == 'trunk_usage':
        where, params = build_where()
        if where: where += " AND party2_device LIKE 'T%'"
        else: where = "WHERE party2_device LIKE 'T%'"
        query = f"""SELECT party2_device AS trunk, COUNT(*), SUM(duration_seconds)
                  FROM calls {where} GROUP BY trunk ORDER BY COUNT(*) DESC"""
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Trunk', 'Call Count', 'Total Talk Time (sec)']
        title = 'Trunk Usage'

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
            ('Total Talk Time (sec)', res1[1] or 0, res2[1] or 0),
            ('Total Cost ($)', round(res1[2] or 0, 2), round(res2[2] or 0, 2))
        ]
        headers = ['Metric', 'Period 1', 'Period 2']
        title = 'Period Comparison'
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

    elif report_type == 'detail_call_report':
        if not start_date and not end_date:
            today_str = datetime.now().strftime('%Y-%m-%d')
            start_date = today_str
            end_date = today_str
        try:
            page = int(request.args.get('page', 1))
        except ValueError:
            page = 1
        per_page = 100
        offset = (page - 1) * per_page
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
        count_query = f"SELECT COUNT(*) FROM calls {where}"
        conn_total = get_db()
        cursor_total = conn_total.cursor()
        cursor_total.execute(count_query, params)
        total = cursor_total.fetchone()[0]
        conn_total.close()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        query = f"SELECT * FROM calls {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        headers = [
            'Start Time', 'Duration', 'Ring (sec)', 'Caller', 'Direction',
            'Called', 'Dialed', 'Account', 'Internal', 'Call ID',
            'Cont', 'P1 Device', 'P1 Name', 'P2 Device', 'P2 Name',
            'Hold (sec)', 'Park (sec)', 'Auth Valid', 'Auth Code', 'Cost'
        ]
        output_rows = []
        for r in rows:
            r = list(r)
            while len(r) < 22:
                r.append('')
            output_rows.append((
                r[1], r[2], r[4], r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                r[17], r[18], r[19], r[20], r[21] if len(r) > 21 else '0.0'
            ))
        title = 'Detail Call Records Report'
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=output_rows,
                               filters=request.args,
                               pagination={
                                   'page': page,
                                   'total_pages': total_pages,
                                   'total': total,
                                   'per_page': per_page,
                                   'query_params': request.args
                               })

    # ======================== NEW REPORTS ========================
    elif report_type == 'call_journey':
        if not call_id:
            conn.close()
            return "Please provide a Call ID.", 400

        # Optional row_id to pinpoint the exact journey (for reboot resilience)
        row_id = request.args.get('row_id', '')

        if row_id:
            # Find the selected leg first
            cursor.execute("SELECT call_start, call_id FROM calls WHERE id = ?", (int(row_id),))
            ref_row = cursor.fetchone()
            if ref_row:
                ref_start = ref_row['call_start']
                ref_call_id = ref_row['call_id']
                # Determine a time window: from a few minutes before the first leg
                # to a generous end. We'll fetch all legs with the same call_id,
                # then filter in Python to the contiguous block around ref_start.
                conn.close()
                conn = get_db()
                cursor = conn.cursor()
                # Get all legs with this call_id, ordered by id (or start_time)
                cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
                all_rows = cursor.fetchall()

                # Filter to only legs within the same journey session:
                # We consider legs that are within 5 minutes of the previous leg's start time.
                # Build a contiguous block containing the selected row id.
                journey_rows = []
                selected_idx = None
                for i, r in enumerate(all_rows):
                    if r['id'] == int(row_id):
                        selected_idx = i
                        break

                if selected_idx is not None:
                    # Walk backward and forward, including legs while gap ≤ 5 minutes
                    legs = [all_rows[selected_idx]]
                    # backward
                    prev_start = ref_start
                    for j in range(selected_idx - 1, -1, -1):
                        curr = all_rows[j]
                        curr_start = curr['call_start']
                        # if the gap between this leg's start and the previous leg's start ≤ 5 min
                        if (datetime.strptime(prev_start, '%Y/%m/%d %H:%M:%S') -
                            datetime.strptime(curr_start, '%Y/%m/%d %H:%M:%S')).total_seconds() <= 300:
                            legs.insert(0, curr)
                            prev_start = curr_start
                        else:
                            break
                    # forward
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
                    journey_rows = all_rows  # fallback (should not happen)

            else:
                # row_id not found, fallback to all legs with that call_id
                cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
                journey_rows = cursor.fetchall()
        else:
            # No row_id – get all legs with that call_id (may include duplicates after reboot)
            cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
            journey_rows = cursor.fetchall()

        # Build output rows
        headers = [
            'ID', 'Start Time', 'Duration', 'Ring (s)', 'Caller', 'Direction',
            'Called', 'Dialed', 'Account', 'Internal', 'Call ID', 'Cont',
            'P1 Device', 'P1 Name', 'P2 Device', 'P2 Name',
            'Hold (s)', 'Park (s)', 'Auth Valid', 'Auth Code', 'Cost'
        ]
        output_rows = []
        for r in journey_rows:
            r = list(r) + [''] * 15
            output_rows.append((
                r[0], r[1], r[2], r[4], r[5], r[6],
                r[7], r[8], r[9], 'Yes' if r[10] else 'No',
                r[11], r[12], r[13], r[14], r[15], r[16],
                r[17], r[18], r[19], r[20], r[21]
            ))
        title = f'Call Journey (Call ID: {call_id})'
        log_action(current_user.id, f"Viewed report: {title}")
        show_diagram = request.args.get('diagram', '0') == '1'
        conn.close()
        return render_template('report_view.html',
                               report_type=report_type,
                               report_title=title,
                               headers=headers,
                               rows=output_rows,
                               filters=request.args,
                               show_diagram=show_diagram,
                               call_id=call_id)

    elif report_type == 'duration_distribution':
        where, params = build_where()
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
        title = 'Call Duration Distribution'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

    elif report_type == 'abandoned_trend':
        where, params = build_where(["duration_seconds = 0"], [])
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
        title = 'Abandoned Call Trend'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

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
        query = f"SELECT * FROM calls {where} ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        stats_query = f"SELECT COUNT(*), SUM(duration_seconds), AVG(duration_seconds), SUM(cost) FROM calls {where}"
        cursor.execute(stats_query, params)
        stats = cursor.fetchone()
        summary = {
            'total_calls': stats[0] or 0,
            'total_talk': f"{stats[1] or 0}s",
            'avg_duration': f"{int(stats[2] or 0)}s",
            'total_cost': f"${round(stats[3] or 0, 2)}"
        }
        headers = ['Start Time', 'Duration', 'Caller', 'Direction', 'Called', 'Party1 Name', 'Party2 Name']
        output_rows = []
        for r in rows:
            r = list(r) + ['']*15
            output_rows.append((r[1], r[2], r[5], r[6], r[7], r[14], r[16]))
        title = f'Caller Profile: {external_number}'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=output_rows, summary=summary, filters=request.args)

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
        title = 'Extension Activity Scorecard'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

    elif report_type == 'trunk_peak_utilisation':
        where, params = build_where()
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
        title = 'Trunk Peak Utilisation'
        log_action(current_user.id, f"Viewed report: {title}")
        conn.close()
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

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
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

    else:
        conn.close()
        return "Invalid report type", 400

    conn.close()
    return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)


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

    # Fetch all legs with that call_id
    cursor.execute("SELECT * FROM calls WHERE call_id = ? ORDER BY id ASC", (int(call_id),))
    all_rows = cursor.fetchall()

    if not row_id:
        # No row_id – return all legs (might be inaccurate after PBX reboot)
        journey_rows = all_rows
    else:
        # Find the selected leg
        ref = None
        for r in all_rows:
            if r['id'] == int(row_id):
                ref = r
                break
        if not ref:
            journey_rows = all_rows
        else:
            ref_start = ref['call_start']
            # Build contiguous block around ref using 5‑minute gap
            legs = [ref]
            prev = ref_start
            # backward
            for r in reversed(all_rows[:all_rows.index(ref)]):
                curr_start = r['call_start']
                if (datetime.strptime(prev, '%Y/%m/%d %H:%M:%S') -
                    datetime.strptime(curr_start, '%Y/%m/%d %H:%M:%S')).total_seconds() <= 300:
                    legs.insert(0, r)
                    prev = curr_start
                else:
                    break
            # forward
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