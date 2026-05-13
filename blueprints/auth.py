import os
import json
import tempfile
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import send_file
from models.settings import get_pabx_servers, get_pabx_status, get_setting

import sqlite3
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, abort, make_response)
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
from werkzeug.security import check_password_hash
from models.user import (get_user_by_username, create_user, delete_user,
                         get_all_users, get_user_by_id, update_user,
                         update_user_email, update_user_email_preferences)
from extensions import login_manager
from models.settings import get_all_settings, update_settings, set_setting
from models.database import get_db
from models.audit import log_action, get_audit_logs, get_all_audit_logs
from models.user import get_active_users, force_logout_user

from models.settings import (get_all_settings, update_settings, set_setting,
                             get_pabx_servers, add_pabx_server, remove_pabx_server)
from models.settings import get_pabx_status, get_pabx_servers

import subprocess, platform
from services.email_sender import send_email

auth_bp = Blueprint('auth', __name__)

class User:
    def __init__(self, id, username, role, extension=None,
                 email_reports_enabled=False, email_alerts_enabled=False):
        self.id = id
        self.username = username
        self.role = role
        self.extension = extension
        self.email_reports_enabled = email_reports_enabled
        self.email_alerts_enabled = email_alerts_enabled

    @property
    def is_authenticated(self):
        return True
    @property
    def is_active(self):
        return True
    @property
    def is_anonymous(self):
        return False
    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(current_app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, role, extension,
               COALESCE(email_reports_enabled, 0),
               COALESCE(email_alerts_enabled, 0)
        FROM users WHERE id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(row[0], row[1], row[2], row[3],
                    row[4] == 1, row[5] == 1)
    return None

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = get_user_by_username(username)
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data['id'], user_data['username'], user_data['role'], user_data['extension'])
            login_user(user)
            log_action(user.id, "Logged in")
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    log_action(current_user.id, "Logged out")
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# ---------- User Management ----------
@auth_bp.route('/admin/users')
@admin_required
def list_users():
    users = get_all_users()
    return render_template('users.html', users=users)

@auth_bp.route('/admin/users/add', methods=['POST'])
@admin_required
def add_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'viewer')
    extension = request.form.get('extension', '').strip() or None
    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('auth.list_users'))
    try:
        create_user(username, password, role, extension)
        flash('User added successfully.', 'success')
        log_action(current_user.id, f"Added user '{username}' with role {role}")
    except Exception as e:
        flash(f'Error adding user: {e}', 'danger')
    return redirect(url_for('auth.list_users'))

@auth_bp.route('/admin/users/delete/<int:user_id>')
@admin_required
def delete_user_route(user_id):
    if current_user.id == user_id:
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('auth.list_users'))
    log_action(current_user.id, f"Deleted user ID {user_id}")
    delete_user(user_id)
    flash('User deleted.', 'info')
    return redirect(url_for('auth.list_users'))

@auth_bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        update_settings({
            'smdr_ip': request.form.get('smdr_ip', '0.0.0.0'),
            'smdr_port': request.form.get('smdr_port', '9001'),
            'web_host': request.form.get('web_host', '0.0.0.0'),
            'web_port': request.form.get('web_port', '5000'),
            'company_name': request.form.get('company_name', 'Avaya CDR').strip(),
            'company_logo_url': request.form.get('company_logo_url', '').strip(),
            'pabx_online_timeout_minutes': request.form.get('pabx_online_timeout_minutes', '15').strip() or '15',
            'pabx_check_interval_minutes': request.form.get('pabx_check_interval_minutes', '5').strip() or '5',
            'smtp_host': request.form.get('smtp_host', '').strip(),
            'smtp_port': request.form.get('smtp_port', '587').strip() or '587',
            'smtp_use_tls': '1' if request.form.get('smtp_use_tls') else '0',
            'smtp_protocol': request.form.get('smtp_protocol', 'starttls').strip(),
            'smtp_verify_cert': '1' if request.form.get('smtp_verify_cert') else '0',
            'smtp_username': request.form.get('smtp_username', '').strip(),
            'smtp_password': request.form.get('smtp_password', '').strip(),
            'smtp_from_email': request.form.get('smtp_from_email', '').strip(),
            'smtp_from_name': request.form.get('smtp_from_name', 'Avaya CDR').strip()
        })
        log_action(current_user.id, "Updated system settings")
        flash('Settings saved. Restart the application for changes to take effect.', 'success')
        return redirect(url_for('auth.settings'))
    return render_template('settings.html', settings=get_all_settings(), pabx_servers=get_pabx_servers())

