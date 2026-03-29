import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
STATE_FILE = os.path.join(BASE_DIR, 'data', 'scheduler_state.json')

_state = {
    'paused': False,
    'status': 'idle',
    'last_run': None,
    'next_run': None,
    'current_stage': None,
}
_lock = threading.Lock()


def _get_env():
    from dotenv import dotenv_values
    return dotenv_values(os.path.join(BASE_DIR, '.env'))


def load_state():
    global _state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                loaded = json.load(f)
                _state.update(loaded)
        except Exception:
            pass


def save_state():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(_state, f, default=str)


def get_state():
    with _lock:
        return dict(_state)


def set_paused(paused: bool):
    with _lock:
        _state['paused'] = paused
        _state['status'] = 'paused' if paused else 'idle'
    save_state()


def _set_status(status, stage=None):
    with _lock:
        _state['status'] = status
        _state['current_stage'] = stage
    save_state()


def _is_in_window():
    env = _get_env()
    now = datetime.now()
    start_str = env.get('UPLOAD_WINDOW_START', '06:00')
    end_str = env.get('UPLOAD_WINDOW_END', '22:00')
    try:
        start = datetime.strptime(start_str, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
        end = datetime.strptime(end_str, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
        return start <= now <= end
    except Exception:
        return True


def _run_pipeline():
    """Execute the full automation pipeline for all active channels."""
    from backend.models.database import get_db
    from backend.services.video_downloader import run_download_for_genre
    from backend.services.voiceover_generator import generate_voiceover
    from backend.services.video_processor import process_video
    from backend.services.video_editor import edit_video
    from backend.services.youtube_uploader import upload_video
    from backend.services.monitoring import run_monitoring, send_monthly_report_if_due

    db = get_db()
    channels = db.execute(
        "SELECT * FROM channels WHERE active=1 AND youtube_channel_id IS NOT NULL"
    ).fetchall()
    db.close()

    if not channels:
        logger.info("No active connected channels to process.")
        _set_status('idle')
        return

    env = _get_env()

    for ch in channels:
        ch = dict(ch)
        genre = ch['genre']
        channel_id = ch['id']
        video_length = ch.get('video_length', 12)

        logger.info(f"--- Starting pipeline for: {ch['name']} ({genre}) ---")

        # Stage 1: Download stock footage
        _set_status('downloading', f"Downloading footage for {ch['name']}")
        try:
            run_download_for_genre(genre)
        except Exception as e:
            logger.error(f"Download stage failed for {ch['name']}: {e}")

        # Stage 2: Generate voiceover
        _set_status('voiceover', f"Generating voiceover for {ch['name']}")
        vo_result = generate_voiceover(genre)
        if not vo_result:
            logger.error(f"Voiceover generation failed for {ch['name']}, skipping.")
            continue

        # Stage 3: Process video
        _set_status('processing', f"Processing video for {ch['name']}")
        proc_result = process_video(genre, video_length)
        if not proc_result:
            logger.error(f"Video processing failed for {ch['name']}, skipping.")
            continue

        # Stage 4: Edit video
        _set_status('editing', f"Editing video for {ch['name']}")
        edit_result = edit_video(
            genre,
            proc_result['video_path'],
            vo_result['audio_path'],
            vo_result['story'],
            channel_id,
        )
        if not edit_result:
            logger.error(f"Video editing failed for {ch['name']}, skipping.")
            continue

        # Stage 5: Upload (only if in window)
        if _is_in_window():
            _set_status('uploading', f"Uploading for {ch['name']}")

            # Upload long-form
            vid_id = upload_video(
                channel_id, genre,
                edit_result['long_form'],
                edit_result['story'],
                video_length,
                'long_form',
                proc_result.get('thumbnail_path'),
            )
            if vid_id:
                logger.info(f"Long-form uploaded: {vid_id}")

            # Upload shorts
            for i, short_path in enumerate(edit_result.get('shorts', [])):
                short_id = upload_video(
                    channel_id, genre,
                    short_path,
                    edit_result['story'],
                    1,
                    'short',
                )
                if short_id:
                    logger.info(f"Short {i+1} uploaded: {short_id}")
        else:
            logger.info(f"Outside upload window, queueing videos for {ch['name']}")

    # Run monitoring every pipeline run
    _set_status('monitoring')
    try:
        run_monitoring()
        send_monthly_report_if_due()
    except Exception as e:
        logger.error(f"Monitoring failed: {e}")

    _set_status('idle')
    with _lock:
        _state['last_run'] = datetime.now().isoformat()
    save_state()
    logger.info("Pipeline complete.")


def _scheduler_loop():
    """Main scheduler loop."""
    load_state()
    last_run_date = None

    while True:
        try:
            state = get_state()
            if state.get('paused'):
                time.sleep(30)
                continue

            env = _get_env()
            start_str = env.get('UPLOAD_WINDOW_START', '06:00')
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')

            try:
                run_at = datetime.strptime(f"{today_str} {start_str}", '%Y-%m-%d %H:%M')
            except Exception:
                run_at = now.replace(hour=6, minute=0, second=0, microsecond=0)

            # Update next_run in state
            if now < run_at:
                next_run = run_at
            else:
                next_run = run_at + timedelta(days=1)
            with _lock:
                _state['next_run'] = next_run.isoformat()
            save_state()

            # Check if it's time to run (within 1 min of start time) and haven't run today
            should_run = (
                abs((now - run_at).total_seconds()) < 60
                and last_run_date != today_str
                and now >= run_at
            )

            if should_run:
                last_run_date = today_str
                _set_status('running')
                logger.info("Scheduler: starting pipeline run")
                _run_pipeline()

            time.sleep(30)

        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            time.sleep(60)


def start_scheduler():
    """Start the background scheduler thread."""
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="SchedulerThread")
    t.start()
    logger.info("Scheduler started.")
    return t
