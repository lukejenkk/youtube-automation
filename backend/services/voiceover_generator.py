import os
import re
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

AUDIO_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'videos', 'temp')

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

# Voice profiles: (name, gender, style)
GOOGLE_VOICES = {
    'dark_male':      {'name': 'en-US-Neural2-D', 'ssmlGender': 'MALE',   'speakingRate': 0.90, 'pitch': -3.0},
    'calm_male':      {'name': 'en-US-Neural2-A', 'ssmlGender': 'MALE',   'speakingRate': 0.95, 'pitch': -1.0},
    'dramatic_female':{'name': 'en-US-Neural2-F', 'ssmlGender': 'FEMALE', 'speakingRate': 0.92, 'pitch': -1.5},
    'warm_female':    {'name': 'en-US-Neural2-H', 'ssmlGender': 'FEMALE', 'speakingRate': 0.95, 'pitch':  0.0},
    'energetic_male': {'name': 'en-US-Neural2-J', 'ssmlGender': 'MALE',   'speakingRate': 1.05, 'pitch':  1.0},
    'friendly_female':{'name': 'en-US-Neural2-E', 'ssmlGender': 'FEMALE', 'speakingRate': 1.00, 'pitch':  0.5},
    'authoritative':  {'name': 'en-GB-Neural2-B', 'ssmlGender': 'MALE',   'speakingRate': 0.93, 'pitch': -2.0},
    'storyteller':    {'name': 'en-AU-Neural2-B', 'ssmlGender': 'MALE',   'speakingRate': 0.92, 'pitch': -1.0},
}


def analyze_sentiment(text, title=''):
    """Analyze story text to determine tone and pick the best voice."""
    combined = (title + ' ' + text[:1000]).lower()

    # Horror / dark / scary
    horror_words = ['horror', 'scary', 'dark', 'death', 'died', 'murdered', 'blood',
                    'killer', 'monster', 'terror', 'nightmare', 'stalker', 'haunted',
                    'ghost', 'demon', 'evil', 'sinister', 'corpse', 'scream', 'fear']
    # Emotional / relationship
    emotional_words = ['love', 'heartbreak', 'crying', 'tears', 'divorce', 'cheating',
                       'betrayal', 'hurt', 'relationship', 'abuse', 'trauma', 'grief',
                       'depressed', 'anxiety', 'mother', 'father', 'family', 'daughter', 'son']
    # Funny / comedy
    funny_words = ['funny', 'hilarious', 'lol', 'joke', 'karma', 'revenge', 'petty',
                   'malicious', 'compliance', 'backfired', 'awkward', 'embarrassing', 'tifu']
    # Authoritative / documentary
    authority_words = ['crime', 'evidence', 'investigation', 'case', 'suspect', 'police',
                       'court', 'convicted', 'sentence', 'victim', 'perpetrator', 'detective']
    # Motivational / uplifting
    motivational_words = ['success', 'inspire', 'achieve', 'overcome', 'journey', 'growth',
                          'transform', 'motivation', 'goal', 'dream', 'persevere', 'triumph']

    def score(words):
        return sum(1 for w in words if w in combined)

    scores = {
        'horror': score(horror_words),
        'emotional': score(emotional_words),
        'funny': score(funny_words),
        'authority': score(authority_words),
        'motivational': score(motivational_words),
    }

    top = max(scores, key=scores.get)
    top_score = scores[top]

    if top_score == 0:
        # Default based on genre keywords in title
        if any(w in combined for w in ['workplace', 'antiwork', 'boss', 'work']):
            return 'calm_male', scores
        return 'storyteller', scores

    voice_map = {
        'horror': 'dark_male',
        'emotional': 'warm_female',
        'funny': 'energetic_male',
        'authority': 'authoritative',
        'motivational': 'friendly_female',
    }

    chosen = voice_map[top]
    logger.info(f"Sentiment scores: {scores} → Voice: {chosen}")
    return chosen, scores


def clean_text_for_tts(text):
    """Clean Reddit story text for TTS — remove special chars, keep natural speech."""
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)

    # Remove markdown formatting
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)  # bold/italic
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)      # underscore bold/italic
    text = re.sub(r'~~([^~]+)~~', r'\1', text)               # strikethrough
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)    # links
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)   # headers
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)    # blockquotes
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)# bullet points
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)# numbered lists

    # Replace special characters that TTS reads awkwardly
    text = text.replace('&amp;', 'and')
    text = text.replace('&lt;', 'less than')
    text = text.replace('&gt;', 'greater than')
    text = text.replace('/', ' or ')      # slash → "or"
    text = text.replace('\\', ' ')        # backslash → space
    text = text.replace('|', ', ')        # pipe → comma
    text = text.replace('@', ' at ')      # @ → "at"
    text = text.replace('#', ' ')         # hashtag → space
    text = text.replace('^', ' ')         # caret → space
    text = text.replace('~', ' ')         # tilde → space
    text = text.replace('`', '')          # backtick → remove
    text = text.replace('*', '')          # asterisk → remove
    text = text.replace('_', ' ')         # underscore → space
    text = text.replace('[', '')          # brackets → remove
    text = text.replace(']', '')
    text = text.replace('{', '')          # curly braces → remove
    text = text.replace('}', '')

    # Fix ellipsis
    text = re.sub(r'\.{3,}', '...', text)

    # Fix multiple exclamation/question marks
    text = re.sub(r'[!]{2,}', '!', text)
    text = re.sub(r'[?]{2,}', '?', text)

    # Remove lines that are just special characters or very short
    lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if len(stripped) > 3 and not re.match(r'^[\W_]+$', stripped):
            lines.append(stripped)

    text = ' '.join(lines)

    # Clean up extra whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    text = text.strip()

    return text


def _get_env():
    from dotenv import dotenv_values
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    return dotenv_values(env_path)


def fetch_reddit_story(genre, min_words=1200, max_words=4000):
    """Fetch a suitable Reddit story for the given genre."""
    env = _get_env()
    try:
        import praw
        reddit = praw.Reddit(
            client_id=env.get('REDDIT_APP_ID', ''),
            client_secret=env.get('REDDIT_APP_SECRET', ''),
            user_agent=env.get('REDDIT_USER_AGENT', 'YTAutomation/1.0'),
            check_for_async=False,
        )
    except Exception as e:
        logger.error(f"Reddit client init failed: {e}")
        return None

    subreddits = GENRE_SUBREDDITS.get(genre, ['popular'])

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=30):
                if not post.is_self or not post.selftext:
                    continue
                word_count = len(post.selftext.split())
                if min_words <= word_count <= max_words:
                    cleaned = clean_text_for_tts(post.selftext)
                    if len(cleaned.split()) < min_words * 0.8:
                        continue
                    logger.info(f"Fetched story from r/{sub_name}: {post.title[:60]}")
                    return {
                        'title': post.title,
                        'text': cleaned,
                        'raw_text': post.selftext,
                        'url': f"https://reddit.com{post.permalink}",
                        'subreddit': sub_name,
                        'word_count': word_count,
                    }
        except Exception as e:
            logger.error(f"Error fetching from r/{sub_name}: {e}")
            continue

    logger.warning(f"No suitable story found for genre: {genre}")
    return None


