import os
import subprocess
import logging
import textwrap
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
TEMP_DIR = os.path.join(BASE_DIR, 'videos', 'temp')
READY_DIR = os.path.join(BASE_DIR, 'videos', 'ready')

# Call-to-action text for end of Shorts
CTA_TEXT = "Watch the full video on the channel above. Don't forget to like and subscribe for more stories."


def _run_ffmpeg(cmd, description="ffmpeg"):
    logger.info(f"Running: {description}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"{description} stderr: {result.stderr[-800:]}")
        raise RuntimeError(f"{description} failed (code {result.returncode})")
    return result


def get_audio_duration(path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
           '-of', 'default=noprint_wrappers=1:nokey=1', path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0


def combine_video_audio(video_path, audio_path, output_path):
    """Merge stock video with voiceover, loop video to match audio length."""
    audio_dur = get_audio_duration(audio_path)
    if audio_dur <= 0:
        raise RuntimeError("Invalid audio duration")
    _run_ffmpeg([
        'ffmpeg', '-y',
        '-stream_loop', '-1', '-i', video_path,
        '-i', audio_path,
        '-t', str(audio_dur),
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'aac', '-b:a', '192k',
        '-map', '0:v:0', '-map', '1:a:0',
        '-shortest',
        output_path
    ], "combine video+audio")
    return output_path


def add_text_overlay(video_path, text, output_path, font_size=36, y_pos='80'):
    """Add a text overlay to video."""
    safe = text.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")
    safe = textwrap.shorten(safe, width=55, placeholder='...')
    drawtext = (
        f"drawtext=text='{safe}'"
        f":fontcolor=white:fontsize={font_size}"
        f":x=(w-text_w)/2:y={y_pos}"
        f":box=1:boxcolor=black@0.55:boxborderw=10"
        f":font=Sans"
    )
    _run_ffmpeg([
        'ffmpeg', '-y', '-i', video_path,
        '-vf', drawtext,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'copy', output_path
    ], "add text overlay")
    return output_path


def extract_short_clip(video_path, start_sec, duration_sec, output_path):
    """Extract a 9:16 vertical Short clip from a long-form video."""
    _run_ffmpeg([
        'ffmpeg', '-y', '-i', video_path,
        '-ss', str(int(start_sec)), '-t', str(int(duration_sec)),
        '-vf', 'crop=ih*9/16:ih,scale=1080:1920,fps=30',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'aac', '-b:a', '128k',
        output_path
    ], f"extract short at {start_sec}s")
    return output_path


def generate_cta_audio(voice_profile, api_key, tts_provider, output_path):
    """Generate call-to-action voiceover using same voice as main story."""
    import requests, base64

    if tts_provider == 'elevenlabs':
        voice_id = "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "text": CTA_TEXT,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(resp.content)
    else:
        # Google TTS - use same voice profile as main video
        from backend.services.voiceover_generator import GOOGLE_VOICES
        voice = GOOGLE_VOICES.get(voice_profile, GOOGLE_VOICES['storyteller'])
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
        payload = {
            "input": {"text": CTA_TEXT},
            "voice": {
                "languageCode": voice['name'][:5],
                "name": voice['name'],
                "ssmlGender": voice['ssmlGender'],
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": voice['speakingRate'],
                "pitch": voice['pitch'],
            },
        }
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        with open(output_path, 'wb') as f:
            f.write(base64.b64decode(data['audioContent']))

    return output_path


def add_cta_to_short(short_path, voice_profile, output_path):
    """Append a CTA voiceover + text overlay to the end of a Short."""
    from dotenv import dotenv_values
    env = dotenv_values(os.path.join(BASE_DIR, '.env'))
    tts_provider = env.get('TTS_PROVIDER', 'google').lower()
    api_key = env.get('ELEVENLABS_API_KEY' if tts_provider == 'elevenlabs' else 'GOOGLE_TTS_API_KEY', '')

    if not api_key:
        logger.warning("No TTS API key for CTA generation — skipping CTA audio")
        import shutil
        shutil.copy(short_path, output_path)
        return output_path

    ts = datetime.now().strftime('%H%M%S%f')
    cta_audio = os.path.join(TEMP_DIR, f"cta_{ts}.mp3")
    cta_video = os.path.join(TEMP_DIR, f"cta_video_{ts}.mp4")
    merged = os.path.join(TEMP_DIR, f"short_merged_{ts}.mp4")

    try:
        # Generate CTA audio with same voice
        generate_cta_audio(voice_profile, api_key, tts_provider, cta_audio)

        cta_dur = get_audio_duration(cta_audio)
        short_dur = get_audio_duration(short_path)

        if cta_dur <= 0:
            raise RuntimeError("CTA audio has zero duration")

        # Create a short video segment for CTA (black background with text)
        cta_text = "Watch full video above\\nLike & Subscribe for more stories!"
        _run_ffmpeg([
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', f'color=c=black:s=1080x1920:d={cta_dur}:r=30',
            '-i', cta_audio,
            '-vf', (
                f"drawtext=text='Watch full video above':fontcolor=white:fontsize=52:"
                f"x=(w-text_w)/2:y=(h/2)-60:box=1:boxcolor=black@0.0:font=Sans,"
                f"drawtext=text='Like \\& Subscribe':fontcolor=#00d4ff:fontsize=42:"
                f"x=(w-text_w)/2:y=(h/2)+20:font=Sans"
            ),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-shortest',
            cta_video
        ], "create CTA video segment")

        # Concat original short + CTA segment
        list_file = os.path.join(TEMP_DIR, f"concat_{ts}.txt")
        with open(list_file, 'w') as f:
            f.write(f"file '{os.path.abspath(short_path)}'\n")
            f.write(f"file '{os.path.abspath(cta_video)}'\n")

        _run_ffmpeg([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', list_file,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            output_path
        ], "concat short + CTA")

        if os.path.exists(list_file):
            os.remove(list_file)

        logger.info(f"CTA added to Short: {output_path} ({short_dur:.1f}s + {cta_dur:.1f}s CTA)")
        return output_path

    except Exception as e:
        logger.error(f"CTA generation failed: {e} — using Short without CTA")
        import shutil
        shutil.copy(short_path, output_path)
        return output_path
    finally:
        for f in [cta_audio, cta_video]:
            if os.path.exists(f):
                os.remove(f)


def add_subtitles_to_short(video_path, text, output_path):
    """Add story preview subtitles to Short."""
    sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 10][:6]
    if not sentences:
        import shutil
        shutil.copy(video_path, output_path)
        return output_path

    parts = []
    for i, sent in enumerate(sentences):
        safe = textwrap.shorten(sent, width=38, placeholder='...')
        safe = safe.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")
        start = i * 8
        end = start + 7
        parts.append(
            f"drawtext=text='{safe}':fontcolor=white:fontsize=30:"
            f"x=(w-text_w)/2:y=h*0.72:box=1:boxcolor=black@0.6:boxborderw=8:"
            f"font=Sans:enable='between(t,{start},{end})'"
        )

    filter_str = ','.join(parts)
    try:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', video_path,
            '-vf', filter_str,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'copy', output_path
        ], "add subtitles")
        return output_path
    except Exception as e:
        logger.warning(f"Subtitle add failed: {e} — continuing without")
        import shutil
        shutil.copy(video_path, output_path)
        return output_path


