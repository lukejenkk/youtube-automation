import os
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
TOKENS_DIR = os.path.join(BASE_DIR, 'data', 'tokens')

GENRE_TAGS = {
    'horror': ['horror story', 'reddit horror', 'scary story', 'nosleep', 'creepy reddit', 'true horror'],
    'relationship': ['relationship advice', 'reddit relationship', 'am i wrong', 'aita', 'reddit drama'],
    'workplace': ['antiwork', 'reddit workplace', 'malicious compliance', 'job story', 'work horror'],
}

SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']


def _get_env():
    from dotenv import dotenv_values
    return dotenv_values(os.path.join(BASE_DIR, '.env'))


def load_credentials(channel_id):
    from google.oauth2.credentials import Credentials
    token_path = os.path.join(TOKENS_DIR, f"channel_{channel_id}.json")
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"No OAuth token for channel {channel_id}")
    with open(token_path) as f:
        data = json.load(f)
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=SCOPES,
    )
    return creds


def save_credentials(channel_id, creds):
    os.makedirs(TOKENS_DIR, exist_ok=True)
    token_path = os.path.join(TOKENS_DIR, f"channel_{channel_id}.json")
    with open(token_path, 'w') as f:
        json.dump({
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
        }, f)


def get_youtube_service(channel_id):
    from googleapiclient.discovery import build
    creds = load_credentials(channel_id)
    return build('youtube', 'v3', credentials=creds)


def _make_title(genre, duration_minutes, video_type='long_form'):
    genre_map = {'horror': 'Horror', 'relationship': 'Relationship Drama', 'workplace': 'Workplace'}
    label = genre_map.get(genre, genre.title())
    if video_type == 'short':
        return f"{label} Reddit Story #Shorts"
    return f"{label} Reddit Story — {duration_minutes} Minutes"


def _make_description(story, genre):
    base = (
        f"Today we're reading a chilling story from Reddit.\n\n"
        f"Original post: {story.get('url', '')}\n\n"
        f"Subscribe for daily Reddit story videos!\n\n"
        f"#reddit #{genre} #redditstories #storytelling"
    )
    return base


def upload_video(channel_id, genre, video_path, story, duration_minutes=12, video_type='long_form', thumbnail_path=None):
    """Upload a video to YouTube. Returns youtube_video_id or None."""
    for attempt in range(3):
        try:
            from googleapiclient.http import MediaFileUpload
            from googleapiclient.errors import HttpError
            youtube = get_youtube_service(channel_id)
            title = _make_title(genre, duration_minutes, video_type)
            description = _make_description(story, genre)
            tags = GENRE_TAGS.get(genre, [])

            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags,
                    'categoryId': '24',  # Entertainment
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False,
                },
            }

            media = MediaFileUpload(video_path, mimetype='video/mp4', resumable=True, chunksize=1024*1024*5)
            request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"Upload progress: {pct}%")

            video_id = response.get('id')
            logger.info(f"Uploaded video {video_id} for channel {channel_id}")

            # Set thumbnail if available
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    from googleapiclient.http import MediaFileUpload as MFU
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MFU(thumbnail_path, mimetype='image/jpeg')
                    ).execute()
                    logger.info(f"Thumbnail set for {video_id}")
                except Exception as e:
                    logger.warning(f"Thumbnail upload failed: {e}")

            _record_upload(channel_id, video_id, title, duration_minutes, 'success')
            return video_id

        except HttpError as e:
            logger.error(f"YouTube API HttpError (attempt {attempt+1}): {e}")
            if attempt < 2:
                logger.info("Retrying upload in 5 minutes...")
                time.sleep(300)
        except Exception as e:
            logger.error(f"Upload error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(300)

    logger.error(f"Upload failed after 3 attempts for channel {channel_id}")
    _record_upload(channel_id, None, _make_title(genre, duration_minutes, video_type), duration_minutes, 'failed')
    _notify_upload_failure(channel_id, genre)
    return None


def _record_upload(channel_id, video_id, title, duration, status):
    from backend.models.database import get_db
    db = get_db()
    db.execute(
        "INSERT INTO upload_history (channel_id, title, duration, status, youtube_video_id) VALUES (?,?,?,?,?)",
        (channel_id, title, duration, status, video_id)
    )
    if status == 'success':
        db.execute("UPDATE channels SET last_upload=? WHERE id=?", (datetime.now().isoformat(), channel_id))
    db.commit()
    db.close()


def _notify_upload_failure(channel_id, genre):
    from backend.services.notifications import send_upload_failure_notification
    send_upload_failure_notification(channel_id, genre)


def get_oauth_flow(client_secrets_json_str):
    """Create OAuth flow from JSON string."""
    from google_auth_oauthlib.flow import Flow
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(client_secrets_json_str)
        tmp_path = f.name
    flow = Flow.from_client_secrets_file(
        tmp_path,
        scopes=SCOPES,
        redirect_uri=_get_redirect_uri(),
    )
    os.unlink(tmp_path)
    return flow


def _get_redirect_uri():
    env = _get_env()
    host = env.get('PI_LOCAL_IP', 'localhost')
    return f"http://{host}:5000/auth/callback"


def list_youtube_channels(credentials):
    """List all YouTube channels for authenticated user."""
    from googleapiclient.discovery import build
    youtube = build('youtube', 'v3', credentials=credentials)
    response = youtube.channels().list(part='snippet,statistics', mine=True).execute()
    channels = []
    for item in response.get('items', []):
        channels.append({
            'id': item['id'],
            'name': item['snippet']['title'],
            'subscribers': item['statistics'].get('subscriberCount', 0),
            'views': item['statistics'].get('viewCount', 0),
        })
    return channels
