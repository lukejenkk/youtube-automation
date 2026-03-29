import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MILESTONES = [1000, 10000, 100000, 1000000]


def _get_env():
    from dotenv import dotenv_values
    return dotenv_values(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


def fetch_channel_stats(channel_id, youtube_channel_id, api_key):
    """Fetch stats from YouTube Data API v3."""
    import requests
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'statistics',
        'id': youtube_channel_id,
        'key': api_key,
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 403:
                logger.warning("YouTube API quota exceeded, trying fallback key")
                from backend.services.notifications import send_quota_warning
                send_quota_warning("YouTube Data API")
                # Try fallback key
                env = _get_env()
                fallback = env.get('YOUTUBE_API_KEY_2', '')
                if fallback and fallback != api_key:
                    params['key'] = fallback
                    continue
                return None
            resp.raise_for_status()
            data = resp.json()
            items = data.get('items', [])
            if not items:
                return None
            stats = items[0]['statistics']
            return {
                'subscriber_count': int(stats.get('subscriberCount', 0)),
                'view_count': int(stats.get('viewCount', 0)),
                'video_count': int(stats.get('videoCount', 0)),
            }
        except Exception as e:
            logger.error(f"Stats fetch attempt {attempt+1} failed: {e}")
    return None


def check_milestones(channel_id, channel_name, old_subs, new_subs):
    from backend.services.notifications import send_milestone_notification
    for milestone in MILESTONES:
        if old_subs < milestone <= new_subs:
            logger.info(f"Milestone reached: {channel_name} at {milestone:,} subs!")
            send_milestone_notification(channel_id, channel_name, milestone)


def run_monitoring():
    """Run monitoring for all connected channels."""
    from backend.models.database import get_db
    env = _get_env()
    api_key = env.get('YOUTUBE_API_KEY_1', '')
    if not api_key:
        logger.warning("No YouTube API key configured for monitoring")
        return

    db = get_db()
    channels = db.execute(
        "SELECT id, name, youtube_channel_id, subscriber_count FROM channels WHERE youtube_channel_id IS NOT NULL"
    ).fetchall()
    db.close()

    for ch in channels:
        stats = fetch_channel_stats(ch['id'], ch['youtube_channel_id'], api_key)
        if not stats:
            continue

        old_subs = ch['subscriber_count'] or 0
        new_subs = stats['subscriber_count']
        est_earnings = stats['view_count'] / 1000 * 2

        db = get_db()
        db.execute(
            "UPDATE channels SET subscriber_count=?, view_count=? WHERE id=?",
            (new_subs, stats['view_count'], ch['id'])
        )
        db.execute(
            "INSERT INTO stats (channel_id, subscriber_count, view_count, estimated_earnings) VALUES (?,?,?,?)",
            (ch['id'], new_subs, stats['view_count'], est_earnings)
        )
        db.commit()
        db.close()

        check_milestones(ch['id'], ch['name'], old_subs, new_subs)
        logger.info(f"Stats updated for {ch['name']}: {new_subs:,} subs, {stats['view_count']:,} views")


def send_monthly_report_if_due():
    """Send monthly report on the 1st of each month."""
    if datetime.now().day != 1:
        return
    from backend.models.database import get_db
    from backend.services.notifications import send_monthly_report
    db = get_db()
    channels = db.execute("SELECT id, name, subscriber_count, view_count FROM channels").fetchall()
    db.close()
    stats = [dict(ch) for ch in channels]
    send_monthly_report(stats)
    logger.info("Monthly report sent.")
