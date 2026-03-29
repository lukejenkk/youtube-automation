import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
import json
import logging
from flask import Blueprint, request, session, redirect, url_for, jsonify

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
TOKENS_DIR = os.path.join(BASE_DIR, 'data', 'tokens')
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']


def _get_env():
    from dotenv import dotenv_values
    return dotenv_values(os.path.join(BASE_DIR, '.env'))


def _get_redirect_uri():
    return "http://yt-dash.duckdns.org:5000/auth/callback"


@auth_bp.route('/auth/start/<int:channel_id>')
def auth_start(channel_id):
    if 'authenticated' not in session:
        return redirect('/')
    env = _get_env()
    oauth_json = env.get('OAUTH_JSON', '')
    if not oauth_json:
        return jsonify({'error': 'OAuth JSON not configured in Settings'}), 400

    try:
        from google_auth_oauthlib.flow import Flow
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(oauth_json)
            tmp = f.name

        flow = Flow.from_client_secrets_file(tmp, scopes=SCOPES, redirect_uri=_get_redirect_uri())
        os.unlink(tmp)

        auth_url, state = flow.authorization_url(
            access_type='offline', include_granted_scopes='true', prompt='consent'
        )
        session['oauth_state'] = state
        session['oauth_channel_id'] = channel_id
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"OAuth start failed: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/auth/callback')
def auth_callback():
    state = session.get('oauth_state')
    channel_id = session.get('oauth_channel_id')
    if not state or not channel_id:
        return redirect('/channels')

    env = _get_env()
    oauth_json = env.get('OAUTH_JSON', '')

    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(oauth_json)
            tmp = f.name

        flow = Flow.from_client_secrets_file(tmp, scopes=SCOPES, state=state, redirect_uri=_get_redirect_uri())
        os.unlink(tmp)
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        # Discover channels for this user
        youtube = build('youtube', 'v3', credentials=creds)
        resp = youtube.channels().list(part='snippet,statistics', mine=True).execute()
        items = resp.get('items', [])

        if not items:
            session['oauth_error'] = "No YouTube channels found for this Google account."
            return redirect('/channels')

        # Store creds and channel info in session for selection
        session['oauth_creds'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
        }
        session['oauth_yt_channels'] = [
            {'id': i['id'], 'name': i['snippet']['title'],
             'subscribers': i['statistics'].get('subscriberCount', 0)}
            for i in items
        ]
        session['oauth_channel_id'] = channel_id
        return redirect('/channels/select')
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        session['oauth_error'] = str(e)
        return redirect('/channels')


@auth_bp.route('/auth/select', methods=['POST'])
def auth_select():
    """User selects which YouTube channel to associate."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json
    yt_channel_id = data.get('youtube_channel_id')
    channel_id = session.get('oauth_channel_id')
    creds_data = session.get('oauth_creds')

    if not all([yt_channel_id, channel_id, creds_data]):
        return jsonify({'error': 'Missing session data'}), 400

    os.makedirs(TOKENS_DIR, exist_ok=True)
    token_path = os.path.join(TOKENS_DIR, f"channel_{channel_id}.json")
    with open(token_path, 'w') as f:
        json.dump(creds_data, f)

    # Get channel name from session
    yt_channels = session.get('oauth_yt_channels', [])
    yt_name = next((c['name'] for c in yt_channels if c['id'] == yt_channel_id), 'Unknown')

    from backend.models.database import get_db
    db = get_db()
    db.execute(
        "UPDATE channels SET youtube_channel_id=?, youtube_channel_name=?, status=?, oauth_token_path=? WHERE id=?",
        (yt_channel_id, yt_name, 'connected', token_path, channel_id)
    )
    db.commit()
    db.close()

    session.pop('oauth_creds', None)
    session.pop('oauth_yt_channels', None)
    session.pop('oauth_channel_id', None)
    session.pop('oauth_state', None)

    logger.info(f"Channel {channel_id} connected to YouTube: {yt_name}")
    return jsonify({'success': True, 'channel_name': yt_name})
