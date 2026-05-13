import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO
from models.settings import get_setting
from models.database import get_db
from datetime import datetime

logger = logging.getLogger(__name__)

def get_smtp_config():
    return {
        'host': get_setting('smtp_host') or '',
        'port': int(get_setting('smtp_port') or 587),
        'protocol': get_setting('smtp_protocol') or 'starttls',
        'verify_cert': get_setting('smtp_verify_cert') == '1',
        'username': get_setting('smtp_username') or '',
        'password': get_setting('smtp_password') or '',
        'from_email': get_setting('smtp_from_email') or '',
        'from_name': get_setting('smtp_from_name') or 'Avaya CDR'
    }

def send_email(to_email, subject, body_html, attachments=None, user_id=None):
    config = get_smtp_config()
    if not config['host'] or not config['from_email']:
        logger.warning("SMTP not configured – email not sent.")
        return False

    try:
        msg = MIMEMultipart('mixed')
        msg['From'] = f"{config['from_name']} <{config['from_email']}>"
        msg['To'] = to_email
        msg['Subject'] = subject

        body = MIMEMultipart('alternative')
        body.attach(MIMEText(body_html, 'html'))
        msg.attach(body)

        if attachments:
            for filename, buffer, mime_type in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(buffer.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                if mime_type:
                    part.set_type(mime_type)
                msg.attach(part)

        # Set up SSL context based on verify_cert
        if config['verify_cert']:
            ctx = ssl.create_default_context()
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        protocol = config['protocol']
        if protocol == 'ssl':
            server = smtplib.SMTP_SSL(config['host'], config['port'], context=ctx, timeout=30)
            # No need for starttls
        else:
            server = smtplib.SMTP(config['host'], config['port'], timeout=30)
            if protocol == 'starttls':
                server.starttls(context=ctx)
                server.ehlo()
            # For 'none', we just continue without TLS.

        # Authentication
        server.ehlo_or_helo_if_needed()
        has_auth = server.has_extn('auth')
        if config['username'] and has_auth:
            server.login(config['username'], config['password'])
        elif config['username'] and not has_auth:
            logger.warning("SMTP server does not support AUTH – sending without login.")

        server.sendmail(config['from_email'], to_email, msg.as_string())
        server.quit()

        log_email(to_email, subject, 'sent', user_id=user_id)
        logger.info(f"Email sent to {to_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Email failed to {to_email}: {e}")
        log_email(to_email, subject, 'failed', error=str(e), user_id=user_id)
        return False

def log_email(to_email, subject, status, error=None, user_id=None):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO email_log (user_id, to_email, subject, status, error_message, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, to_email, subject, status, error, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass