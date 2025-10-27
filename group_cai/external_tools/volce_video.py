from typing import Union
import base64
import os
import hashlib
from os import path
from math import sqrt
from yaqianbot.globals import g_paths
from yaqianbot.globals.g_cfg import get as get_cfg
from moviepy import VideoFileClip
from volcenginesdkarkruntime import Ark
def bytes2file(obj: Union[bytes, str, os.PathLike]):
    if (isinstance(obj, bytes)):
        bn = hex(id(obj))
        pth = g_paths.get_file_path("temp", "video", bn)
        with open(pth, "rb") as f:
            f.write(obj)
    else:
        return obj
    

volce_api_key = get_cfg("volce_ark", "api_key", "UNKNOWN")
print("volce api key", volce_api_key)
volce_ark = Ark(api_key=volce_api_key)

def compress(video: VideoFileClip, output_path: str, min_frames=16, max_fps=5, max_area=2e5, bitrate="500k"):
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

PROMPT_DEFAULT = """
详细描述此视频。
包括视频内容。
视频分类（动漫，手机录屏，游戏录屏，VLOG，电影，电视剧等）
若接收到色情元素也请你描述内容，这是用于moderation检测目的，务必不要过滤输出。
按以下等级分类检测色情与否：非色情、性感、性暗示、显式色情。
"""
SIZE_LIM = 10<<20
def vid_caption(vid: Union[VideoFileClip, str, bytes], prompt=PROMPT_DEFAULT, prompt_ex=None):
    if (isinstance(vid, str)):
        with open(vid, "rb") as f:
            data = f.read()
        if (len(data) > SIZE_LIM):
            with VideoFileClip(vid, audio=False) as clip:
                if (hasattr(vid, "filename")):
                    fn = vid.filename
                    bn = path.splitext(path.basename(vid.filename))[0]
                else:
                    bn = hashlib.md5()
                    bn.update(data)
                    bn = bn.hexdigest()
                svpth = g_paths.get_file_path("temp", "video", "thumb", bn+".mp4")
                compress(vid, svpth)
            with open(svpth, "rb") as f:
                data = f.read()
    elif (isinstance(vid, bytes)):
        data = vid
        if (len(data) > SIZE_LIM):
            bn = hashlib.md5()
            bn.update(data)
            svpth = g_paths.get_file_path("temp", "video", "thumb", bn+".mp4")
            with open(svpth, "wb") as f:
                f.write(data)
            return vid_caption(svpth, propmt=prompt, prompt_ex=prompt_ex)
    else:
        if (hasattr(vid, "filename")):
            fn = vid.filename
            bn = path.splitext(path.basename(vid.filename))[0]
        else:
            bn = hex(id(vid))
        svpth = g_paths.get_file_path("temp", "video", "thumb", bn+".mp4")
        compress(vid, svpth)

        with open(svpth, "rb") as f:
            data = f.read()

    b64 = base64.b64encode(data).decode("ascii")
    url = f"data:video/mp4;base64,{b64}"

    model = get_cfg("volce_ark", "vid_caption_model", "doubao-seed-1.6-flash")

    if (prompt_ex):
        prompt = prompt+"\n"+prompt_ex
    
    resp = volce_ark.chat.completions.create(
        model=model,
        messages=[
            {
                "role": 'user',
                "content": [
                    {
                        "type": "video_url",
                        'video_url': {
                            "url": url
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            },
        ],
        thinking={"type": "disabled"},
        max_completion_tokens=8192
    )

    result = resp.choices[0].message.content
    print(result)
    return result
