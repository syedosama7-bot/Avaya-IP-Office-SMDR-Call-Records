from flask import Blueprint, render_template, request
from flask_login import login_required
from models.database import get_db
from models.tariff import get_tariffs
from utils import apply_user_filter

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
        return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)

    # ... (other report types: extension_usage, ring_time, abandoned, heatmap, trunk_usage, period_comparison)
    # These are identical to the original generate_report, using build_where and get_db().
    # I'll include the full code below to be safe.

    # For the complete file, I'll now provide the rest of the report types as a single block.

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

    else:
        conn.close()
        return "Invalid report type", 400

    conn.close()
    return render_template('report_view.html', report_type=report_type, report_title=title, headers=headers, rows=rows, filters=request.args)