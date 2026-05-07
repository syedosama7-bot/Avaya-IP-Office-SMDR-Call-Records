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
                         get_all_users, get_user_by_id, update_user)
from extensions import login_manager
from models.settings import get_all_settings, update_settings, set_setting
from models.database import get_db
from models.audit import log_action, get_audit_logs, get_all_audit_logs
from models.user import get_active_users, force_logout_user


from models.settings import (get_all_settings, update_settings, set_setting,
                             get_pabx_servers, add_pabx_server, remove_pabx_server)
from models.settings import get_pabx_status, get_pabx_servers

auth_bp = Blueprint('auth', __name__)

class User:
    def __init__(self, id, username, role, extension=None):
        self.id = id
        self.username = username
        self.role = role
        self.extension = extension

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
    cursor.execute("SELECT id, username, role, extension FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(row[0], row[1], row[2], row[3])
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
    log_action(current_user.id, "Logged out")   # log BEFORE clearing session
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

# ---------- Admin required decorator ----------
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# ---------- User Management (admin only) ----------
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
    # Log before deletion so we know which user was deleted
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
            'web_port': request.form.get('web_port', '5000')
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

        # Password confirmation check
        if password:
            if password != password_confirm:
                flash('Passwords do not match.', 'danger')
                return render_template('edit_user.html', user=user)

        if password:
            update_user(user_id, password=password)
        if role:
            update_user(user_id, role=role)
        if extension is not None:
            update_user(user_id, extension=extension)

        # Now log the action
        log_action(current_user.id,
                   f"Edited user '{user['username']}': role={role}, "
                   f"extension={extension}, password={'changed' if password else 'unchanged'}")
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

        # Verify current password
        user_data = get_user_by_id(current_user.id)
        if not user_data or not check_password_hash(user_data['password_hash'], current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')

        # Update password
        update_user(current_user.id, password=new_password)
        log_action(current_user.id, "Changed own password")
        flash('Password changed successfully. Please use the new password on your next login.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('change_password.html')


@auth_bp.route('/admin/maintenance', methods=['GET', 'POST'])
@admin_required
def maintenance():
    db_path = current_app.config['DATABASE']
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    db_size_mb = round(db_size / (1024 * 1024), 2)
    db_mtime = datetime.fromtimestamp(os.path.getmtime(db_path)).strftime('%Y-%m-%d %H:%M:%S') if os.path.exists(db_path) else 'N/A'

    # Log file
    log_path = current_app.config.get('LOG_FILE', '')
    log_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    log_size_kb = round(log_size / 1024, 2)
    log_content = ""

    # Fetch all settings early so they are available for both GET and POST
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
            config_data = {
                'settings': settings,
                'tariffs': tariffs,
                'users': users,
                'exported_at': datetime.now().isoformat()
            }
            fd, tmp_path = tempfile.mkstemp(suffix='.json')
            with os.fdopen(fd, 'w') as f:
                json.dump(config_data, f, indent=2)
            return send_file(tmp_path, as_attachment=True, download_name='avaya_cdr_config_backup.json', mimetype='application/json')

        elif action == 'restore_db':
            if 'db_file' not in request.files:
                flash('No file uploaded.', 'danger')
                return redirect(url_for('auth.maintenance'))
            file = request.files['db_file']
            if file.filename == '':
                flash('No file selected.', 'danger')
                return redirect(url_for('auth.maintenance'))
            if file and file.filename.endswith('.db'):
                try:
                    backup_path_db = db_path + '.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
                    os.rename(db_path, backup_path_db)   # keep the old file just in case
                    file.save(db_path)
                    flash('Database restored successfully. Please restart the application for the change to take effect.', 'success')
                except Exception as e:
                    flash(f'Restore failed: {str(e)}', 'danger')
                return redirect(url_for('auth.maintenance'))
            else:
                flash('Invalid file. Please upload a .db file.', 'danger')
                return redirect(url_for('auth.maintenance'))

        elif action == 'restore_config':
            if 'config_file' not in request.files:
                flash('No file uploaded.', 'danger')
                return redirect(url_for('auth.maintenance'))
            file = request.files['config_file']
            if file.filename == '':
                flash('No file selected.', 'danger')
                return redirect(url_for('auth.maintenance'))
            if file and file.filename.endswith('.json'):
                try:
                    data = json.load(file)
                    conn = get_db()
                    cursor = conn.cursor()
                    for key, value in data.get('settings', {}).items():
                        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
                    cursor.execute("DELETE FROM tariffs")
                    for t in data.get('tariffs', []):
                        cursor.execute("INSERT INTO tariffs (prefix, description, rate_per_minute) VALUES (?, ?, ?)",
                                       (t['prefix'], t['description'], t['rate']))
                    cursor.execute("DELETE FROM users")
                    for u in data.get('users', []):
                        cursor.execute("INSERT INTO users (username, password_hash, role, extension) VALUES (?, ?, ?, ?)",
                                       (u['username'], u['password_hash'], u['role'], u['extension']))
                    conn.commit()
                    conn.close()
                    flash('Configuration restored successfully. Some changes (like user accounts) may require a logout/login.', 'success')
                except Exception as e:
                    flash(f'Restore configuration failed: {str(e)}', 'danger')
                return redirect(url_for('auth.maintenance'))
            else:
                flash('Invalid file. Please upload a .json file.', 'danger')
                return redirect(url_for('auth.maintenance'))

        elif action == 'update_backup_schedule':
            new_path = request.form.get('backup_path', '').strip()
            new_interval = request.form.get('backup_interval_hours', '24')
            set_setting('backup_path', new_path)
            set_setting('backup_interval_hours', new_interval)
            flash('Backup schedule updated. The scheduler will pick up the new settings on the next cycle.', 'success')
            return redirect(url_for('auth.maintenance'))

        elif action == 'view_log':
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    log_content = ''.join(lines[-250:])
            # No return here – fall through to render template with log_content

        elif action == 'download_log':
            if os.path.exists(log_path):
                return send_file(log_path, as_attachment=True, download_name='avaya_cdr.log', mimetype='text/plain')

    uptime = datetime.now() - current_app.config['START_TIME']
    uptime_str = str(uptime).split('.')[0]  # remove microseconds


    log_lines = 250   # or any number you set
    return render_template('maintenance.html',
                           db_size_mb=db_size_mb,
                           db_mtime=db_mtime,
                           backup_path=backup_path,
                           backup_interval=backup_interval,
                           last_backup_time=last_backup_time,
                           last_backup_status=last_backup_status,
                           log_path=log_path,
                           log_size_kb=log_size_kb,
                           log_content=log_content,
                           log_lines=log_lines,
                           uptime_str=uptime_str)


@auth_bp.route('/admin/restart')
@admin_required
def restart_app():
    log_action(current_user.id, "Restarted the application")
    flash('Application is restarting...', 'info')
    # Schedule the actual shutdown after returning response
    import os, signal
    def shutdown():
        try:
            import time
            time.sleep(0.5)
            os._exit(0)
        except:
            pass
    import threading
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
    if not name or not ip:
        flash('Name and IP are required.', 'danger')
    else:
        if add_pabx_server(name, ip):
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

from models.settings import get_pabx_servers, get_pabx_status, get_setting

@auth_bp.route('/admin/status')
@admin_required
def system_status():
    server_list = get_pabx_servers()
    status_db = get_pabx_status() if server_list else {}
    timeout_minutes = int(get_setting('pabx_online_timeout_minutes') or 15)
    now = datetime.now()
    status_rows = []
    for s in server_list:
        ip = s['ip']
        info = status_db.get(ip, {})
        last_seen_str = info.get('last_seen')
        online = False
        if last_seen_str:
            try:
                last_dt = datetime.strptime(last_seen_str, '%Y-%m-%d %H:%M:%S')
                online = (now - last_dt).total_seconds() <= timeout_minutes * 60
            except:
                pass
        status_rows.append({
            'name': s['name'],
            'ip': ip,
            'connected': online,
            'last_seen': last_seen_str or 'Never'
        })
    return render_template('system_status.html', servers=status_rows)