@auth_bp.route('/admin/audit')
@admin_required
def view_audit():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    logs, total = get_audit_logs(page, per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('audit.html', logs=logs, page=page, total_pages=total_pages, total=total)

@auth_bp.route('/admin/audit/download/csv')
@admin_required
def download_audit_csv():
    from io import StringIO
    import csv
    logs = get_all_audit_logs()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Timestamp', 'User', 'Action', 'IP Address'])
    for log in logs:
        cw.writerow([log[4], log[1] or 'N/A', log[2], log[3]])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=audit_log.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@auth_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.list_users'))
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        role = request.form['role']
        extension = request.form['extension'].strip() or None
        if password and password != password_confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('edit_user.html', user=user)
        if password:
            update_user(user_id, password=password)
        if role:
            update_user(user_id, role=role)
        if extension is not None:
            update_user(user_id, extension=extension)
        reports_enabled = request.form.get('email_reports_enabled') == 'on'
        alerts_enabled  = request.form.get('email_alerts_enabled') == 'on'
        update_user_email_preferences(user_id, reports_enabled=reports_enabled, alerts_enabled=alerts_enabled)
        email = request.form.get('email', '').strip()
        if email:
            update_user_email(user_id, email)
        log_action(current_user.id,
                   f"Edited user '{user['username']}': role={role}, extension={extension}, password={'changed' if password else 'unchanged'}")
        flash('User updated successfully.', 'success')
        return redirect(url_for('auth.list_users'))
    return render_template('edit_user.html', user=user)

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html')
        user_data = get_user_by_id(current_user.id)
        if not user_data or not check_password_hash(user_data['password_hash'], current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')
        update_user(current_user.id, password=new_password)
        log_action(current_user.id, "Changed own password")
        flash('Password changed successfully.', 'success')
        return redirect(url_for('dashboard.index'))
    return render_template('change_password.html')

@auth_bp.route('/admin/maintenance', methods=['GET', 'POST'])
@admin_required
def maintenance():
    db_path = current_app.config['DATABASE']
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    db_size_mb = round(db_size / (1024 * 1024), 2)
    db_mtime = datetime.fromtimestamp(os.path.getmtime(db_path)).strftime('%Y-%m-%d %H:%M:%S') if os.path.exists(db_path) else 'N/A'
    log_path = current_app.config.get('LOG_FILE', '')
    log_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    log_size_kb = round(log_size / 1024, 2)
    log_content = ""
    all_settings = get_all_settings()
    backup_path = all_settings.get('backup_path', '')
    backup_interval = all_settings.get('backup_interval_hours', '24')
    last_backup_time = all_settings.get('last_backup_time', '')
    last_backup_status = all_settings.get('last_backup_status', '')
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'backup_db':
            return send_file(db_path, as_attachment=True, download_name='smdr_records_backup.db', mimetype='application/octet-stream')
        elif action == 'backup_config':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            settings = {row['key']: row['value'] for row in cursor.fetchall()}
            cursor.execute("SELECT prefix, description, rate_per_minute FROM tariffs")
            tariffs = [{'prefix': row['prefix'], 'description': row['description'], 'rate': row['rate_per_minute']} for row in cursor.fetchall()]
            cursor.execute("SELECT username, password_hash, role, extension FROM users")
            users = [{'username': row['username'], 'password_hash': row['password_hash'], 'role': row['role'], 'extension': row['extension']} for row in cursor.fetchall()]
            conn.close()
            config_data = {'settings': settings, 'tariffs': tariffs, 'users': users, 'exported_at': datetime.now().isoformat()}
            fd, tmp_path = tempfile.mkstemp(suffix='.json')
            with os.fdopen(fd, 'w') as f:
                json.dump(config_data, f, indent=2)
            return send_file(tmp_path, as_attachment=True, download_name='avaya_cdr_config_backup.json', mimetype='application/json')
        # ... (rest of maintenance actions unchanged, keep them exactly as before) ...
    uptime = datetime.now() - current_app.config['START_TIME']
    uptime_str = str(uptime).split('.')[0]
    log_lines = 250
    return render_template('maintenance.html', db_size_mb=db_size_mb, db_mtime=db_mtime,
                           backup_path=backup_path, backup_interval=backup_interval,
                           last_backup_time=last_backup_time, last_backup_status=last_backup_status,
                           log_path=log_path, log_size_kb=log_size_kb, log_content=log_content,
                           log_lines=log_lines, uptime_str=uptime_str)

# Save the rest of the maintenance actions (restore_db, restore_config, etc.) exactly as they were.
# I'll skip repeating them for brevity – keep YOUR existing code inside that if/elif block.
# ...

@auth_bp.route('/admin/restart')
@admin_required
def restart_app():
    log_action(current_user.id, "Restarted the application")
    flash('Application is restarting...', 'info')
    import os, signal, threading, time
    def shutdown():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=shutdown).start()
    return redirect(url_for('auth.maintenance'))

@auth_bp.route('/admin/sessions')
@admin_required
def active_sessions():
    active_users = get_active_users()
    return render_template('active_sessions.html', active_users=active_users)

@auth_bp.route('/admin/sessions/force_logout/<int:user_id>')
@admin_required
def force_logout_route(user_id):
    if user_id == current_user.id:
        flash('You cannot force-logout yourself.', 'danger')
        return redirect(url_for('auth.active_sessions'))
    force_logout_user(user_id)
    log_action(current_user.id, f"Forcefully logged out user ID {user_id}")
    flash('User will be logged out on their next request.', 'success')
    return redirect(url_for('auth.active_sessions'))

@auth_bp.route('/admin/settings/add_pabx', methods=['POST'])
@admin_required
def add_pabx():
    name = request.form.get('pabx_name', '').strip()
    ip = request.form.get('pabx_ip', '').strip()
    monitor_port = request.form.get('monitor_port', '80').strip() or '80'
    if not name or not ip:
        flash('Name and IP are required.', 'danger')
    else:
        if add_pabx_server(name, ip, int(monitor_port)):
            flash('PABX server added.', 'success')
        else:
            flash('Server with that IP already exists.', 'danger')
    return redirect(url_for('auth.settings'))

@auth_bp.route('/admin/settings/delete_pabx/<ip>')
@admin_required
def delete_pabx(ip):
    remove_pabx_server(ip)
    flash('Server removed.', 'info')
    return redirect(url_for('auth.settings'))

# ---------- My Preferences ----------
@auth_bp.route('/my_preferences', methods=['GET', 'POST'])
@login_required
def my_preferences():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        update_user_email(current_user.id, email)
        reports_enabled = request.form.get('email_reports_enabled') == 'on'
        alerts_enabled  = request.form.get('email_alerts_enabled') == 'on'
        update_user_email_preferences(current_user.id, reports_enabled=reports_enabled, alerts_enabled=alerts_enabled)
        flash('Email preferences saved.', 'success')
        log_action(current_user.id, "Updated email preferences")
        return redirect(url_for('auth.my_preferences'))
    user_data = get_user_by_id(current_user.id)
    return render_template('my_preferences.html', user=user_data)

# ---------- Manual Email Report ----------
@auth_bp.route('/email_report_manual')
@login_required
def email_report_manual():
    from io import BytesIO
    report_type = request.args.get('report_type', '')
    file_format = request.args.get('format', 'pdf')
    user_data = get_user_by_id(current_user.id)
    to_email = user_data[5] if user_data and len(user_data) > 5 else ''
    if not to_email:
        flash('You have no email address set. Please update your preferences.', 'warning')
        return redirect(request.referrer or url_for('reports.reports'))

    # Build query string from current parameters (excluding format)
    params = dict(request.args)
    params.pop('format', None)
    params.pop('report_type', None)
    query_string = '&'.join(f"{k}={v}" for k, v in params.items() if v)

    # Use Flask test client to call the export route (authenticated)
    with current_app.test_client() as client:
        # Simulate login
        with client.session_transaction() as sess:
            sess['_user_id'] = str(current_user.id)
            sess['_fresh'] = True
        url = f'/report/{report_type}/export/{file_format}'
        if query_string:
            url += '?' + query_string
        resp = client.get(url, follow_redirects=True)

    if resp.status_code != 200:
        flash('Failed to generate the report for email.', 'danger')
        return redirect(request.referrer or url_for('reports.reports'))

    buffer = BytesIO(resp.data)
    filename = f"{report_type}_report.{file_format}"
    mime = 'application/pdf' if file_format == 'pdf' else 'text/csv'

    subject = f"Avaya CDR Report: {report_type.replace('_', ' ').title()}"
    body = f"""
    <html><body>
    <h3>{report_type.replace('_', ' ').title()} Report</h3>
    <p>Please find attached your requested report.</p>
    <p><small>Generated by Avaya CDR on {datetime.now().strftime('%Y-%m-%d %H:%M')}</small></p>
    </body></html>
    """
    success = send_email(to_email, subject, body, attachments=[(filename, buffer, mime)], user_id=current_user.id)
    if success:
        flash(f'Report emailed to {to_email}.', 'success')
    else:
        flash('Failed to send email. Check SMTP settings.', 'danger')
    return redirect(request.referrer or url_for('reports.reports'))

# ---------- User Schedule (admin) ----------
# ---------- User Schedule (admin) ----------
@auth_bp.route('/admin/users/schedule/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def user_schedule(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.list_users'))

    report_types = [
        ('daily_summary', 'Daily Summary'),
        ('top_callers', 'Top Callers'),
        ('top_called', 'Top Called Numbers'),
        ('hourly_distribution', 'Hourly Distribution'),
        ('extension_usage', 'Extension Usage'),
        ('ring_time', 'Ring Time'),
        ('abandoned', 'Abandoned Calls'),
        ('heatmap', 'Call Heatmap'),
        ('trunk_usage', 'Trunk Usage'),
        ('duration_distribution', 'Duration Distribution'),
        ('abandoned_trend', 'Abandoned Trend'),
        ('outcome_summary', 'Outcome Summary'),
    ]

    if request.method == 'POST':
        report_type = request.form.get('report_type', '')
        frequency = request.form.get('frequency', 'daily')
        schedule_time = request.form.get('schedule_time', '08:00')
        enabled = request.form.get('enabled') == 'on'

        if frequency == 'daily':
            schedule_day = 0
        elif frequency == 'weekly':
            schedule_day = int(request.form.get('schedule_day', '1'))
        elif frequency == 'monthly':
            schedule_day = int(request.form.get('schedule_day', '1'))
        else:
            schedule_day = 0

        filters = {
            'start_date': request.form.get('start_date', '').strip(),
            'end_date': request.form.get('end_date', '').strip(),
            'direction': request.form.get('direction', '').strip(),
            'is_internal': request.form.get('is_internal', '').strip(),
            'search': request.form.get('search', '').strip(),
        }
        filter_json = json.dumps(filters)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM report_subscriptions WHERE user_id = ? AND report_type = ?", (user_id, report_type))
        if enabled:
            cursor.execute(
                "INSERT INTO report_subscriptions (user_id, report_type, frequency, schedule_day, schedule_time, enabled, filter_params) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (user_id, report_type, frequency, schedule_day, schedule_time, filter_json)
            )
        conn.commit()
        conn.close()
        flash('Schedule updated.', 'success')
        return redirect(url_for('auth.user_schedule', user_id=user_id))

    # ---------- GET ----------
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM report_subscriptions WHERE user_id = ?", (user_id,))
    raw_subs = cursor.fetchall()
    conn.close()

    subscriptions = []                          # ← THIS was missing in your file
    for sub in raw_subs:
        d = dict(sub)
        filters = {}
        if d.get('filter_params'):
            try:
                filters = json.loads(d['filter_params'])
            except:
                pass
        d['filters'] = filters
        subscriptions.append(d)

    return render_template('user_schedule.html',
                           user=user,
                           subscriptions=subscriptions,
                           report_types=report_types)

   

