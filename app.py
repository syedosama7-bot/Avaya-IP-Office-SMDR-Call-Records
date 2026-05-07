import os
import threading
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from flask import Flask, request
from flask_login import current_user, logout_user
from config import Config
from extensions import login_manager
from models.database import init_db, get_db
from models.settings import get_all_settings
from models.user import update_last_seen
from services.smdr_listener import start_listener
from services.backup_scheduler import start_backup_scheduler
from blueprints.auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.reports import reports_bp
from blueprints.export import export_bp
from services.pabx_monitor import start_monitor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = os.urandom(24)   # changes every restart → logs out all users
    app.config['START_TIME'] = datetime.now()
    start_monitor(app.config['DATABASE'])

    # ---------- Configure application logging ----------
    log_dir = os.path.join(BASE_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'avaya_cdr.log')
    app.config['LOG_FILE'] = log_file

    class SizeRotatingHandler(TimedRotatingFileHandler):
        def __init__(self, filename, when='midnight', backupCount=30, maxBytes=10*1024*1024):
            super().__init__(filename, when=when, backupCount=backupCount)
            self.maxBytes = maxBytes

        def shouldRollover(self, record):
            if super().shouldRollover(record):
                return True
            if self.stream is not None and self.stream.tell() > self.maxBytes:
                return True
            return False

    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    file_handler = SizeRotatingHandler(log_file, when='midnight', backupCount=100, maxBytes=2*1024*1024)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    ))

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
    app.logger.info("Application logging configured.")

    login_manager.init_app(app)

    with app.app_context():
        init_db()
        settings = get_all_settings()
        app.config['SMDR_LISTEN_IP'] = settings['smdr_ip']
        app.config['SMDR_LISTEN_PORT'] = int(settings['smdr_port'])
        app.config['WEB_HOST'] = settings['web_host']
        app.config['WEB_PORT'] = int(settings['web_port'])

        threading.Thread(target=start_listener, args=(
            app.config['SMDR_LISTEN_IP'],
            app.config['SMDR_LISTEN_PORT'],
            app.config['DATABASE']
        ), daemon=True).start()

        start_backup_scheduler(app.config['DATABASE'])

    # ---------- User activity tracking & forced logout ----------
    @app.before_request
    def track_user_activity():
        if current_user.is_authenticated:
            ip = request.remote_addr or 'unknown'
            update_last_seen(current_user.id, ip)
            # Check if this user has been flagged for forced logout
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM force_logout WHERE user_id = ?", (current_user.id,))
            if cursor.fetchone():
                cursor.execute("DELETE FROM force_logout WHERE user_id = ?", (current_user.id,))
                conn.commit()
                conn.close()
                logout_user()
            else:
                conn.close()

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(export_bp)

    return app