from ..external_tools.volce_video import compress
from moviepy.video.io.VideoFileClip import VideoFileClip
from yaqianbot.globals.g_paths import get_file_path

with VideoFileClip(r"D:\Streaming\2024\Replay 2025-10-07 10-14-03.flv") as clip:
    out = get_file_path("./tmp.mp4")
    print(compress(clip, out))