# ---------- Live PABX ping ----------
@auth_bp.route('/admin/ping_pabx')
@admin_required
def ping_pabx():
    import socket
    server_list = get_pabx_servers()
    results = []
    for s in server_list:
        ip = s['ip']
        port = int(s.get('monitor_port', 80))
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((ip, port))
            sock.close()
            results.append(f"{s['name']} ({ip}) is reachable")
        except Exception:
            results.append(f"{s['name']} ({ip}) is NOT reachable")
    all_ok = all('reachable' in r for r in results)
    return {'success': all_ok, 'message': ' | '.join(results)}

# ---------- System Health Helper (unchanged) ----------
# ---------- System Health Helper (RESTORED) ----------
def get_system_health():
    health = {
        'cpu_percent': None,
        'memory_percent': None,
        'disk_percent': None,
        'disk_total_gb': None,
        'disk_used_gb': None,
        'disk_free_gb': None,
        'uptime_str': 'N/A',
        'overall': 'Unknown',
        'overall_color': 'secondary'
    }
    try:
        import psutil
        health['cpu_percent'] = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        health['memory_percent'] = mem.percent
        app_path = os.path.abspath(current_app.root_path)
        disk = psutil.disk_usage(app_path)
        health['disk_percent'] = disk.percent
        health['disk_total_gb'] = round(disk.total / (1024**3), 1)
        health['disk_used_gb'] = round(disk.used / (1024**3), 1)
        health['disk_free_gb'] = round(disk.free / (1024**3), 1)
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime_delta = datetime.now() - boot_time
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        health['uptime_str'] = f"{days}d {hours}h {minutes}m"
        cpu = health['cpu_percent']; mem_pct = health['memory_percent']; disk_pct = health['disk_percent']
        if cpu > 90 or mem_pct > 90 or disk_pct > 90:
            health['overall'] = 'Critical'; health['overall_color'] = 'danger'
        elif cpu > 75 or mem_pct > 75 or disk_pct > 80:
            health['overall'] = 'Warning'; health['overall_color'] = 'warning'
        else:
            health['overall'] = 'Healthy'; health['overall_color'] = 'success'
    except ImportError:
        system = platform.system()
        cpu = None
        if system == 'Windows':
            try:
                output = subprocess.check_output(['wmic', 'cpu', 'get', 'loadpercentage'], universal_newlines=True)
                lines = [line.strip() for line in output.split('\n') if line.strip()]
                if len(lines) >= 2: cpu = float(lines[1]); health['cpu_percent'] = min(100, cpu)
            except: pass
        else:
            try:
                with open('/proc/loadavg', 'r') as f:
                    load = f.readline().split()[0]
                    cores = os.cpu_count() or 2
                    cpu = min(100, round((float(load) / cores) * 100, 1))
                    health['cpu_percent'] = cpu
            except: pass
        if cpu is None: health['cpu_percent'] = 'N/A'

        mem_pct = None
        if system == 'Windows':
            try:
                out = subprocess.check_output(['wmic', 'OS', 'get', 'TotalVisibleMemorySize,FreePhysicalMemory', '/Value'], universal_newlines=True)
                total_kb = free_kb = None
                for line in out.split('\n'):
                    line = line.strip()
                    if line.startswith('TotalVisibleMemorySize='): total_kb = int(line.split('=')[1])
                    elif line.startswith('FreePhysicalMemory='): free_kb = int(line.split('=')[1])
                if total_kb and free_kb:
                    used_kb = total_kb - free_kb
                    mem_pct = round((used_kb / total_kb) * 100, 1)
                    health['memory_percent'] = mem_pct
            except: pass
        else:
            try:
                with open('/proc/meminfo', 'r') as f: lines = f.readlines()
                meminfo = {}
                for line in lines:
                    if ':' in line:
                        k, v = line.split(':', 1)
                        try: meminfo[k.strip()] = int(v.strip().split(' ')[0])
                        except: pass
                total = meminfo.get('MemTotal', 1)
                avail = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
                if total: mem_pct = round(((total - avail) / total) * 100, 1); health['memory_percent'] = mem_pct
            except: pass
        if mem_pct is None: health['memory_percent'] = 'N/A'

        try:
            import shutil
            total, used, free = shutil.disk_usage(current_app.root_path)
            health['disk_percent'] = round((used / total) * 100, 1)
            health['disk_total_gb'] = round(total / (1024**3), 1)
            health['disk_used_gb'] = round(used / (1024**3), 1)
            health['disk_free_gb'] = round(free / (1024**3), 1)
        except: health['disk_percent'] = 'N/A'

        uptime_delta = datetime.now() - current_app.config['START_TIME']
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        health['uptime_str'] = f"{days}d {hours}h {minutes}m (app)"

        cpu_val = mem_val = disk_val = 0
        try: cpu_val = float(health.get('cpu_percent', 0)) if health.get('cpu_percent') != 'N/A' else 0
        except: pass
        try: mem_val = float(health.get('memory_percent', 0)) if health.get('memory_percent') != 'N/A' else 0
        except: pass
        try: disk_val = float(health.get('disk_percent', 0)) if health.get('disk_percent') != 'N/A' else 0
        except: pass
        if cpu_val > 90 or mem_val > 90 or disk_val > 90:
            health['overall'] = 'Critical'; health['overall_color'] = 'danger'
        elif cpu_val > 75 or mem_val > 75 or disk_val > 80:
            health['overall'] = 'Warning'; health['overall_color'] = 'warning'
        else:
            health['overall'] = 'Healthy'; health['overall_color'] = 'success'
    return health


