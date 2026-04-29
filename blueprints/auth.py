import sqlite3
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, abort)
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
from werkzeug.security import check_password_hash
from models.user import (get_user_by_username, create_user, delete_user,
                         get_all_users, get_user_by_id, update_user)
from extensions import login_manager

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
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
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
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    role = request.form['role']
    extension = request.form['extension'].strip() or None
    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('auth.list_users'))
    try:
        create_user(username, password, role, extension)
        flash('User added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash('Username already exists.', 'danger')
    except Exception as e:
        flash(f'Error adding user: {e}', 'danger')
    return redirect(url_for('auth.list_users'))

@auth_bp.route('/admin/users/delete/<int:user_id>')
@admin_required
def delete_user_route(user_id):
    if current_user.id == user_id:
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('auth.list_users'))
    delete_user(user_id)
    flash('User deleted.', 'info')
    return redirect(url_for('auth.list_users'))

@auth_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    # Only admin can access
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.list_users'))

    if request.method == 'POST':
        password = request.form['password'].strip()
        role = request.form['role']
        extension = request.form['extension'].strip() or None

        if password:
            update_user(user_id, password=password)
        if role:
            update_user(user_id, role=role)
        if extension is not None:
            update_user(user_id, extension=extension)
        flash('User updated successfully.', 'success')
        return redirect(url_for('auth.list_users'))

    # Pre-populate form for GET
    return render_template('edit_user.html', user=user)