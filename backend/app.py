import os
import sys
import logging
from datetime import timedelta
from flask import Flask, request, session, redirect, send_from_directory, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, ROOT_DIR)

LOG_DIR = os.path.join(ROOT_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'system.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(ROOT_DIR, '.env')
FRONTEND_DIR = os.path.join(ROOT_DIR, 'frontend')

logger.info(f"ROOT_DIR: {ROOT_DIR}")
logger.info(f"FRONTEND_DIR exists: {os.path.isdir(FRONTEND_DIR)}")


def read_env():
    result = {}
    if not os.path.exists(ENV_PATH):
        return result
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            k = k.strip(); v = v.strip()
            if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                v = v[1:-1]
            v = v.replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n').replace('\\\\', '\\')
            result[k] = v
    return result


def write_env_key(key, value):
    v_str = str(value)
    v_escaped = v_str.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '')
    new_line = f'{key}="{v_escaped}"\n'
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'w') as f:
            f.write(new_line)
        return
    lines = []
    found = False
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith(f'{key}='):
                lines.append(new_line)
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(new_line)
    with open(ENV_PATH, 'w', encoding='utf-8') as f:
        f.writelines(lines)


if not os.path.exists(ENV_PATH):
    defaults = [
        'DASHBOARD_PASSWORD_HASH=""', 'YOUTUBE_API_KEY_1=""', 'YOUTUBE_API_KEY_2=""',
        'OAUTH_JSON=""', 'PEXELS_API_KEY=""', 'PIXABAY_API_KEY=""',
        'TTS_PROVIDER="google"', 'GOOGLE_TTS_API_KEY=""', 'ELEVENLABS_API_KEY=""',
        'REDDIT_APP_ID=""', 'REDDIT_APP_SECRET=""', 'REDDIT_USER_AGENT="YTAutomation/1.0"',
        'UPLOAD_WINDOW_START="06:00"', 'UPLOAD_WINDOW_END="22:00"',
        'TWILIO_ACCOUNT_SID=""', 'TWILIO_AUTH_TOKEN=""', 'TWILIO_FROM=""', 'TWILIO_TO=""',
        'EMAIL_SENDER=""', 'EMAIL_PASSWORD=""', 'EMAIL_RECIPIENT=""',
        'DUCKDNS_DOMAIN=""', 'DUCKDNS_TOKEN=""',
        'TIMEZONE="Pacific/Auckland"', 'PI_LOCAL_IP="yt-dash.duckdns.org"',
        'VIDEO_RETENTION_DAYS="7"', 'EXTERNAL_DRIVE=""',
        f'SECRET_KEY="{os.urandom(24).hex()}"',
    ]
    with open(ENV_PATH, 'w') as f:
        f.write('# YouTube Automation Configuration\n')
        for d in defaults:
            f.write(d + '\n')

from backend.models.database import init_db
init_db()

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
env_vals = read_env()
secret = env_vals.get('SECRET_KEY', '') or os.urandom(32).hex()
app.secret_key = secret
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

from backend.routes.auth import auth_bp
from backend.routes.dashboard import dashboard_bp
from backend.routes.channels import channels_bp
from backend.routes.settings import settings_bp
from backend.routes.logs import logs_bp
from backend.routes.system import system_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(channels_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(system_bp)


@app.before_request
def check_auth():
    if request.path.startswith('/css') or request.path.startswith('/js'):
        return
    if request.path in ('/', '/api/auth/login', '/api/auth/setup', '/api/auth/check'):
        return
    if request.path.startswith('/auth/'):
        return
    if 'authenticated' not in session:
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not authenticated'}), 401
        return redirect('/')


@app.route('/api/auth/check')
def auth_check():
    env_v = read_env()
    has_pin = bool(env_v.get('DASHBOARD_PASSWORD_HASH', '').strip())
    return jsonify({'authenticated': 'authenticated' in session, 'has_pin': has_pin})


@app.route('/api/auth/setup', methods=['POST'])
def auth_setup():
    import bcrypt
    env_v = read_env()
    if env_v.get('DASHBOARD_PASSWORD_HASH', '').strip():
        return jsonify({'error': 'PIN already set'}), 400
    data = request.json or {}
    pin = str(data.get('pin', '')).strip()
    if not pin.isdigit() or len(pin) != 4:
        return jsonify({'error': 'PIN must be 4 digits'}), 400
    hashed = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
    write_env_key('DASHBOARD_PASSWORD_HASH', hashed)
    session['authenticated'] = True
    session.permanent = True
    return jsonify({'success': True})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    import bcrypt
    env_v = read_env()
    stored_hash = env_v.get('DASHBOARD_PASSWORD_HASH', '').strip()
    if not stored_hash:
        return jsonify({'error': 'No PIN set'}), 400
    data = request.json or {}
    pin = str(data.get('pin', '')).strip()
    try:
        if bcrypt.checkpw(pin.encode(), stored_hash.encode()):
            session['authenticated'] = True
            session.permanent = True
            return jsonify({'success': True})
    except Exception as e:
        logger.error(f"bcrypt error: {e}")
    return jsonify({'error': 'Incorrect PIN'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/dashboard')
def dashboard_page():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/channels')
def channels_page():
    return send_from_directory(FRONTEND_DIR, 'channels.html')

@app.route('/settings')
def settings_page():
    return send_from_directory(FRONTEND_DIR, 'settings.html')

@app.route('/logs')
def logs_page():
    return send_from_directory(FRONTEND_DIR, 'logs.html')

@app.route('/videos')
def videos_page():
    return send_from_directory(FRONTEND_DIR, 'videos.html')

@app.route('/css/<path:filename>')
def css_files(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'css'), filename)

@app.route('/js/<path:filename>')
def js_files(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'js'), filename)


if __name__ == '__main__':
    from backend.services.scheduler import start_scheduler
    start_scheduler()
    logger.info("YouTube Automation Dashboard starting on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
