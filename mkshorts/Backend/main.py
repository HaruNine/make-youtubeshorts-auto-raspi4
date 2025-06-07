import os
import uuid
import random
import datetime
import gc
import logging
import moviepy.config as mpy_config

from datetime import timedelta
from termcolor import colored
from dotenv import load_dotenv
from moviepy import *
# from moviepy.audio.fx.all import audio_loop
from gpt import generate_script, get_search_terms, generate_metadata
from video import save_video, combine_videos, generate_video, generate_subtitles
from search import search_for_stock_videos
from tiktokvoice import tts
from youtube import upload_video_brand
import matplotlib
matplotlib.use('Agg')

def log_to_alog(msg: str):
    log_dir = "/app/log"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "alog.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

# logging 설정 (moviepy 내부 로그도 alog.log에 기록)
logging.basicConfig(
    filename='/app/log/alog.log',
    filemode='a',
    encoding='utf-8',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)
mpy_config.logger = logger

log_to_alog("[BOOT] main.py starting (pre-import)")

load_dotenv("/app/.env")

CONFIG = {
    "videoSubject": "romance stories",
    "voice": "en_us_002",
    "aiModel": "gpt3.5-turbo",
    "customPrompt": """
        Rule:
            1. You are an AI that writes scripts for YouTube Shorts.
            2. Only tell the story itself—never include greetings, introductions, or closing remarks.
            3. The story must be high-quality, vivid, and immersive, as if a real person is telling it from their own experience.
            4. Use true events, famous anecdotes, or believable situations as the basis for your story.
            5. Length: 200~240 tokens (60~90 seconds)
            6. Tone: Fast-paced, captivating, and conversational—like someone sharing a story with a friend.
            7. Structure: Only the story body, no hook, no CTA, no summary.
            8. Language: English
            9. No section breaks, natural flow.
            10. Use punctuation for flow.
            11. Never use hashtags or emojis.
            12. Make the story sound authentic and personal, even if you have to creatively adapt real events.
            13. The story should be either funny or sad romance, but always captivating.

        Topic: {videoSubject}
        """,
    "useMusic": False,
    "automateYoutubeUpload": True,
    "zipUrl": "/app/Songs/songs.zip",
    "paragraphNumber": 1,
    "threads": 1,  # OOM 방지를 위해 동시 작업 수를 1로 고정
    "subtitlesPosition": "center,center",
    "color": "#FFFFFF",
    "subtitle_background": "rgba(0, 0, 0, 180)",
    "youtube": {
        "channel_id": os.getenv("YOUTUBE_CHANNEL_ID"),
        "privacyStatus": "public",
        "credentials_path": "/app/Backend/brand-oauth2.json"
    }
}

TEMP_DIR = "/app/temp"
SUBTITLE_DIR = "/app/subtitles"


def clean_dir(directory):
    os.makedirs(directory, exist_ok=True)
    for root, _, files in os.walk(directory):
        for file in files:
            try:
                os.remove(os.path.join(root, file))
            except Exception as e:
                log_to_alog(colored(f"[-] Failed to remove {file}: {e}"))

def extract_songs(zip_path):
    from zipfile import ZipFile
    try:
        with ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(f"{TEMP_DIR}/music")
        log_to_alog(colored(f"[+] Extracted music: {zip_path}"))
    except Exception as e:
        log_to_alog(colored(f"[-] Music extraction failed: {e}"))

def get_music_files():
    music_dir = f"{TEMP_DIR}/music"
    return [os.path.join(music_dir, f) for f in os.listdir(music_dir)
            if f.lower().endswith(('.mp3', '.wav', '.ogg'))]

def search_with_fallback(term, api_key, min_dur=10, max_retry=3):
    """비디오가 없으면 키워드에 숫자, '4k', 'nature', 'background' 등 추가로 재검색"""
    fallback_terms = [
        term + " nature",
        term + " background",
        term + " stock",
        term + " video",
    ]
    tried = set()
    for t in [term] + fallback_terms:
        if t in tried:
            continue
        tried.add(t)
        found = search_for_stock_videos(t, api_key, it=15, min_dur=min_dur)
        if found:
            return found
    return []