def edit_video(genre, video_path, audio_path, story, channel_id):
    """
    Full editing pipeline:
    1. Combine stock video + voiceover
    2. Add story title overlay
    3. Export long-form video
    4. Extract 3 Shorts with subtitles + CTA
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(READY_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    voice_profile = story.get('voice_profile', 'storyteller')

    # Step 1: Combine video + audio
    combined_path = os.path.join(TEMP_DIR, f"combined_{ts}.mp4")
    try:
        combine_video_audio(video_path, audio_path, combined_path)
    except Exception as e:
        logger.error(f"combine_video_audio failed: {e}")
        return None

    # Step 2: Add story title overlay
    overlay_path = os.path.join(TEMP_DIR, f"overlay_{ts}.mp4")
    title_text = story.get('title', 'Reddit Story')
    try:
        add_text_overlay(combined_path, title_text, overlay_path, font_size=38, y_pos='80')
    except Exception as e:
        logger.warning(f"Title overlay failed (continuing): {e}")
        import shutil
        shutil.copy(combined_path, overlay_path)

    # Step 3: Long-form output
    long_form_path = os.path.join(READY_DIR, f"ch{channel_id}_{genre.replace(' ','_')}_longform_{ts}.mp4")
    import shutil
    shutil.copy(overlay_path, long_form_path)
    logger.info(f"Long-form ready: {long_form_path}")

    # Step 4: Generate 3 Shorts
    total_dur = get_audio_duration(combined_path)
    short_paths = []

    if total_dur > 90:
        short_starts = [15, int(total_dur * 0.35), int(total_dur * 0.65)]
    elif total_dur > 60:
        short_starts = [10, int(total_dur * 0.5)]
    else:
        short_starts = [0]

    story_text = story.get('text', '')

    for i, start in enumerate(short_starts[:3]):
        short_raw = os.path.join(TEMP_DIR, f"short_raw_{i}_{ts}.mp4")
        short_sub = os.path.join(TEMP_DIR, f"short_sub_{i}_{ts}.mp4")
        short_cta = os.path.join(TEMP_DIR, f"short_cta_{i}_{ts}.mp4")
        short_final = os.path.join(READY_DIR, f"ch{channel_id}_{genre.replace(' ','_')}_short{i+1}_{ts}.mp4")

        try:
            # Extract 50s clip (leaving room for ~10s CTA)
            extract_short_clip(combined_path, start, 50, short_raw)

            # Add subtitles
            add_subtitles_to_short(short_raw, story_text[:600], short_sub)

            # Add CTA at end (same voice as main video)
            add_cta_to_short(short_sub, voice_profile, short_cta)

            shutil.copy(short_cta, short_final)
            short_paths.append(short_final)
            logger.info(f"Short {i+1} ready: {short_final}")

        except Exception as e:
            logger.error(f"Short {i+1} failed: {e}")
        finally:
            for tmp in [short_raw, short_sub, short_cta]:
                if os.path.exists(tmp):
                    os.remove(tmp)

    # Cleanup temp files
    for tmp in [combined_path, overlay_path]:
        if os.path.exists(tmp):
            os.remove(tmp)

    return {
        'long_form': long_form_path,
        'shorts': short_paths,
        'story': story,
        'voice_profile': voice_profile,
    }