def _split_text(text, max_chars):
    """Split text at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for sent in sentences:
        if len(current) + len(sent) < max_chars:
            current += " " + sent
        else:
            if current:
                chunks.append(current.strip())
            current = sent
    if current:
        chunks.append(current.strip())
    return chunks


def _concatenate_audio_parts(parts, output_path):
    import subprocess, shutil
    if len(parts) == 1:
        shutil.copy(parts[0], output_path)
        return
    list_file = output_path + '.txt'
    with open(list_file, 'w') as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(list_file):
        os.remove(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")


def generate_tts_google(text, output_path, api_key, voice_profile='storyteller'):
    """Generate TTS using Google Cloud TTS with selected voice profile."""
    import base64
    voice = GOOGLE_VOICES.get(voice_profile, GOOGLE_VOICES['storyteller'])
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    chunks = _split_text(text, 4800)
    audio_parts = []

    for i, chunk in enumerate(chunks):
        payload = {
            "input": {"text": chunk},
            "voice": {
                "languageCode": voice['name'][:5],
                "name": voice['name'],
                "ssmlGender": voice['ssmlGender']
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": voice['speakingRate'],
                "pitch": voice['pitch'],
            },
        }
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                part_path = output_path.replace('.mp3', f'_part{i}.mp3')
                with open(part_path, 'wb') as f:
                    f.write(base64.b64decode(data['audioContent']))
                audio_parts.append(part_path)

                # Track TTS usage
                chars_used = len(chunk)
                _track_tts_usage(chars_used)
                break
            except Exception as e:
                logger.error(f"Google TTS chunk {i} attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    raise

    _concatenate_audio_parts(audio_parts, output_path)
    for p in audio_parts:
        if os.path.exists(p):
            os.remove(p)
    return output_path


def generate_tts_elevenlabs(text, output_path, api_key):
    """Generate TTS using ElevenLabs."""
    voice_id = "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    chunks = _split_text(text, 2500)
    audio_parts = []

    for i, chunk in enumerate(chunks):
        payload = {
            "text": chunk,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        for attempt in range(3):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                part_path = output_path.replace('.mp3', f'_part{i}.mp3')
                with open(part_path, 'wb') as f:
                    f.write(resp.content)
                audio_parts.append(part_path)
                _track_tts_usage(len(chunk))
                break
            except Exception as e:
                logger.error(f"ElevenLabs chunk {i} attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    raise

    _concatenate_audio_parts(audio_parts, output_path)
    for p in audio_parts:
        if os.path.exists(p):
            os.remove(p)
    return output_path


def _track_tts_usage(chars):
    """Track TTS character usage for the current month."""
    import json
    data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    tts_file = os.path.join(data_dir, 'tts_usage.json')
    month_key = datetime.now().strftime('%Y-%m')
    try:
        usage = {}
        if os.path.exists(tts_file):
            with open(tts_file) as f:
                usage = json.load(f)
        usage[month_key] = usage.get(month_key, 0) + chars
        with open(tts_file, 'w') as f:
            json.dump(usage, f)
    except Exception as e:
        logger.error(f"TTS usage tracking failed: {e}")


def _is_tts_limit_reached():
    """Check if TTS character limit has been hit this month."""
    import json
    data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    tts_file = os.path.join(data_dir, 'tts_usage.json')
    month_key = datetime.now().strftime('%Y-%m')
    try:
        if os.path.exists(tts_file):
            with open(tts_file) as f:
                usage = json.load(f)
            return usage.get(month_key, 0) >= 950_000
    except Exception:
        pass
    return False


def generate_voiceover(genre, output_filename=None):
    """Full pipeline: fetch story → clean → analyze sentiment → pick voice → generate TTS."""
    env = _get_env()
    os.makedirs(AUDIO_DIR, exist_ok=True)

    # Check TTS limit
    if _is_tts_limit_reached():
        logger.warning("TTS character limit reached (950K). Pausing voiceover generation.")
        return None

    # Fetch story
    story = fetch_reddit_story(genre)
    if not story:
        logger.error(f"Could not get story for genre: {genre}")
        return None

    if not output_filename:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{genre.replace(' ','_')}_{ts}.mp3"

    output_path = os.path.join(AUDIO_DIR, output_filename)
    tts_provider = env.get('TTS_PROVIDER', 'google').lower()

    # Analyze sentiment and pick voice
    voice_profile, sentiment_scores = analyze_sentiment(story['text'], story['title'])
    logger.info(f"Story sentiment → voice profile: {voice_profile}")
    story['voice_profile'] = voice_profile
    story['sentiment_scores'] = sentiment_scores

    try:
        if tts_provider == 'elevenlabs':
            api_key = env.get('ELEVENLABS_API_KEY', '')
            if not api_key:
                raise ValueError("ElevenLabs API key not configured")
            generate_tts_elevenlabs(story['text'], output_path, api_key)
        else:
            api_key = env.get('GOOGLE_TTS_API_KEY', '')
            if not api_key:
                raise ValueError("Google TTS API key not configured")
            generate_tts_google(story['text'], output_path, api_key, voice_profile)

        logger.info(f"Voiceover generated: {output_path} (voice: {voice_profile})")
        return {'audio_path': output_path, 'story': story, 'voice_profile': voice_profile}

    except Exception as e:
        logger.error(f"Voiceover generation failed for genre {genre}: {e}")
        return None
