import os
import sys
import json
import glob
import logging
import subprocess
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, session

logger = logging.getLogger(__name__)
system_bp = Blueprint('system', __name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def require_auth(f):
    from functools import wraps
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'authenticated' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


def read_env():
    from backend.routes.settings import read_env as _read_env
    return _read_env()


# ===== SYSTEM STATS =====
@system_bp.route('/api/system/stats')
@require_auth
def system_stats():
    stats = {}
    try:
        # CPU usage
        with open('/proc/stat') as f:
            cpu_line = f.readline()
        fields = [float(x) for x in cpu_line.strip().split()[1:]]
        idle = fields[3]
        total = sum(fields)
        stats['cpu_percent'] = round((1 - idle / total) * 100, 1)
    except Exception:
        stats['cpu_percent'] = 0

    try:
        # RAM usage
        mem = {}
        with open('/proc/meminfo') as f:
            for line in f:
                parts = line.split()
                if parts[0] in ('MemTotal:', 'MemAvailable:'):
                    mem[parts[0]] = int(parts[1])
        total_mb = mem.get('MemTotal:', 0) / 1024
        avail_mb = mem.get('MemAvailable:', 0) / 1024
        used_mb = total_mb - avail_mb
        stats['ram_used_gb'] = round(used_mb / 1024, 2)
        stats['ram_total_gb'] = round(total_mb / 1024, 2)
        stats['ram_percent'] = round((used_mb / total_mb) * 100, 1) if total_mb else 0
    except Exception:
        stats['ram_used_gb'] = 0
        stats['ram_total_gb'] = 0
        stats['ram_percent'] = 0

    try:
        # CPU Temperature
        temp_paths = [
            '/sys/class/thermal/thermal_zone0/temp',
            '/sys/devices/virtual/thermal/thermal_zone0/temp',
        ]
        temp = None
        for p in temp_paths:
            if os.path.exists(p):
                with open(p) as f:
                    temp = int(f.read().strip()) / 1000
                break
        stats['cpu_temp'] = round(temp, 1) if temp else None
    except Exception:
        stats['cpu_temp'] = None

    try:
        # Uptime
        with open('/proc/uptime') as f:
            uptime_secs = float(f.read().split()[0])
        hours = int(uptime_secs // 3600)
        minutes = int((uptime_secs % 3600) // 60)
        stats['uptime'] = f"{hours}h {minutes}m"
    except Exception:
        stats['uptime'] = 'Unknown'

    try:
        # Disk usage for videos dir
        video_dir = os.path.join(BASE_DIR, 'videos')
        result = subprocess.run(['df', '-h', video_dir], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            stats['disk_total'] = parts[1]
            stats['disk_used'] = parts[2]
            stats['disk_free'] = parts[3]
            stats['disk_percent'] = parts[4]
        else:
            stats['disk_total'] = stats['disk_used'] = stats['disk_free'] = stats['disk_percent'] = 'N/A'
    except Exception:
        stats['disk_total'] = stats['disk_used'] = stats['disk_free'] = stats['disk_percent'] = 'N/A'

    try:
        # TTS character usage this month
        tts_file = os.path.join(BASE_DIR, 'data', 'tts_usage.json')
        if os.path.exists(tts_file):
            with open(tts_file) as f:
                tts_data = json.load(f)
            now = datetime.now()
            month_key = f"{now.year}-{now.month:02d}"
            chars_used = tts_data.get(month_key, 0)
        else:
            chars_used = 0
        stats['tts_chars_used'] = chars_used
        stats['tts_chars_limit'] = 1_000_000
        stats['tts_chars_pause'] = 950_000
        stats['tts_paused'] = chars_used >= 950_000
    except Exception:
        stats['tts_chars_used'] = 0
        stats['tts_chars_limit'] = 1_000_000
        stats['tts_paused'] = False

    # External drives
    try:
        result = subprocess.run(['lsblk', '-J', '-o', 'NAME,SIZE,MOUNTPOINT,TYPE,LABEL'], capture_output=True, text=True)
        lsblk = json.loads(result.stdout)
        drives = []
        for dev in lsblk.get('blockdevices', []):
            if dev.get('type') == 'disk':
                for child in dev.get('children', []):
                    if child.get('mountpoint'):
                        drives.append({
                            'name': child['name'],
                            'size': child.get('size', ''),
                            'mountpoint': child['mountpoint'],
                            'label': child.get('label', ''),
                        })
        stats['drives'] = drives
    except Exception:
        stats['drives'] = []

    return jsonify(stats)


# ===== SHUTDOWN =====
@system_bp.route('/api/system/shutdown', methods=['POST'])
@require_auth
def shutdown():
    logger.info("System shutdown requested from dashboard.")
    import threading
    def do_shutdown():
        import time
        time.sleep(2)  # Give Flask time to send response
        subprocess.run(['sudo', 'shutdown', '-h', 'now'])
    t = threading.Thread(target=do_shutdown, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Shutting down...'})


# ===== VIDEOS PAGE =====
@system_bp.route('/api/system/videos')
@require_auth
def list_videos():
    env = read_env()
    retention_days = int(env.get('VIDEO_RETENTION_DAYS', 7))
    ready_dir = os.path.join(BASE_DIR, 'videos', 'ready')

    videos = []
    cutoff = datetime.now() - timedelta(days=retention_days)

    for pattern in ['*.mp4']:
        for fpath in glob.glob(os.path.join(ready_dir, pattern)):
            try:
                stat = os.stat(fpath)
                created = datetime.fromtimestamp(stat.st_mtime)
                size_mb = round(stat.st_size / (1024 * 1024), 1)
                fname = os.path.basename(fpath)
                age_days = (datetime.now() - created).days
                videos.append({
                    'filename': fname,
                    'path': fpath,
                    'size_mb': size_mb,
                    'created': created.isoformat(),
                    'age_days': age_days,
                    'expires_in_days': max(0, retention_days - age_days),
                    'type': 'short' if 'short' in fname.lower() else 'long_form',
                })
            except Exception:
                continue

    videos.sort(key=lambda x: x['created'], reverse=True)
    return jsonify({'videos': videos, 'retention_days': retention_days})


@system_bp.route('/api/system/videos/delete', methods=['POST'])
@require_auth
def delete_video():
    data = request.json or {}
    filename = data.get('filename', '')
    if not filename or '/' in filename or '..' in filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    ready_dir = os.path.join(BASE_DIR, 'videos', 'ready')
    fpath = os.path.join(ready_dir, filename)
    if not os.path.exists(fpath):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    os.remove(fpath)
    return jsonify({'success': True})


@system_bp.route('/api/system/videos/download/<filename>')
@require_auth
def download_video(filename):
    from flask import send_from_directory
    if '/' in filename or '..' in filename:
        return 'Invalid filename', 400
    ready_dir = os.path.join(BASE_DIR, 'videos', 'ready')
    return send_from_directory(ready_dir, filename, as_attachment=True)


@system_bp.route('/api/system/cleanup', methods=['POST'])
@require_auth
def cleanup_old_videos():
    """Delete videos older than retention period."""
    env = read_env()
    retention_days = int(env.get('VIDEO_RETENTION_DAYS', 7))
    ready_dir = os.path.join(BASE_DIR, 'videos', 'ready')
    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted = []
    for fpath in glob.glob(os.path.join(ready_dir, '*.mp4')):
        try:
            mtime = datetime.fromtimestamp(os.stat(fpath).st_mtime)
            if mtime < cutoff:
                os.remove(fpath)
                deleted.append(os.path.basename(fpath))
        except Exception:
            pass
    logger.info(f"Cleanup: deleted {len(deleted)} old videos")
    return jsonify({'success': True, 'deleted': len(deleted), 'files': deleted})


# ===== DETECT EXTERNAL DRIVES =====
@system_bp.route('/api/system/drives')
@require_auth
def list_drives():
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,SIZE,MOUNTPOINT,TYPE,LABEL,FSTYPE'],
            capture_output=True, text=True
        )
        lsblk = json.loads(result.stdout)
        drives = []
        for dev in lsblk.get('blockdevices', []):
            if dev.get('type') == 'disk':
                for child in dev.get('children', []):
                    drives.append({
                        'name': child['name'],
                        'size': child.get('size', ''),
                        'mountpoint': child.get('mountpoint') or '',
                        'label': child.get('label') or '',
                        'fstype': child.get('fstype') or '',
                        'path': f"/dev/{child['name']}",
                    })
        return jsonify({'drives': drives})
    except Exception as e:
        return jsonify({'drives': [], 'error': str(e)})


@system_bp.route('/api/system/mount-drive', methods=['POST'])
@require_auth
def mount_drive():
    data = request.json or {}
    device = data.get('device', '')
    if not device.startswith('/dev/'):
        return jsonify({'success': False, 'error': 'Invalid device path'}), 400
    mount_point = os.path.join(BASE_DIR, 'videos')
    try:
        os.makedirs(mount_point, exist_ok=True)
        result = subprocess.run(
            ['sudo', 'mount', device, mount_point],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Save selected drive to .env
            from backend.routes.settings import write_env_key
            write_env_key('EXTERNAL_DRIVE', device)
            logger.info(f"Drive {device} mounted at {mount_point}")
            return jsonify({'success': True, 'message': f'Drive mounted at {mount_point}'})
        return jsonify({'success': False, 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
