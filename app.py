from flask import Flask
from config import Config
from extensions import login_manager
from models.database import init_db
from services.smdr_listener import start_listener
from blueprints.auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.reports import reports_bp
from blueprints.export import export_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    login_manager.init_app(app)

    # Ensure database is ready
    with app.app_context():
        init_db()

    # Start SMDR listener in background thread
    import threading
    threading.Thread(target=start_listener, args=(
        app.config['SMDR_LISTEN_IP'],
        app.config['SMDR_LISTEN_PORT'],
        app.config['DATABASE']
    ), daemon=True).start()

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(export_bp)

    return app