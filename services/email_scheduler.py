import threading
import time
import logging
from datetime import datetime, date
import json
import sqlite3
from io import BytesIO
from flask import current_app

logger = logging.getLogger(__name__)

DB_PATH = None
APP = None

def start_email_scheduler(app, db_path):
    global DB_PATH, APP
    DB_PATH = db_path
    APP = app

    def run():
        logger.info("Email scheduler started – checking every minute")
        while True:
            try:
                with APP.app_context():
                    conn = sqlite3.connect(DB_PATH)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT rs.*, u.email, u.id as user_id
                        FROM report_subscriptions rs
                        JOIN users u ON rs.user_id = u.id
                        WHERE rs.enabled = 1
                          AND u.email_reports_enabled = 1
                          AND u.email IS NOT NULL
                          AND u.email != ''
                    """)
                    subs = cursor.fetchall()
                    now = datetime.now()
                    for sub in subs:
                        try:
                            _process_subscription(sub, now)
                        except Exception as e:
                            logger.error(f"Error processing sub {sub['id']}: {e}")
                    conn.close()
            except Exception as err:
                logger.error(f"Email scheduler outer error: {err}")
            time.sleep(60)

    threading.Thread(target=run, daemon=True).start()
    logger.info("Email scheduler thread started")


def _process_subscription(sub, now):
    freq = sub['frequency']
    schedule_day = int(sub['schedule_day']) if sub['schedule_day'] else 0
    schedule_time = sub['schedule_time'] or '08:00'

    try:
        hour, minute = map(int, schedule_time.split(':'))
    except Exception:
        return

    # Check if today is the right day
    due = False
    if freq == 'daily':
        due = True
    elif freq == 'weekly':
        due = (now.isoweekday() == schedule_day)
    elif freq == 'monthly':
        if now.month == 12:
            last_day = 31
        else:
            next_month = date(now.year, now.month + 1, 1)
            last_day = (next_month - date(now.year, now.month, 1)).days
        due = (schedule_day <= last_day and now.day == schedule_day)
    else:
        return

    if not due or now.hour != hour or now.minute != minute:
        return

    report_type = sub['report_type']
    to_email = sub['email']
    user_id = sub['user_id']

    # Build filter string from stored JSON
    filters = {}
    if sub['filter_params']:
        try:
            filters = json.loads(sub['filter_params'])
        except:
            filters = {}
    params = {k: v for k, v in filters.items() if v}
    query_string = '&'.join(f"{k}={v}" for k, v in params.items())

    # Use the app's test client, authenticated as the subscription owner
    with APP.test_client() as client:
        # Fake login by setting the user_id in the session
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        url = f'/report/{report_type}/export/pdf'
        if query_string:
            url += '?' + query_string
        response = client.get(url, follow_redirects=True)

        if response.status_code == 200:
            buffer = BytesIO(response.data)
            from services.email_sender import send_email
            subject = f"Scheduled Report – {report_type.replace('_', ' ').title()}"
            body = f"""
            <html><body>
                <h3>{report_type.replace('_', ' ').title()}</h3>
                <p>Your scheduled report is attached.</p>
                <p><small>Sent automatically by Avaya CDR</small></p>
            </body></html>
            """
            success = send_email(to_email, subject, body,
                                 attachments=[(f"{report_type}_report.pdf", buffer, 'application/pdf')],
                                 user_id=user_id)
            if success:
                logger.info(f"Scheduled email sent: {report_type} to {to_email}")
            else:
                logger.error(f"Failed to send scheduled email: {report_type} to {to_email}")
        else:
            logger.error(f"Export failed for {report_type} (HTTP {response.status_code})")