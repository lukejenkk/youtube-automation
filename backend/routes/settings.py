import os
import json
import logging
from flask import Blueprint, jsonify, request, session

logger = logging.getLogger(__name__)
settings_bp = Blueprint('settings', __name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ENV_PATH = os.path.join(BASE_DIR, '.env')

SETTINGS_FIELDS = [
    'YOUTUBE_API_KEY_1', 'YOUTUBE_API_KEY_2',
    'PEXELS_API_KEY', 'PIXABAY_API_KEY',
    'TTS_PROVIDER', 'GOOGLE_TTS_API_KEY', 'ELEVENLABS_API_KEY',
    'REDDIT_APP_ID', 'REDDIT_APP_SECRET', 'REDDIT_USER_AGENT',
    'UPLOAD_WINDOW_START', 'UPLOAD_WINDOW_END',
    'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM', 'TWILIO_TO',
    'EMAIL_SENDER', 'EMAIL_PASSWORD', 'EMAIL_RECIPIENT',
    'DUCKDNS_DOMAIN', 'DUCKDNS_TOKEN',
    'TIMEZONE', 'PI_LOCAL_IP',
]


def require_auth(f):
    from functools import wraps
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'authenticated' not in session:
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


def read_env():
    """Read .env file — handles JSON, special chars, multi-line values."""
    result = {}
    if not os.path.exists(ENV_PATH):
        return result
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        elif len(v) >= 2 and v[0] == "'" and v[-1] == "'":
            v = v[1:-1]
        v = v.replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n').replace('\\\\', '\\')
        result[k] = v
    return result


def write_env_key(key, value):
    """Write a single key to .env safely, handling any value including JSON."""
    # Escape: backslashes first, then double-quotes, then collapse newlines
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
            if line.strip().startswith(f'{key}=') or line.strip() == f'{key}=':
                lines.append(new_line)
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(new_line)

    with open(ENV_PATH, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def write_env(data):
    """Write multiple keys to .env."""
    for k, v in data.items():
        write_env_key(k, v)


@settings_bp.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    env = read_env()
    result = {k: env.get(k, '') for k in SETTINGS_FIELDS}
    result['oauth_json_set'] = bool(env.get('OAUTH_JSON', '').strip())
    result['oauth_json_client_id'] = ''
    if result['oauth_json_set']:
        try:
            parsed = json.loads(env.get('OAUTH_JSON', ''))
            app_type = 'web' if 'web' in parsed else 'installed'
            result['oauth_json_client_id'] = parsed[app_type].get('client_id', '')[:30]
        except Exception:
            pass
    return jsonify(result)


@settings_bp.route('/api/settings', methods=['POST'])
@require_auth
def save_settings():
    data = request.json or {}
    filtered = {k: v for k, v in data.items() if k in SETTINGS_FIELDS and v is not None}
    write_env(filtered)
    logger.info(f"Settings saved: {list(filtered.keys())}")
    return jsonify({'success': True})


@settings_bp.route('/api/settings/upload-oauth', methods=['POST'])
@require_auth
def upload_oauth():
    """Accept OAuth JSON as uploaded file or raw JSON POST."""
    # Handle file upload
    if 'file' in request.files:
        f = request.files['file']
        raw = f.read().decode('utf-8').strip()
    elif request.is_json:
        raw = request.json.get('json', '').strip()
    else:
        raw = request.get_data(as_text=True).strip()

    if not raw:
        return jsonify({'success': False, 'error': 'No data received'}), 400

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Invalid JSON: {e}'}), 400

    if 'web' not in parsed and 'installed' not in parsed:
        return jsonify({'success': False, 'error': 'Missing "web" or "installed" key'}), 400

    app_type = 'web' if 'web' in parsed else 'installed'
    client_id = parsed[app_type].get('client_id', 'unknown')

    # Save to .env
    write_env_key('OAUTH_JSON', raw)
    logger.info(f"OAuth JSON uploaded and saved. client_id: {client_id[:24]}")

    return jsonify({
        'success': True,
        'client_id': client_id[:30],
        'app_type': app_type,
        'message': f'OAuth JSON saved ({app_type} app)'
    })


@settings_bp.route('/api/settings/test-oauth', methods=['POST'])
@require_auth
def test_oauth():
    env = read_env()
    oauth_json = env.get('OAUTH_JSON', '').strip()
    if not oauth_json:
        return jsonify({'valid': False, 'error': 'No OAuth JSON saved yet. Upload your client_secret.json file.'})
    try:
        parsed = json.loads(oauth_json)
        if 'web' not in parsed and 'installed' not in parsed:
            return jsonify({'valid': False, 'error': 'Invalid structure'})
        app_type = 'web' if 'web' in parsed else 'installed'
        client_id = parsed[app_type].get('client_id', 'unknown')
        return jsonify({'valid': True, 'message': f'Valid {app_type} OAuth. Client ID: {client_id[:24]}...'})
    except json.JSONDecodeError as e:
        return jsonify({'valid': False, 'error': f'Corrupted JSON in .env: {e}'})


@settings_bp.route('/api/settings/test-sms', methods=['POST'])
@require_auth
def test_sms():
    from backend.services.notifications import send_sms
    ok = send_sms("YouTube Automation: Test SMS!")
    return jsonify({'success': ok})


@settings_bp.route('/api/settings/test-email', methods=['POST'])
@require_auth
def test_email():
    from backend.services.notifications import send_email
    ok = send_email("YouTube Automation Test", "<p>Test email from Pi.</p>")
    return jsonify({'success': ok})


@settings_bp.route('/api/settings/change-pin', methods=['POST'])
@require_auth
def change_pin():
    import bcrypt
    data = request.json or {}
    current_pin = str(data.get('current_pin', '')).strip()
    new_pin = str(data.get('new_pin', '')).strip()
    env = read_env()
    stored_hash = env.get('DASHBOARD_PASSWORD_HASH', '').strip()
    if stored_hash:
        try:
            if not bcrypt.checkpw(current_pin.encode(), stored_hash.encode()):
                return jsonify({'error': 'Current PIN is incorrect'}), 401
        except Exception:
            return jsonify({'error': 'PIN verification failed'}), 500
    if not new_pin.isdigit() or len(new_pin) != 4:
        return jsonify({'error': 'New PIN must be exactly 4 digits'}), 400
    hashed = bcrypt.hashpw(new_pin.encode(), bcrypt.gensalt()).decode()
    write_env_key('DASHBOARD_PASSWORD_HASH', hashed)
    logger.info("PIN changed.")
    return jsonify({'success': True})


@settings_bp.route('/api/settings/clear-oauth', methods=['POST'])
@require_auth
def clear_oauth():
    write_env_key('OAUTH_JSON', '')
    logger.info("OAuth JSON cleared.")
    return jsonify({'success': True})


@settings_bp.route('/api/settings/test-pexels', methods=['POST'])
@require_auth
def test_pexels():
    import requests
    env = read_env()
    key = env.get('PEXELS_API_KEY', '').strip()
    if not key:
        return jsonify({'success': False, 'error': 'No Pexels API key saved'})
    try:
        r = requests.get('https://api.pexels.com/videos/search',
            headers={'Authorization': key},
            params={'query': 'nature', 'per_page': 1}, timeout=10)
        if r.status_code == 200:
            total = r.json().get('total_results', 0)
            return jsonify({'success': True, 'message': f'Connected — {total:,} results for test query'})
        return jsonify({'success': False, 'error': f'HTTP {r.status_code}: {r.text[:100]}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@settings_bp.route('/api/settings/test-pixabay', methods=['POST'])
@require_auth
def test_pixabay():
    import requests
    env = read_env()
    key = env.get('PIXABAY_API_KEY', '').strip()
    if not key:
        return jsonify({'success': False, 'error': 'No Pixabay API key saved'})
    try:
        r = requests.get('https://pixabay.com/api/videos/',
            params={'key': key, 'q': 'nature', 'per_page': 3}, timeout=10)
        if r.status_code == 200:
            total = r.json().get('totalHits', 0)
            return jsonify({'success': True, 'message': f'Connected — {total:,} results for test query'})
        return jsonify({'success': False, 'error': f'HTTP {r.status_code}: {r.text[:100]}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@settings_bp.route('/api/settings/test-tts', methods=['POST'])
@require_auth
def test_tts():
    import requests, base64, tempfile, os
    env = read_env()
    provider = env.get('TTS_PROVIDER', 'google').lower()
    if provider == 'elevenlabs':
        key = env.get('ELEVENLABS_API_KEY', '').strip()
        if not key:
            return jsonify({'success': False, 'error': 'No ElevenLabs API key saved'})
        try:
            r = requests.get('https://api.elevenlabs.io/v1/voices',
                headers={'xi-api-key': key}, timeout=10)
            if r.status_code == 200:
                voices = len(r.json().get('voices', []))
                return jsonify({'success': True, 'message': f'ElevenLabs connected — {voices} voices available'})
            return jsonify({'success': False, 'error': f'HTTP {r.status_code}'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        key = env.get('GOOGLE_TTS_API_KEY', '').strip()
        if not key:
            return jsonify({'success': False, 'error': 'No Google TTS API key saved'})
        try:
            r = requests.post(
                f'https://texttospeech.googleapis.com/v1/text:synthesize?key={key}',
                json={'input': {'text': 'Test.'}, 'voice': {'languageCode': 'en-US', 'name': 'en-US-Neural2-D'}, 'audioConfig': {'audioEncoding': 'MP3'}},
                timeout=15)
            if r.status_code == 200:
                return jsonify({'success': True, 'message': 'Google TTS connected and working'})
            return jsonify({'success': False, 'error': f'HTTP {r.status_code}: {r.json().get("error",{}).get("message","Unknown")}'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


@settings_bp.route('/api/settings/test-reddit', methods=['POST'])
@require_auth
def test_reddit():
    env = read_env()
    app_id = env.get('REDDIT_APP_ID', '').strip()
    secret = env.get('REDDIT_APP_SECRET', '').strip()
    agent = env.get('REDDIT_USER_AGENT', 'YTAutomation/1.0').strip()
    if not app_id or not secret:
        return jsonify({'success': False, 'error': 'Reddit App ID and Secret required'})
    try:
        import praw
        reddit = praw.Reddit(client_id=app_id, client_secret=secret, user_agent=agent, check_for_async=False)
        sub = reddit.subreddit('nosleep')
        posts = list(sub.hot(limit=3))
        return jsonify({'success': True, 'message': f'Reddit connected — fetched {len(posts)} posts from r/nosleep'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

