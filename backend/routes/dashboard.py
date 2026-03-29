import os
import logging
from flask import Blueprint, jsonify, session
from backend.models.database import get_db
from backend.services.scheduler import get_state, set_paused

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint('dashboard', __name__)


def require_auth(f):
    from functools import wraps
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'authenticated' not in session:
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


@dashboard_bp.route('/api/dashboard/stats')
@require_auth
def dashboard_stats():
    db = get_db()
    channels = db.execute("SELECT * FROM channels").fetchall()
    notifications = db.execute(
        "SELECT * FROM notifications WHERE read=0 ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    history = db.execute("""
        SELECT uh.*, c.name as channel_name
        FROM upload_history uh
        JOIN channels c ON c.id = uh.channel_id
        ORDER BY uh.uploaded_at DESC LIMIT 50
    """).fetchall()
    queue = db.execute("""
        SELECT v.*, c.name as channel_name
        FROM videos v
        JOIN channels c ON c.id = v.channel_id
        WHERE v.status IN ('pending','queued')
        ORDER BY v.scheduled_time ASC LIMIT 20
    """).fetchall()
    db.close()

    total_subs = sum(c['subscriber_count'] or 0 for c in channels)
    total_views = sum(c['view_count'] or 0 for c in channels)
    est_earnings = total_views / 1000 * 2

    # Videos this week
    from datetime import datetime, timedelta
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    db = get_db()
    week_count = db.execute(
        "SELECT COUNT(*) as cnt FROM upload_history WHERE uploaded_at > ? AND status='success'",
        (week_ago,)
    ).fetchone()['cnt']
    db.close()

    sched_state = get_state()

    return jsonify({
        'total_subscribers': total_subs,
        'total_views': total_views,
        'estimated_earnings_nzd': round(est_earnings, 2),
        'videos_this_week': week_count,
        'channels': [dict(c) for c in channels],
        'notifications': [dict(n) for n in notifications],
        'upload_history': [dict(h) for h in history],
        'queue': [dict(q) for q in queue],
        'scheduler': sched_state,
    })


@dashboard_bp.route('/api/dashboard/pause', methods=['POST'])
@require_auth
def pause():
    set_paused(True)
    return jsonify({'status': 'paused'})


@dashboard_bp.route('/api/dashboard/resume', methods=['POST'])
@require_auth
def resume():
    set_paused(False)
    return jsonify({'status': 'resumed'})


@dashboard_bp.route('/api/notifications/<int:nid>/dismiss', methods=['POST'])
@require_auth
def dismiss_notification(nid):
    db = get_db()
    db.execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))
    db.commit()
    db.close()
    return jsonify({'success': True})


@dashboard_bp.route('/api/dashboard/shutdown', methods=['POST'])
@require_auth
def shutdown():
    logger.info("Shutdown requested from dashboard")
    import subprocess
    subprocess.Popen(['sudo', 'shutdown', '-h', 'now'])
    return jsonify({'status': 'shutting_down'})
