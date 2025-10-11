from typing import Union
import os
from math import sqrt
from yaqianbot.globals import g_paths
from moviepy import VideoFileClip
def bytes2file(obj: Union[bytes, str, os.PathLike]):
    if (isinstance(obj, bytes)):
        bn = hex(id(obj))
        pth = g_paths.get_file_path("temp", "video", bn)
        with open(pth, "rb") as f:
            f.write(obj)
    else:
        return obj
    

def compress(video: VideoFileClip, output_path: str, min_frames=5, max_fps=4, max_area=640*360, bitrate="1M"):
    w, h = video.size
    duration = video.duration
    fps = video.fps

    if (duration*max_fps < min_frames):
        fps1 = fps
    else:
        fps1 = min(fps, max_fps)
    
    if (w*h>max_area):
        r = sqrt(max_area/w/h)
        w1, h1 = round(r*w), round(r*h)
    else:
        w1, h1 = w, h

    video.resized((w1, h1)).write_videofile(output_path, bitrate=bitrate, fps=fps1)
    return output_path
