import os
import logging
from flask import Blueprint, jsonify, send_file, session

logger = logging.getLogger(__name__)
logs_bp = Blueprint('logs', __name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
LOG_FILE = os.path.join(BASE_DIR, 'logs', 'system.log')


def require_auth(f):
    from functools import wraps
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'authenticated' not in session:
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


@logs_bp.route('/api/logs')
@require_auth
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({'logs': []})

    entries = []
    with open(LOG_FILE, 'r') as f:
        lines = f.readlines()

    for line in lines[-200:]:
        line = line.strip()
        if not line:
            continue
        # Parse: 2024-01-01 12:00:00,000 - LEVEL - message
        parts = line.split(' - ', 2)
        if len(parts) == 3:
            entries.append({
                'timestamp': parts[0],
                'level': parts[1].strip(),
                'message': parts[2].strip(),
            })
        else:
            entries.append({'timestamp': '', 'level': 'INFO', 'message': line})

    return jsonify({'logs': list(reversed(entries))})


@logs_bp.route('/api/logs/download')
@require_auth
def download_logs():
    if not os.path.exists(LOG_FILE):
        return 'No log file found', 404
    return send_file(LOG_FILE, as_attachment=True, download_name='system.log', mimetype='text/plain')