def main():
    audio_clips = []
    try:
        clean_dir(TEMP_DIR)
        clean_dir(SUBTITLE_DIR)
        data = CONFIG

        if data["useMusic"] and data["zipUrl"]:
            extract_songs(data["zipUrl"])
            music_files = get_music_files()
            if not music_files:
                log_to_alog(colored("[-] No valid music files"))
                data["useMusic"] = False

        voice = data["voice"] or "en_us_002"
        script = generate_script(data["videoSubject"], data["paragraphNumber"], data["aiModel"], voice, data["customPrompt"])
        search_terms = get_search_terms(data["videoSubject"], 5, script, data["aiModel"])

        video_urls = []
        for term in search_terms:
            found = search_with_fallback(term, os.getenv("PEXELS_API_KEY"), min_dur=10)
            if found:
                for url in found:
                    if url not in video_urls:
                        video_urls.append(url)
                        break
            else:
                log_to_alog(colored(f"[-] No Videos found for '{term}' and fallback terms."))

        video_paths = [save_video(url) for url in video_urls]

        sentences = [s.strip() for s in script.split(". ") if s.strip()]
        audio_clips = []
        for sentence in sentences:
            tts_path = f"{TEMP_DIR}/{uuid.uuid4()}.mp3"
            tts(sentence, voice, filename=tts_path)

            if not os.path.isfile(tts_path):
                log_to_alog(colored(f"[-] Failed to create TTS file: {tts_path}"))
                continue  # skip this sentence

            clip = AudioFileClip(tts_path)
            audio_clips.append(clip)

        final_audio = concatenate_audioclips(audio_clips)
        tts_path = f"{TEMP_DIR}/{uuid.uuid4()}.mp3"
        final_audio.write_audiofile(tts_path)

        subtitles_path = generate_subtitles(tts_path, sentences, audio_clips, "en")

        temp_audio = AudioFileClip(tts_path)
        combined_path = combine_videos(video_paths, temp_audio.duration, 10, threads=data["threads"])

        final_video_path = generate_video(
            combined_video_path=combined_path,
            tts_path=tts_path,
            subtitles_path=subtitles_path,
            threads=data["threads"],
            subtitles_position=data["subtitlesPosition"],
            text_color=data["color"],
            bg_color=data["subtitle_background"]
        )

        import shutil
        from pathlib import Path
        # generate_video에서 반환된 경로(final_video_path)는 이미 절대경로임
        # 필요시 복사/이동/업로드에 그대로 사용
        log_to_alog(colored(f"[+] Final file: {final_video_path}"))

        # 업로드 시 uptemp 경로 사용
        if data["automateYoutubeUpload"]:
            title, desc, keywords = generate_metadata(data["videoSubject"], script, data["aiModel"])
            upload_video_brand(
                video_path=final_video_path,
                title=title,
                description=desc,
                category="28",
                keywords=",".join(keywords),
                config=data["youtube"]
            )

    except Exception as e:
        log_to_alog(colored(f"[ERROR] {e}"))

    finally:
        log_to_alog(colored("[Cleanup] Releasing resources...", "magenta"))
        try:
            for clip in audio_clips:
                try:
                    clip.close()
                except Exception:
                    pass
            try:
                gc.collect()
                import ctypes
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except Exception:
                pass
            log_to_alog(colored("메모리 정리 완료"))
            # clean_dir(TEMP_DIR)
            # clean_dir(SUBTITLE_DIR)
        except FileNotFoundError:
            log_to_alog(colored("[-] Cleanup failed: Directory not found"))
        except Exception as e:
            log_to_alog(colored(f"[-] Cleanup failed: {e}"))

if __name__ == "__main__":
    main()
