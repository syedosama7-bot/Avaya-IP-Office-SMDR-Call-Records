from flask import Flask, render_template, request, make_response, send_file
import sqlite3
import socket
import threading
import csv
import re
import os                     # <-- ADD THIS LINE
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


app = Flask(__name__)

# -------------------------------------------------------------------
# ABSOLUTE PATH TO DATABASE – CHANGE THIS IF NEEDED
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smdr_records.db')
# Or hardcode if you prefer:
# DB_PATH = r"I:\Gen AI Pak angels\IPOFFICE SMDR Project osama\smdr_records.db"

LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 9001

# -------------------------------------------------------------------
# DATABASE INITIALISATION – UPDATED SCHEMA WITH MORE SMDR FIELDS
# -------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create table with all required columns if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_start TEXT,
            duration_raw TEXT,
            duration_seconds INTEGER,
            ring_time INTEGER DEFAULT 0,
            caller TEXT,
            direction TEXT,
            called_num TEXT,
            dialled_num TEXT,
            account_code TEXT,
            is_internal INTEGER,
            call_id INTEGER,
            continuation INTEGER,
            party1_device TEXT,
            party1_name TEXT,
            party2_device TEXT,
            party2_name TEXT,
            hold_time INTEGER DEFAULT 0,
            park_time INTEGER DEFAULT 0,
            auth_valid INTEGER,
            auth_code TEXT,
            cost REAL DEFAULT 0.0
        )
    ''')

    # If table already existed, add any missing columns (migration)
    cursor.execute("PRAGMA table_info(calls)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    desired_columns = {
        'ring_time': 'INTEGER DEFAULT 0',
        'dialled_num': 'TEXT',
        'account_code': 'TEXT',
        'call_id': 'INTEGER',
        'continuation': 'INTEGER',
        'party1_device': 'TEXT',
        'party1_name': 'TEXT',
        'party2_device': 'TEXT',
        'party2_name': 'TEXT',
        'hold_time': 'INTEGER DEFAULT 0',
        'park_time': 'INTEGER DEFAULT 0',
        'auth_valid': 'INTEGER',
        'auth_code': 'TEXT',
    }

    for col_name, col_type in desired_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE calls ADD COLUMN {col_name} {col_type}")
                print(f"[MIGRATION] Added column '{col_name}'")
            except sqlite3.OperationalError as e:
                print(f"[WARN] Could not add column {col_name}: {e}")

    # Tariffs table (unchanged)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix TEXT UNIQUE,
            description TEXT,
            rate_per_minute REAL
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO tariffs (prefix, description, rate_per_minute) VALUES ('local', 'Default Rate', 1.0)")
    conn.commit()
    conn.close()
    print("[OK] Database Ready")

# -------------------------------------------------------------------
# PARSE SMDR RAW DATA AND SAVE TO DATABASE (EXPANDED FIELDS)
# -------------------------------------------------------------------
def parse_and_save(raw_data):
    match = re.search(r'(\d{4}/\d{2}/\d{2}\s\d{2}:\d{2}:\d{2},.*)', raw_data)
    if not match:
        return

    try:
        line = match.group(1).strip()
        row = next(csv.reader(StringIO(line)))

        # Ensure we have at least 30 fields (pad with empty strings)
        while len(row) < 30:
            row.append('')

        # Extract fields with safe parsing
        call_start   = row[0]
        duration     = row[1]
        ring_time    = int(row[2]) if row[2].strip().isdigit() else 0
        caller       = row[3]
        direction    = "Inbound" if row[4] == "I" else "Outbound"
        called_num   = row[5]
        dialled_num  = row[6]
        account_code = row[7]
        is_int_raw   = int(row[8]) if row[8].strip().isdigit() else 0
        call_id      = int(row[9]) if row[9].strip().isdigit() else None
        continuation = int(row[10]) if row[10].strip().isdigit() else 0
        party1_dev   = row[11]
        party1_name  = row[12]
        party2_dev   = row[13]
        party2_name  = row[14]
        hold_time    = int(row[15]) if row[15].strip().isdigit() else 0
        park_time    = int(row[16]) if row[16].strip().isdigit() else 0
        auth_valid   = int(row[17]) if row[17].strip().isdigit() else 0
        auth_code    = row[18] if row[18] != 'n/a' else None

        # Calculate duration in seconds
        h, m, s = map(int, duration.split(':'))
        sec = (h * 3600) + (m * 60) + s

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO calls 
                (call_start, duration_raw, duration_seconds, ring_time,
                 caller, direction, called_num, dialled_num, account_code,
                 is_internal, call_id, continuation, party1_device, party1_name,
                 party2_device, party2_name, hold_time, park_time,
                 auth_valid, auth_code, cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (call_start, duration, sec, ring_time,
                  caller, direction, called_num, dialled_num, account_code,
                  is_int_raw, call_id, continuation, party1_dev, party1_name,
                  party2_dev, party2_name, hold_time, park_time,
                  auth_valid, auth_code, 0.0))
        print(f"[SAVED] {party1_name} | {caller} -> {called_num}")

    except Exception as e:
        print(f"[!] Parse Error: {e}")

# -------------------------------------------------------------------
# TCP LISTENER – RECEIVES SMDR STREAM FROM AVAYA
# -------------------------------------------------------------------
def tcp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((LISTEN_IP, LISTEN_PORT))
        sock.listen(5)
        print(f"[LISTENING] TCP port {LISTEN_PORT}")
        while True:
            client, addr = sock.accept()
            print(f"[CONNECTED] {addr}")
            data = client.recv(4096).decode('utf-8', errors='ignore')
            if data:
                parse_and_save(data)
            client.close()
    except Exception as e:
        print(f"[LISTENER ERROR] {e}")
        threading.Event().wait(5)

# -------------------------------------------------------------------
# MAIN DASHBOARD ROUTE WITH FILTERS AND SUMMARY
# -------------------------------------------------------------------
@app.route('/')
def index():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This makes rows behave like dictionaries
    cursor = conn.cursor()

    conditions = []
    params = []

    if start_date:
        start_date_formatted = start_date.replace('-', '/')
        conditions.append("call_start >= ?")
        params.append(start_date_formatted + " 00:00:00")
    if end_date:
        end_date_formatted = end_date.replace('-', '/')
        conditions.append("call_start <= ?")
        params.append(end_date_formatted + " 23:59:59")
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

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Fetch calls as dictionaries
    query = f"""
        SELECT id, call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost
        FROM calls
        {where_clause}
        ORDER BY id DESC
        LIMIT 100
    """
    cursor.execute(query, params)
    calls = cursor.fetchall()

    # Summary statistics (same filters)
    summary_query = f"""
        SELECT
            COUNT(*) as total_calls,
            SUM(duration_seconds) as total_seconds,
            AVG(duration_seconds) as avg_seconds,
            SUM(ring_time) as total_ring,
            SUM(hold_time) as total_hold,
            SUM(cost) as total_cost
        FROM calls
        {where_clause}
    """
    cursor.execute(summary_query, params)
    stats = cursor.fetchone()
    conn.close()

    # Format summary
    total_calls = stats['total_calls'] or 0
    total_duration = str(timedelta(seconds=stats['total_seconds'] or 0))
    avg_duration = str(timedelta(seconds=int(stats['avg_seconds'] or 0)))
    total_ring = str(timedelta(seconds=stats['total_ring'] or 0))
    total_hold = str(timedelta(seconds=stats['total_hold'] or 0))
    total_cost = round(stats['total_cost'] or 0, 2)

    summary = {
        'total_calls': total_calls,
        'total_duration': total_duration,
        'avg_duration': avg_duration,
        'total_ring': total_ring,
        'total_hold': total_hold,
        'total_cost': total_cost
    }

    return render_template('index.html',
                           records=calls,
                           summary=summary,
                           filters={
                               'start_date': start_date,
                               'end_date': end_date,
                               'direction': direction,
                               'is_internal': is_internal,
                               'search': search
                           })

# -------------------------------------------------------------------
# DEBUG ROUTE – CHECK DATABASE CONTENT
# -------------------------------------------------------------------
@app.route('/raw')
def raw_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM calls")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT * FROM calls ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    output = f"Path: {DB_PATH}\nTotal records: {count}\n\n"
    for row in rows:
        output += f"{row}\n"
    return f"<pre>{output}</pre>"



@app.route('/reports')
def reports():
    """Show available report templates"""
    return render_template('reports.html')


@app.route('/report/<report_type>')
def generate_report(report_type):
    # Initialize filter variables from request arguments
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    # Build WHERE clause
    conditions = []
    params = []

    if start_date:
        start_date_formatted = start_date.replace('-', '/')
        conditions.append("call_start >= ?")
        params.append(start_date_formatted + " 00:00:00")
    if end_date:
        end_date_formatted = end_date.replace('-', '/')
        conditions.append("call_start <= ?")
        params.append(end_date_formatted + " 23:59:59")
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

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ----- Report Types -----
    if report_type == 'daily_summary':
        query = f"""
            SELECT DATE(call_start) as date,
                   COUNT(*) as total_calls,
                   SUM(duration_seconds) as total_sec,
                   SUM(ring_time) as total_ring,
                   SUM(hold_time) as total_hold,
                   SUM(cost) as total_cost
            FROM calls
            {where_clause}
            GROUP BY DATE(call_start)
            ORDER BY date DESC
            LIMIT 30
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring Time (sec)', 'Hold Time (sec)', 'Cost ($)']
        title = 'Daily Call Summary'

    elif report_type == 'top_callers':
        query = f"""
            SELECT caller, COUNT(*) as call_count,
                   SUM(duration_seconds) as total_sec,
                   SUM(cost) as total_cost
            FROM calls
            {where_clause}
            GROUP BY caller
            ORDER BY call_count DESC
            LIMIT 20
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Caller', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
        title = 'Top Callers'

    elif report_type == 'top_called':
        query = f"""
            SELECT called_num, COUNT(*) as call_count,
                   SUM(duration_seconds) as total_sec,
                   SUM(cost) as total_cost
            FROM calls
            {where_clause}
            GROUP BY called_num
            ORDER BY call_count DESC
            LIMIT 20
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Called Number', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
        title = 'Top Called Numbers'

    elif report_type == 'hourly_distribution':
        query = f"""
            SELECT strftime('%H', call_start) as hour,
                   COUNT(*) as total_calls,
                   SUM(duration_seconds) as total_sec
            FROM calls
            {where_clause}
            GROUP BY hour
            ORDER BY hour
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        headers = ['Hour', 'Total Calls', 'Total Talk Time (sec)']
        title = 'Hourly Call Distribution'

    elif report_type == 'cost_by_prefix':
        # Get tariff rates
        cursor.execute("SELECT prefix, rate_per_minute FROM tariffs")
        tariffs = cursor.fetchall()

        # Build query with proper WHERE handling
        if conditions:
            query = f"""
                SELECT called_num, duration_seconds
                FROM calls
                WHERE {" AND ".join(conditions)} AND is_internal = 0
            """
        else:
            query = """
                SELECT called_num, duration_seconds
                FROM calls
                WHERE is_internal = 0
            """
        cursor.execute(query, params)
        call_rows = cursor.fetchall()

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
        title = 'Cost by Tariff Prefix'

    else:
        conn.close()
        return "Invalid report type", 400

    conn.close()
    return render_template('report_view.html',
                           report_type=report_type,
                           report_title=title,
                           headers=headers,
                           rows=rows,
                           filters=request.args)


@app.route('/report/<report_type>/export/csv')
def export_csv(report_type):
    # Re-generate report data (similar to above but without HTML)
    # For simplicity, we'll reuse the generate_report logic but output CSV.
    # Alternatively, you can factor out a function to get report data.
    # We'll duplicate logic here for clarity.

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    conditions = []
    params = []
    if start_date:
        conditions.append("call_start >= ?")
        params.append(start_date + " 00:00:00")
    if end_date:
        conditions.append("call_start <= ?")
        params.append(end_date + " 23:59:59")
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
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Similar queries as above
    if report_type == 'daily_summary':
        query = f"""
            SELECT DATE(call_start) as date, COUNT(*), SUM(duration_seconds),
                   SUM(ring_time), SUM(hold_time), SUM(cost)
            FROM calls {where_clause}
            GROUP BY DATE(call_start) ORDER BY date DESC LIMIT 30
        """
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring Time (sec)', 'Hold Time (sec)', 'Cost ($)']
    elif report_type == 'top_callers':
        query = f"""
            SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
            FROM calls {where_clause}
            GROUP BY caller ORDER BY COUNT(*) DESC LIMIT 20
        """
        headers = ['Caller', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
    elif report_type == 'top_called':
        query = f"""
            SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
            FROM calls {where_clause}
            GROUP BY called_num ORDER BY COUNT(*) DESC LIMIT 20
        """
        headers = ['Called Number', 'Call Count', 'Total Talk Time (sec)', 'Total Cost ($)']
    elif report_type == 'hourly_distribution':
        query = f"""
            SELECT strftime('%H', call_start) as hour, COUNT(*), SUM(duration_seconds)
            FROM calls {where_clause}
            GROUP BY hour ORDER BY hour
        """
        headers = ['Hour', 'Total Calls', 'Total Talk Time (sec)']
    elif report_type == 'cost_by_prefix':
        cursor.execute("SELECT prefix, rate_per_minute FROM tariffs")
        tariffs = cursor.fetchall()
        query = f"""
            SELECT called_num, duration_seconds
            FROM calls {where_clause} AND is_internal = 0
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        prefix_costs = {}
        for called_num, dur_sec in rows:
            matched_prefix = 'local'
            max_len = 0
            for prefix, rate in tariffs:
                if called_num.startswith(prefix) and len(prefix) > max_len:
                    matched_prefix = prefix
                    max_len = len(prefix)
            minutes = dur_sec / 60.0
            cost = minutes * (dict(tariffs).get(matched_prefix, 1.0))
            prefix_costs[matched_prefix] = prefix_costs.get(matched_prefix, 0) + cost
        rows = [(prefix, round(cost,2)) for prefix, cost in prefix_costs.items()]
        headers = ['Prefix', 'Total Cost ($)']
        # Direct CSV generation
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(headers)
        cw.writerows(rows)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    else:
        return "Invalid report type", 400

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    cw.writerows(rows)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output



@app.route('/report/<report_type>/export/pdf')
def export_pdf(report_type):
    # Reuse data generation (same as CSV but output PDF)
    # For brevity, we'll call export_csv logic and then convert to PDF.
    # Better: refactor to a common data fetcher. Here's a direct implementation.

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    conditions = []
    params = []
    if start_date:
        conditions.append("call_start >= ?")
        params.append(start_date + " 00:00:00")
    if end_date:
        conditions.append("call_start <= ?")
        params.append(end_date + " 23:59:59")
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
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Define query and headers per type (similar to CSV)
    if report_type == 'daily_summary':
        query = f"""
            SELECT DATE(call_start) as date, COUNT(*), SUM(duration_seconds),
                   SUM(ring_time), SUM(hold_time), SUM(cost)
            FROM calls {where_clause}
            GROUP BY DATE(call_start) ORDER BY date DESC LIMIT 30
        """
        headers = ['Date', 'Total Calls', 'Talk Time (sec)', 'Ring (sec)', 'Hold (sec)', 'Cost ($)']
        title = "Daily Call Summary"
    elif report_type == 'top_callers':
        query = f"""
            SELECT caller, COUNT(*), SUM(duration_seconds), SUM(cost)
            FROM calls {where_clause}
            GROUP BY caller ORDER BY COUNT(*) DESC LIMIT 20
        """
        headers = ['Caller', 'Call Count', 'Talk Time (sec)', 'Cost ($)']
        title = "Top Callers"
    elif report_type == 'top_called':
        query = f"""
            SELECT called_num, COUNT(*), SUM(duration_seconds), SUM(cost)
            FROM calls {where_clause}
            GROUP BY called_num ORDER BY COUNT(*) DESC LIMIT 20
        """
        headers = ['Called Number', 'Call Count', 'Talk Time (sec)', 'Cost ($)']
        title = "Top Called Numbers"
    elif report_type == 'hourly_distribution':
        query = f"""
            SELECT strftime('%H', call_start) as hour, COUNT(*), SUM(duration_seconds)
            FROM calls {where_clause}
            GROUP BY hour ORDER BY hour
        """
        headers = ['Hour', 'Total Calls', 'Talk Time (sec)']
        title = "Hourly Call Distribution"
    elif report_type == 'cost_by_prefix':
        cursor.execute("SELECT prefix, rate_per_minute FROM tariffs")
        tariffs = cursor.fetchall()
        query = f"""
            SELECT called_num, duration_seconds
            FROM calls {where_clause} AND is_internal = 0
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        prefix_costs = {}
        for called_num, dur_sec in rows:
            matched_prefix = 'local'
            max_len = 0
            for prefix, rate in tariffs:
                if called_num.startswith(prefix) and len(prefix) > max_len:
                    matched_prefix = prefix
                    max_len = len(prefix)
            minutes = dur_sec / 60.0
            cost = minutes * (dict(tariffs).get(matched_prefix, 1.0))
            prefix_costs[matched_prefix] = prefix_costs.get(matched_prefix, 0) + cost
        data = [[prefix, f"${cost:.2f}"] for prefix, cost in prefix_costs.items()]
        headers = ['Prefix', 'Total Cost']
        title = "Cost by Tariff Prefix"
        # Generate PDF directly
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, fontSize=16)
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.2*inch))
        # Create table
        table_data = [headers] + data
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(t)
        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')
    else:
        return "Invalid report type", 400

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    # Convert rows to list of lists (with formatting)
    data = [list(row) for row in rows]
    # Format numbers if needed
    # For daily summary, format duration from seconds to HH:MM:SS? We'll keep raw for simplicity.

    # Generate PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, fontSize=16)
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 0.2*inch))
    # Add filter info
    filter_text = f"Filters: {start_date or 'Any'} to {end_date or 'Any'}"
    elements.append(Paragraph(filter_text, styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))

    table_data = [headers] + data
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')


@app.route('/export/calls/csv')
def export_calls_csv():
    # Reuse filter parameters from the dashboard
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    conditions = []
    params = []

    if start_date:
        start_date_formatted = start_date.replace('-', '/')
        conditions.append("call_start >= ?")
        params.append(start_date_formatted + " 00:00:00")
    if end_date:
        end_date_formatted = end_date.replace('-', '/')
        conditions.append("call_start <= ?")
        params.append(end_date_formatted + " 23:59:59")
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

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = f"""
        SELECT call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost
        FROM calls
        {where_clause}
        ORDER BY id DESC
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
        # Convert internal flag to readable text
        row_list = list(row)
        row_list[6] = 'Yes' if row[6] else 'No'
        cw.writerow(row_list)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=call_details.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route('/export/calls/pdf')
def export_calls_pdf():
    # Reuse same filter logic as above
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    conditions = []
    params = []

    if start_date:
        start_date_formatted = start_date.replace('-', '/')
        conditions.append("call_start >= ?")
        params.append(start_date_formatted + " 00:00:00")
    if end_date:
        end_date_formatted = end_date.replace('-', '/')
        conditions.append("call_start <= ?")
        params.append(end_date_formatted + " 23:59:59")
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

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = f"""
        SELECT call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost
        FROM calls
        {where_clause}
        ORDER BY id DESC
    """
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    # Convert rows to list of lists with formatted internal flag
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
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, fontSize=14)
    elements.append(Paragraph("Avaya Call Details Report", title_style))
    elements.append(Spacer(1, 0.2*inch))

    # Add filter summary
    filter_text = f"Filters: {start_date or 'Any'} to {end_date or 'Any'} | Dir: {direction or 'All'} | Type: {is_internal or 'All'}"
    elements.append(Paragraph(filter_text, styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))

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
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="call_details.pdf", mimetype='application/pdf')

# -------------------------------------------------------------------
# START APPLICATION
# -------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    threading.Thread(target=tcp_listener, daemon=True).start()
    print("[WEB] Running on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)