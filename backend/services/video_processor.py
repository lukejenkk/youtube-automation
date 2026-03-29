import os
import subprocess
import logging
import glob
import random
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
RAW_DIR = os.path.join(BASE_DIR, 'videos', 'raw')
TEMP_DIR = os.path.join(BASE_DIR, 'videos', 'temp')
READY_DIR = os.path.join(BASE_DIR, 'videos', 'ready')


def _run_ffmpeg(cmd, description="ffmpeg"):
    logger.info(f"Running {description}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"{description} stderr: {result.stderr[-1000:]}")
        raise RuntimeError(f"{description} failed with code {result.returncode}")
    return result


def get_video_duration(path):
    """Return duration of video in seconds."""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0


def get_available_clips(genre):
    """Get list of available raw video clips for genre."""
    genre_dir = os.path.join(RAW_DIR, genre)
    if not os.path.isdir(genre_dir):
        # Fall back to any genre
        clips = glob.glob(os.path.join(RAW_DIR, '**', '*.mp4'), recursive=True)
    else:
        clips = glob.glob(os.path.join(genre_dir, '*.mp4'))
    return [c for c in clips if os.path.getsize(c) > 10000]


def create_looped_video(genre, target_duration_minutes, output_path):
    """Loop/concatenate raw clips to reach target duration."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    target_secs = target_duration_minutes * 60
    clips = get_available_clips(genre)

    if not clips:
        logger.error(f"No raw clips available for genre {genre}")
        return None

    random.shuffle(clips)

    # Build concat list, repeating clips until we have enough duration
    total_dur = 0
    concat_list = []
    while total_dur < target_secs:
        for clip in clips:
            dur = get_video_duration(clip)
            if dur > 0:
                concat_list.append(clip)
                total_dur += dur
            if total_dur >= target_secs:
                break

    if not concat_list:
        logger.error("Could not build concat list")
        return None

    list_file = os.path.join(TEMP_DIR, f"concat_{genre}_{datetime.now().strftime('%H%M%S')}.txt")
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(list_file, 'w') as f:
        for clip in concat_list:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    try:
        # Concat and trim to exact target duration
        _run_ffmpeg([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', list_file,
            '-t', str(target_secs),
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-an',
            output_path
        ], "concat video")
        logger.info(f"Looped video created: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to create looped video: {e}")
        return None
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)


def normalize_audio(input_path, output_path):
    """Normalize audio levels using ffmpeg loudnorm filter."""
    try:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', input_path,
            '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
            output_path
        ], "normalize audio")
        return output_path
    except Exception as e:
        logger.error(f"Audio normalization failed: {e}")
        return input_path


def generate_thumbnail(video_path, output_path):
    """Extract first frame as thumbnail."""
    try:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', video_path,
            '-ss', '00:00:05', '-vframes', '1',
            '-vf', 'scale=1280:720',
            output_path
        ], "generate thumbnail")
        return output_path
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        return None


def process_video(genre, target_duration_minutes=12):
    """Full video processing pipeline."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(READY_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    looped_path = os.path.join(TEMP_DIR, f"{genre}_looped_{ts}.mp4")
    final_path = os.path.join(READY_DIR, f"{genre}_video_{ts}.mp4")
    thumb_path = os.path.join(READY_DIR, f"{genre}_thumb_{ts}.jpg")

    video = create_looped_video(genre, target_duration_minutes, looped_path)
    if not video:
        return None

    thumbnail = generate_thumbnail(looped_path, thumb_path)

    # Rename looped to final (audio will be added in editor)
    import shutil
    shutil.move(looped_path, final_path)

    logger.info(f"Video processed: {final_path}")
    return {
        'video_path': final_path,
        'thumbnail_path': thumbnail,
        'duration_minutes': target_duration_minutes,
    }
