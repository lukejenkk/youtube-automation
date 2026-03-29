import logging
from flask import Blueprint, jsonify, request, session, render_template_string
from backend.models.database import get_db

logger = logging.getLogger(__name__)
channels_bp = Blueprint('channels', __name__)

GENRES = [
    'Horror Stories', 'True Crime', 'Paranormal', 'Mystery',
    'Relationship Drama', 'AITA Stories', 'Workplace Stories',
    'Malicious Compliance', 'Revenge Stories', 'Family Drama',
    'Gaming', 'Tech', 'Science', 'History', 'Finance',
    'Motivational', 'Self Help', 'Fitness', 'Comedy', 'Creepy Stories',
]

GENRE_SUBREDDITS = {
    'Horror Stories': ['nosleep', 'letsnotmeet'],
    'True Crime': ['truecrime', 'UnresolvedMysteries'],
    'Paranormal': ['Paranormal', 'Ghoststories'],
    'Mystery': ['UnresolvedMysteries', 'mystery'],
    'Relationship Drama': ['relationship_advice', 'JUSTNOSO'],
    'AITA Stories': ['AmItheAsshole', 'AITAFiltered'],
    'Workplace Stories': ['antiwork', 'MaliciousCompliance'],
    'Malicious Compliance': ['MaliciousCompliance', 'pettyrevenge'],
    'Revenge Stories': ['pettyrevenge', 'ProRevenge'],
    'Family Drama': ['raisedbynarcissists', 'JUSTNOMIL'],
    'Gaming': ['gaming', 'tifu'],
    'Tech': ['technology', 'programming'],
    'Science': ['science', 'space'],
    'History': ['history', 'AskHistorians'],
    'Finance': ['personalfinance', 'wallstreetbets'],
    'Motivational': ['GetMotivated', 'DecidingToBeBetter'],
    'Self Help': ['selfimprovement', 'DecidingToBeBetter'],
    'Fitness': ['fitness', 'loseit'],
    'Comedy': ['tifu', 'funny'],
    'Creepy Stories': ['nosleep', 'creepy'],
}


def require_auth(f):
    from functools import wraps
    from flask import redirect
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'authenticated' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


@channels_bp.route('/api/channels')
@require_auth
def list_channels():
    db = get_db()
    channels = db.execute("SELECT * FROM channels ORDER BY id").fetchall()
    db.close()
    return jsonify([dict(c) for c in channels])


@channels_bp.route('/api/channels/genres')
@require_auth
def list_genres():
    return jsonify({'genres': GENRES})


@channels_bp.route('/api/channels', methods=['POST'])
@require_auth
def create_channel():
    data = request.json or {}
    name = data.get('name', 'New Channel').strip()
    genre = data.get('genre', 'Horror Stories')
    video_length_min = int(data.get('video_length_min', 10))
    video_length_max = int(data.get('video_length_max', 15))
    videos_per_day = int(data.get('videos_per_day', 1))
    shorts_per_day = int(data.get('shorts_per_day', 2))

    db = get_db()
    cursor = db.execute(
        """INSERT INTO channels 
        (name, genre, video_length_min, video_length_max, videos_per_day, shorts_per_day, active, status)
        VALUES (?,?,?,?,?,?,1,'not_connected')""",
        (name, genre, video_length_min, video_length_max, videos_per_day, shorts_per_day)
    )
    channel_id = cursor.lastrowid
    db.commit()
    row = db.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
    db.close()
    logger.info(f"Channel created: {name} ({genre})")
    return jsonify(dict(row))


@channels_bp.route('/api/channels/<int:channel_id>', methods=['PUT'])
@require_auth
def update_channel(channel_id):
    data = request.json or {}
    allowed = ['name', 'genre', 'video_length_min', 'video_length_max',
               'videos_per_day', 'shorts_per_day', 'active', 'upload_frequency']
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'No valid fields'}), 400
    set_clause = ', '.join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [channel_id]
    db = get_db()
    db.execute(f"UPDATE channels SET {set_clause} WHERE id=?", vals)
    db.commit()
    row = db.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
    db.close()
    return jsonify(dict(row))


@channels_bp.route('/api/channels/<int:channel_id>', methods=['DELETE'])
@require_auth
def delete_channel(channel_id):
    db = get_db()
    db.execute("DELETE FROM channels WHERE id=?", (channel_id,))
    db.commit()
    db.close()
    logger.info(f"Channel {channel_id} deleted.")
    return jsonify({'success': True})


@channels_bp.route('/channels/select')
def select_channel():
    if 'authenticated' not in session:
        from flask import redirect
        return redirect('/')
    yt_channels = session.get('oauth_yt_channels', [])
    channel_id = session.get('oauth_channel_id')
    error = session.pop('oauth_error', None)
    return render_template_string("""
<!DOCTYPE html>
<html>
<head><title>Select Channel</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#080808;color:#f0f0f0;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;}
.card{background:#111;border:1px solid #222;border-radius:14px;padding:2rem;min-width:360px;max-width:95vw;}
h2{color:#00d4ff;margin-bottom:1rem;font-size:1.1rem;}
select{width:100%;padding:0.7rem;background:#080808;color:#f0f0f0;border:1px solid #2a2a2a;border-radius:8px;margin-bottom:1rem;font-size:0.9rem;}
button{width:100%;padding:0.75rem;background:#00d4ff;color:#000;border:none;border-radius:8px;cursor:pointer;font-size:0.95rem;font-weight:700;}
.err{color:#ff4757;margin-bottom:1rem;font-size:0.85rem;}
p{color:#555;font-size:0.85rem;margin-bottom:1rem;}
</style></head>
<body>
<div class="card">
  <h2>Select YouTube Channel</h2>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  {% if yt_channels %}
  <p>Select which YouTube channel to connect:</p>
  <select id="yt_select">
    {% for ch in yt_channels %}
    <option value="{{ ch.id }}">{{ ch.name }} ({{ ch.subscribers }} subs)</option>
    {% endfor %}
  </select>
  <button onclick="selectChannel()">Connect This Channel</button>
  {% else %}
  <div class="err">No YouTube channels found for this Google account.</div>
  <a href="/channels" style="color:#00d4ff;">Back to Channels</a>
  {% endif %}
</div>
<script>
function selectChannel() {
  const id = document.getElementById('yt_select').value;
  fetch('/auth/select', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({youtube_channel_id: id})
  }).then(r => r.json()).then(d => {
    if (d.success) window.location.href = '/channels';
    else alert('Error: ' + d.error);
  });
}
</script>
</body></html>
""", yt_channels=yt_channels, channel_id=channel_id, error=error)
