import os
import requests
import logging
import time
from datetime import datetime
from backend.models.database import get_db

logger = logging.getLogger(__name__)

VIDEOS_RAW_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'videos', 'raw')

GENRE_KEYWORDS = {
    'horror': 'scary suspense dark thriller',
    'relationship': 'couple argument conflict relationship',
    'workplace': 'office work business professional',
}


def _already_downloaded(source_id):
    db = get_db()
    row = db.execute("SELECT id FROM stock_videos WHERE source_id = ?", (source_id,)).fetchone()
    db.close()
    return row is not None


def _record_download(source, source_id, url, local_path, genre, duration):
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO stock_videos (source, source_id, url, local_path, genre, duration) VALUES (?,?,?,?,?,?)",
        (source, source_id, url, local_path, genre, duration)
    )
    db.commit()
    db.close()


def _download_file(url, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return dest_path


def download_from_pexels(genre, api_key, max_videos=5):
    """Download stock videos from Pexels."""
    query = GENRE_KEYWORDS.get(genre, 'nature')
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": max_videos, "min_duration": 30}

    downloaded = []
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 429:
                logger.warning("Pexels rate limited, waiting 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            logger.error(f"Pexels request failed (attempt {attempt+1}): {e}")
            time.sleep(10)
    else:
        return downloaded

    for video in data.get('videos', []):
        vid_id = str(video['id'])
        source_id = f"pexels_{vid_id}"
        if _already_downloaded(source_id):
            logger.info(f"Pexels video {vid_id} already downloaded, skipping.")
            continue

        # Pick highest quality file
        files = sorted(video.get('video_files', []), key=lambda x: x.get('width', 0), reverse=True)
        if not files:
            continue

        best = files[0]
        download_url = best['link']
        duration = video.get('duration', 0)
        filename = f"pexels_{vid_id}.mp4"
        dest = os.path.join(VIDEOS_RAW_DIR, genre, filename)

        try:
            _download_file(download_url, dest)
            _record_download('pexels', source_id, download_url, dest, genre, duration)
            downloaded.append(dest)
            logger.info(f"Downloaded Pexels video {vid_id} for genre {genre}")
        except Exception as e:
            logger.error(f"Failed to download Pexels video {vid_id}: {e}")

    return downloaded


def download_from_pixabay(genre, api_key, max_videos=5):
    """Download stock videos from Pixabay."""
    query = GENRE_KEYWORDS.get(genre, 'nature')
    url = "https://pixabay.com/api/videos/"
    params = {"key": api_key, "q": query, "per_page": max_videos, "min_duration": 30}

    downloaded = []
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                logger.warning("Pixabay rate limited, waiting 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            logger.error(f"Pixabay request failed (attempt {attempt+1}): {e}")
            time.sleep(10)
    else:
        return downloaded

    for hit in data.get('hits', []):
        vid_id = str(hit['id'])
        source_id = f"pixabay_{vid_id}"
        if _already_downloaded(source_id):
            logger.info(f"Pixabay video {vid_id} already downloaded, skipping.")
            continue

        videos_dict = hit.get('videos', {})
        # Prefer large > medium > small > tiny
        for quality in ['large', 'medium', 'small', 'tiny']:
            if quality in videos_dict and videos_dict[quality].get('url'):
                download_url = videos_dict[quality]['url']
                break
        else:
            continue

        duration = hit.get('duration', 0)
        filename = f"pixabay_{vid_id}.mp4"
        dest = os.path.join(VIDEOS_RAW_DIR, genre, filename)

        try:
            _download_file(download_url, dest)
            _record_download('pixabay', source_id, download_url, dest, genre, duration)
            downloaded.append(dest)
            logger.info(f"Downloaded Pixabay video {vid_id} for genre {genre}")
        except Exception as e:
            logger.error(f"Failed to download Pixabay video {vid_id}: {e}")

    return downloaded


def run_download_for_genre(genre):
    """Run video download for a genre using configured API keys."""
    from dotenv import dotenv_values
    env = dotenv_values(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

    pexels_key = env.get('PEXELS_API_KEY', '')
    pixabay_key = env.get('PIXABAY_API_KEY', '')

    results = []
    if pexels_key:
        logger.info(f"Downloading from Pexels for genre: {genre}")
        results += download_from_pexels(genre, pexels_key)
    if pixabay_key:
        logger.info(f"Downloading from Pixabay for genre: {genre}")
        results += download_from_pixabay(genre, pixabay_key)

    if not results:
        logger.warning(f"No videos downloaded for genre {genre}. Check API keys.")

    return results
