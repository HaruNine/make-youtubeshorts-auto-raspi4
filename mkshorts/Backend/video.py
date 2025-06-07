import os
import uuid
import logging
import moviepy.config as mpy_config
import datetime


import requests
import srt_equalizer
import assemblyai as aai

from typing import List
from moviepy import *
# from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips, CompositeAudioClip
from termcolor import colored
from dotenv import load_dotenv
from datetime import timedelta
# from moviepy.video.fx import crop
from moviepy.video.tools.subtitles import SubtitlesClip
import pathlib

# .env 파일을 절대경로로 안전하게 로드
dotenv_path = os.path.join(pathlib.Path(__file__).parent.parent.parent.resolve(), ".env")
load_dotenv(dotenv_path)

ASSEMBLY_AI_API_KEY = os.getenv("ASSEMBLY_AI_API_KEY")

# 로깅 설정 (main.py와 동일하게)
logging.basicConfig(
    filename='/app/log/alog.log',
    filemode='a',
    encoding='utf-8',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# MoviePy 내부 로그도 alog.log에 기록되도록 설정
mpy_config.logger = logger

def save_video(video_url: str, directory: str = "/app/temp") -> str:
    """
    Saves a video from a given URL and returns the path to the video.

    Args:
        video_url (str): The URL of the video to save.
        directory (str): The path of the temporary directory to save the video to

    Returns:
        str: The path to the saved video.
    """
    video_id = uuid.uuid4()
    video_path = f"{directory}/{video_id}.mp4"
    with open(video_path, "wb") as f:
        f.write(requests.get(video_url).content)

    return video_path


def __generate_subtitles_assemblyai(audio_path: str, voice: str) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        audio_path (str): The path to the audio file to generate subtitles from.

    Returns:
        str: The generated subtitles
    """

    language_mapping = {
        "br": "pt",
        "id": "en", #AssemblyAI doesn't have Indonesian 
        "jp": "ja",
        "kr": "ko",
    }

    if voice in language_mapping:
        lang_code = language_mapping[voice]
    else:
        lang_code = voice

    aai.settings.api_key = ASSEMBLY_AI_API_KEY
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_path)
    subtitles = transcript.export_subtitles_srt()

    return subtitles


def __generate_subtitles_locally(sentences: List[str], audio_clips: List[AudioFileClip]) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        sentences (List[str]): all the sentences said out loud in the audio clips
        audio_clips (List[AudioFileClip]): all the individual audio clips which will make up the final audio track
    Returns:
        str: The generated subtitles
    """

    def convert_to_srt_time_format(total_seconds):
        # Convert total seconds to the SRT time format: HH:MM:SS,mmm
        if total_seconds == 0:
            return "0:00:00,0"
        return str(timedelta(seconds=total_seconds)).rstrip('0').replace('.', ',')

    start_time = 0
    subtitles = []

    for i, (sentence, audio_clip) in enumerate(zip(sentences, audio_clips), start=1):
        duration = audio_clip.duration
        end_time = start_time + duration

        # Format: subtitle index, start time --> end time, sentence
        subtitle_entry = f"{i}\n{convert_to_srt_time_format(start_time)} --> {convert_to_srt_time_format(end_time)}\n{sentence}\n"
        subtitles.append(subtitle_entry)

        start_time += duration  # Update start time for the next subtitle

    return "\n".join(subtitles)


def generate_subtitles(audio_path: str, sentences: List[str], audio_clips: List[AudioFileClip], voice: str) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        audio_path (str): The path to the audio file to generate subtitles from.
        sentences (List[str]): all the sentences said out loud in the audio clips
        audio_clips (List[AudioFileClip]): all the individual audio clips which will make up the final audio track

    Returns:
        str: The path to the generated subtitles.
    """

    def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
        # Equalize subtitles
        srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)

    # Save subtitles
    subtitles_path = f"/app/subtitles/{uuid.uuid4()}.srt"

    if ASSEMBLY_AI_API_KEY is not None and ASSEMBLY_AI_API_KEY != "":
        print(colored("[+] Creating subtitles using AssemblyAI", "blue"))
        subtitles = __generate_subtitles_assemblyai(audio_path, voice)
    else:
        print(colored("[+] Creating subtitles locally", "blue"))
        subtitles = __generate_subtitles_locally(sentences, audio_clips)
        # print(colored("[-] Local subtitle generation has been disabled for the time being.", "red"))
        # print(colored("[-] Exiting.", "red"))
        # sys.exit(1)

    with open(subtitles_path, "w") as file:
        file.write(subtitles)

    # Equalize subtitles
    equalize_subtitles(subtitles_path)

    print(colored("[+] Subtitles generated.", "green"))

    return subtitles_path


def combine_videos(video_paths: List[str], max_duration: int, max_clip_duration: int, threads: int) -> str:
    """
    Combines a list of videos into one video and returns the path to the combined video.

    Args:
        video_paths (List): A list of paths to the videos to combine.
        max_duration (int): The maximum duration of the combined video.
        max_clip_duration (int): The maximum duration of each clip.
        threads (int): The number of threads to use for the video processing.

    Returns:
        str: The path to the combined video.
    """
    video_id = uuid.uuid4()
    combined_video_path = f"/app/temp/{video_id}.mp4"
    
    # Required duration of each clip
    req_dur = max_duration / len(video_paths)

    print(colored("[+] Combining videos...", "blue"))
    print(colored(f"[+] Each clip will be maximum {req_dur} seconds long.", "blue"))

    clips = []
    tot_dur = 0
    # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
    while tot_dur < max_duration:
        for video_path in video_paths:
            clip = VideoFileClip(video_path)
            clip = clip.without_audio()
            # Check if clip is longer than the remaining audio
            if (max_duration - tot_dur) < clip.duration:
                clip = clip.subclipped(0, (max_duration - tot_dur))
            elif req_dur < clip.duration:
                clip = clip.subclipped(0, req_dur)
            clip = clip.with_fps(24)

            # Not all videos are same size,
            # so we need to resize them
            if round((clip.w/clip.h), 4) < 0.5625:
                clip = clip.cropped(width=clip.w, height=round(clip.w/0.5625), \
                                   x_center=clip.w / 2, \
                                   y_center=clip.h / 2)
            else:
                clip = clip.cropped(width=round(0.5625*clip.h), height=clip.h, \
                                   x_center=clip.w / 2, \
                                   y_center=clip.h / 2)
            clip = clip.resized((1080, 1920))

            if clip.duration > max_clip_duration:
                clip = clip.subclipped(0, max_clip_duration)

            clips.append(clip)
            tot_dur += clip.duration

    final_clip = concatenate_videoclips(clips)
    final_clip = final_clip.with_fps(24)
    final_clip.write_videofile(combined_video_path, threads=threads, fps=24)

    return combined_video_path

def generate_video(combined_video_path: str, tts_path: str, subtitles_path: str, threads: int, subtitles_position: str, text_color: str, bg_color: str) -> str:
    """
    This function creates the final video, with subtitles and audio.

    Args:
        combined_video_path (str): The path to the combined video.
        tts_path (str): The path to the text-to-speech audio.
        subtitles_path (str): The path to the subtitles.
        threads (int): The number of threads to use for the video processing.
        subtitles_position (str): The position of the subtitles.

    Returns:
        str: The path to the final video.
    """
    video_clip = VideoFileClip(combined_video_path)

    generator = lambda txt: TextClip(
        text=txt,
        font="/app/fonts/bold_font.ttf",
        font_size=100,
        size=(video_clip.w, None),
        color=text_color,
        bg_color=bg_color,
        stroke_color="black",
        stroke_width=5,
        method='label',
        text_align='center',
        horizontal_align='center',
        vertical_align='center',
        interline=3,
        duration=1
    )

    # SRT 자막을 영상 중앙에 위치, duration 속성 명시
    subtitles = SubtitlesClip(subtitles_path, make_textclip=generator).with_position(('center', 'center'))
    subtitles.duration = video_clip.duration

    # 영상+자막 합성, 사이즈 명시 (duration 인자 없이)
    result = CompositeVideoClip([
        video_clip,
        subtitles
    ], size=video_clip.size)

    # 오디오를 붙이고, 길이 맞춤
    audio = AudioFileClip(tts_path)
    result.audio = audio

    print(colored(f"[DEBUG] video_clip.duration: {video_clip.duration}", "yellow"))
    print(colored(f"[DEBUG] audio.duration: {audio.duration}", "yellow"))
    if abs(video_clip.duration - audio.duration) > 0.1:
        print(colored(f"[WARNING] 영상과 오디오 길이가 다릅니다!", "red"))

    output_path = "/app/uptemp/output.mp4"
    result.write_videofile(output_path, threads=threads or 2, fps=video_clip.fps, codec="libx264", audio_codec="aac")

    return output_path
