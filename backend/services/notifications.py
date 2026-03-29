import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_env():
    from dotenv import dotenv_values
    return dotenv_values(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


def _store_notification(ntype, title, message, channel_id=None):
    from backend.models.database import get_db
    db = get_db()
    db.execute(
        "INSERT INTO notifications (type, title, message, channel_id) VALUES (?,?,?,?)",
        (ntype, title, message, channel_id)
    )
    db.commit()
    db.close()


def send_sms(message):
    env = _get_env()
    sid = env.get('TWILIO_ACCOUNT_SID', '')
    token = env.get('TWILIO_AUTH_TOKEN', '')
    from_num = env.get('TWILIO_FROM', '')
    to_num = env.get('TWILIO_TO', '')
    if not all([sid, token, from_num, to_num]):
        logger.warning("SMS not configured, skipping.")
        return False
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(body=message, from_=from_num, to=to_num)
        logger.info(f"SMS sent: {message[:60]}")
        return True
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return False


def send_email(subject, body):
    env = _get_env()
    sender = env.get('EMAIL_SENDER', '')
    password = env.get('EMAIL_PASSWORD', '')
    recipient = env.get('EMAIL_RECIPIENT', '')
    if not all([sender, password, recipient]):
        logger.warning("Email not configured, skipping.")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        logger.info(f"Email sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_upload_failure_notification(channel_id, genre):
    from backend.models.database import get_db
    db = get_db()
    ch = db.execute("SELECT name FROM channels WHERE id=?", (channel_id,)).fetchone()
    db.close()
    ch_name = ch['name'] if ch else f"Channel {channel_id}"
    title = f"Upload Failed: {ch_name}"
    msg = f"YouTube upload failed for {ch_name} ({genre}) after 3 attempts at {datetime.now().strftime('%Y-%m-%d %H:%M')}."
    _store_notification('error', title, msg, channel_id)
    send_sms(msg)
    send_email(f"⚠️ {title}", f"<p>{msg}</p>")


def send_milestone_notification(channel_id, channel_name, milestone):
    title = f"🎉 Milestone: {channel_name} reached {milestone:,} subscribers!"
    msg = f"Congratulations! {channel_name} has reached {milestone:,} subscribers on YouTube!"
    _store_notification('milestone', title, msg, channel_id)
    send_sms(msg)
    send_email(title, f"<p>{msg}</p>")


def send_quota_warning(api_name):
    title = f"API Quota Exceeded: {api_name}"
    msg = f"Your {api_name} quota has been exceeded. Consider adding a fallback API key in Settings."
    _store_notification('warning', title, msg)
    send_email(f"⚠️ {title}", f"<p>{msg}</p>")


def send_monthly_report(stats):
    total_subs = sum(s.get('subscriber_count', 0) for s in stats)
    total_views = sum(s.get('view_count', 0) for s in stats)
    total_earnings = total_views / 1000 * 2

    rows = "".join(
        f"<tr><td>{s['name']}</td><td>{s['subscriber_count']:,}</td>"
        f"<td>{s['view_count']:,}</td><td>NZ${s['view_count']/1000*2:.2f}</td></tr>"
        for s in stats
    )
    html = f"""
    <h2>📊 Monthly YouTube Automation Report</h2>
    <p><b>Total Subscribers:</b> {total_subs:,}</p>
    <p><b>Total Views:</b> {total_views:,}</p>
    <p><b>Estimated Earnings:</b> NZ${total_earnings:.2f}</p>
    <table border='1' cellpadding='8'>
    <tr><th>Channel</th><th>Subscribers</th><th>Views</th><th>Est. Earnings</th></tr>
    {rows}
    </table>
    """
    send_email("📊 Monthly YouTube Report", html)