# ---------- Delete Subscription ----------
@auth_bp.route('/admin/users/subscription/delete/<int:sub_id>')
@admin_required
def delete_subscription(sub_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM report_subscriptions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    if row:
        user_id = row['user_id']
        cursor.execute("DELETE FROM report_subscriptions WHERE id = ?", (sub_id,))
        conn.commit()
        flash('Subscription deleted.', 'info')
        conn.close()
        return redirect(url_for('auth.user_schedule', user_id=user_id))
    conn.close()
    flash('Subscription not found.', 'danger')
    return redirect(url_for('auth.list_users'))


# ---------- Test Email ----------
@auth_bp.route('/admin/settings/test_email', methods=['POST'])
@admin_required
def test_email():
    to_email = request.form.get('to_email', '').strip()
    if not to_email:
        flash('Please enter a test email address.', 'warning')
        return redirect(url_for('auth.settings'))
    body = "<h3>Test Email from Avaya CDR</h3><p>Your SMTP settings are working correctly.</p>"
    success = send_email(to_email, "Test Email – Avaya CDR", body, user_id=current_user.id)
    if success:
        flash(f'Test email sent successfully to {to_email}.', 'success')
    else:
        flash('Failed to send test email. Check SMTP settings.', 'danger')
    return redirect(url_for('auth.settings'))


# ---------- SMTP Status Helper ----------
def get_smtp_status():
    import socket
    host = get_setting('smtp_host') or ''
    port = int(get_setting('smtp_port') or 587)
    connected = False
    error = ''
    if host:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            sock.close()
            connected = True
        except Exception as e:
            error = str(e)
    return {
        'host': host or 'Not configured',
        'port': port,
        'status': 'Connected' if connected else ('Not configured' if not host else 'Unreachable'),
        'connected_color': 'success' if connected else ('secondary' if not host else 'danger'),
        'connected_icon': 'check-circle-fill' if connected else ('dash-circle' if not host else 'exclamation-triangle-fill'),
        'error': error
    }


# ---------- System Status route (UPDATED) ----------
@auth_bp.route('/admin/status')
@admin_required
def system_status():
    server_list = get_pabx_servers()
    status_db = get_pabx_status() if server_list else {}
    now = datetime.now()
    timeout_minutes = int(get_setting('pabx_online_timeout_minutes') or 15)
    status_rows = []
    for s in server_list:
        ip = s['ip']
        info = status_db.get(ip, {})
        online = info.get('connected', False)
        last_seen_str = info.get('last_seen')
        if not online and last_seen_str:
            try:
                last_dt = datetime.strptime(last_seen_str, '%Y-%m-%d %H:%M:%S')
                online = (now - last_dt).total_seconds() <= timeout_minutes * 60
            except: pass
        status_rows.append({'name': s['name'], 'ip': ip, 'connected': online, 'last_seen': last_seen_str or 'Never'})
    system_health = get_system_health()
    smtp_status = get_smtp_status()
    return render_template('system_status.html', servers=status_rows, health=system_health, smtp=smtp_status)