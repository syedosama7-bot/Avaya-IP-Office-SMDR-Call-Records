from flask import Blueprint, render_template, request, current_app, abort
from flask_login import login_required, current_user
from models.call import fetch_calls, summary_stats
from models.database import get_db
from utils import apply_user_filter
from datetime import datetime, timedelta
import sqlite3

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    if not start_date and not end_date:
        today_str = datetime.now().strftime('%Y-%m-%d')
        start_date = today_str
        end_date = today_str

    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

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
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    calls = fetch_calls(where_clause, params)
    stats = summary_stats(where_clause, params)

    total_calls = stats['total_calls'] or 0
    total_duration = str(timedelta(seconds=stats['total_seconds'] or 0))
    avg_duration = str(timedelta(seconds=int(stats['avg_seconds'] or 0)))
    total_ring = str(timedelta(seconds=stats['total_ring'] or 0))
    total_hold = str(timedelta(seconds=stats['total_hold'] or 0))
    total_cost = round(stats['total_cost'] or 0, 2)

    return render_template('index.html',
                           records=calls,
                           summary={
                               'total_calls': total_calls,
                               'total_duration': total_duration,
                               'avg_duration': avg_duration,
                               'total_ring': total_ring,
                               'total_hold': total_hold,
                               'total_cost': total_cost
                           },
                           filters={
                               'start_date': start_date,
                               'end_date': end_date,
                               'direction': direction,
                               'is_internal': is_internal,
                               'search': search
                           })

@dashboard_bp.route('/api/dashboard')
@login_required
def api_dashboard():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    if not start_date and not end_date:
        today_str = datetime.now().strftime('%Y-%m-%d')
        start_date = today_str
        end_date = today_str

    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

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
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    calls = fetch_calls(where_clause, params)
    stats = summary_stats(where_clause, params)

    return {
        'calls': [dict(row) for row in calls],
        'summary': {
            'total_calls': stats['total_calls'] or 0,
            'total_duration': str(timedelta(seconds=stats['total_seconds'] or 0)),
            'avg_duration': str(timedelta(seconds=int(stats['avg_seconds'] or 0))),
            'total_ring': str(timedelta(seconds=stats['total_ring'] or 0)),
            'total_hold': str(timedelta(seconds=stats['total_hold'] or 0)),
            'total_cost': round(stats['total_cost'] or 0, 2)
        }
    }

@dashboard_bp.route('/raw')
@login_required
def raw_data():
    if current_user.role != 'admin':
        abort(403)
    
    # Direct connection – no model layer
    db_path = current_app.config['DATABASE']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM calls")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT * FROM calls ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()

    output = f"Path: {db_path}\nTotal records: {count}\n\n"
    for row in rows:
        output += f"{row}\n"
    return f"<pre>{output}</pre>"

@dashboard_bp.route('/api/call_volume')
@login_required
def api_call_volume():
    range_param = request.args.get('range', '7d')
    interval = request.args.get('interval', 'day')
    now = datetime.now()
    if range_param.endswith('h'):
        hours = int(range_param[:-1])
        start_dt = now - timedelta(hours=hours)
    elif range_param.endswith('d'):
        days = int(range_param[:-1])
        start_dt = now - timedelta(days=days)
    elif range_param.endswith('m'):
        months = int(range_param[:-1])
        start_dt = now - timedelta(days=months * 30)
    elif range_param.endswith('y'):
        years = int(range_param[:-1])
        start_dt = now - timedelta(days=years * 365)
    else:
        start_dt = now - timedelta(days=7)
    start_str = start_dt.strftime('%Y/%m/%d %H:%M:%S')
    base = "replace(call_start, '/', '-')"
    if interval == 'hour':
        group_expr = f"strftime('%Y-%m-%d %H:00', {base})"
        order_expr = group_expr
    elif interval == 'day':
        group_expr = f"date({base})"
        order_expr = group_expr
    elif interval == 'month':
        group_expr = f"strftime('%Y-%m', {base})"
        order_expr = group_expr
    elif interval == 'year':
        group_expr = f"strftime('%Y', {base})"
        order_expr = group_expr
    else:
        group_expr = f"date({base})"
        order_expr = group_expr

    conditions = ["call_start >= ?"]
    params = [start_str]
    conditions, params = apply_user_filter(conditions, params)
    where = "WHERE " + " AND ".join(conditions)

    query = f"""SELECT {group_expr} as period, COUNT(*) as count
                FROM calls {where}
                GROUP BY period ORDER BY {order_expr}"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [{'period': row[0], 'count': row[1]} for row in rows]