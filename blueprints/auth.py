import sqlite3
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, abort)
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
from werkzeug.security import check_password_hash
from models.user import (get_user_by_username, create_user, delete_user,
                         get_all_users, get_user_by_id, update_user)
from extensions import login_manager
from models.settings import get_all_settings, update_settings
from models.audit import log_action
from models.database import get_db


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
    log_action(current_user.id, f"Deleted user ID {user_id}")
    if current_user.id == user_id:
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('auth.list_users'))
    delete_user(user_id)
    flash('User deleted.', 'info')
    return redirect(url_for('auth.list_users'))


@auth_bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    log_action(current_user.id, "Updated system settings")
    if request.method == 'POST':
        update_settings({
            'smdr_ip': request.form.get('smdr_ip', '0.0.0.0'),
            'smdr_port': request.form.get('smdr_port', '9001'),
            'web_host': request.form.get('web_host', '0.0.0.0'),
            'web_port': request.form.get('web_port', '5000')
        })
        flash('Settings saved. Restart the application for changes to take effect.', 'success')
        return redirect(url_for('auth.settings'))
    return render_template('settings.html', settings=get_all_settings())


@auth_bp.route('/admin/audit')
@admin_required
def view_audit():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, u.username, a.action, a.ip_address, a.timestamp
        FROM audit_log a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
        LIMIT 200
    """)
    logs = cursor.fetchall()
    conn.close()
    return render_template('audit.html', logs=logs)


@auth_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    log_action(current_user.id, f"Edited user '{user[1]}': role={role}, extension={extension}, password={'changed' if password else 'unchanged'}")
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

        flash('User updated successfully.', 'success')
        return redirect(url_for('auth.list_users'))

    return render_template('edit_user.html', user=user)


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    log_action(current_user.id, "Changed own password")
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
        flash('Password changed successfully. Please use the new password on your next login.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('change_password.html')