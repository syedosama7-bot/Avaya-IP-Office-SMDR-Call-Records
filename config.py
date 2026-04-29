import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smdr_records.db')
    SMDR_LISTEN_IP = '0.0.0.0'
    SMDR_LISTEN_PORT = 9001
    DEBUG = False