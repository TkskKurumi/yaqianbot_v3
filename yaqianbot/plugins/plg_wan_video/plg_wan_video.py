from ...receiver import on_message, command, on_exception_send_sync
from ...adapters.base_adapter.message import BaseMessage
from ...adapters.base_adapter.mseg import BaseSendVideoFile
from PIL import Image, ImageFilter
from collections import defaultdict
from yaqianbot.globals.g_paths import get_file_path
from threading import RLock
import numpy as np
import traceback, random
from ...globals.g_threading import threading_run
from ...globals import g_threading
from ...globals import g_cfg
import yaml
from math import sqrt
from typing import Any

from io import BytesIO
from PIL import Image
from typing import Optional
import requests, time
def upload_image(host, im: Image.Image):
    bio = BytesIO()
    if ("P" in im.mode):
        im = im.convert("RGBA")
    if ("A" in im.mode):
        fmt = "PNG"
        fn = "data.png"
    else:
        fmt = "JPEG"
        fn = "data.jpg"
    im.save(bio, format=fmt)
    bio.seek(0)

    files = {"data": (fn, bio)}
    r = requests.post(f"{host}/upload_image", files=files)
    if (r.status_code==201):
        return r.json()["image_id"]
    else:
        print(r.json())
        r.raise_for_status()


class Client:

    def __init__(self, prompt, image: Optional[Image.Image]=None, negative=None, width=16, height=9, host="http://localhost:8060"):
        self.prompt = prompt
        self.negative = negative
        self.image_pil = image
        self.host = host
        if (image):
            self.image_id = upload_image(host, image)
        else:
            self.image_id = None
        self.width = width
        self.height = height
        resp = requests.post(f'{host}/create', json=self.asdict())
        if (resp.status_code==201):
            self.task_id = resp.json()["task_id"]
        else:
            print(resp.json())
            resp.raise_for_status()
        


    def asdict(self):
        def pop_none(d):
            return {k: v for k, v in d.items() if v is not None}
        return pop_none({
            "prompt": self.prompt,
            "negative": self.negative,
            "image_id": self.image_id,
            "width": self.width,
            "height": self.height
        })
    def get_status(self):
        resp = requests.get(f"{self.host}/task?task_id={self.task_id}")
        if (resp.status_code == 404):
            return "fail", "not found"
        else:
            return resp.json()["task"]["status"], resp.json()["task"].get("fail_message", None)
    def get_result_block(self):
        while (True):
            st, reason = self.get_status()
            if (st == "fail"):
                raise Exception(reason)
            elif (st == "finish"):
                print("finish")
                break
            else:
                print(st, reason)
                time.sleep(1)
    def get_bytes(self):
        resp = requests.get(f"{self.host}/get_result?task_id={self.task_id}")
        if (resp.status_code==200):
            return True, resp.content
        else:
            #  resp.raise_for_status()
            return False, resp.json()
        
DEFAULT_NEG = """
低质量，低画质，压缩损失，模糊，水印，丑陋的，多余的肢体，缺少肢体，人体结构错误，多余手指，残缺手指，黑白，色调偏淡，过曝，静止不动，打码，马赛克，肩宽
low quality, low resolution, compression loss, lossy compression, blurry, watermark, ugly, extra legs, extra arms, missing arms, missing legs, bad anatomy, extra fingers, missing fingers, monochrome, greyscale, over-exposure, static, cencored, mosaic censoring, wide shoulders, gigantic breasts, huge breasts, flat chest
"""

RUNNING_CLIENT = None


def wait_and_send(mes: BaseMessage, client: Client):
    try:
        start_t = time.time()
        wait_t = 5
        verbose_time = time.time()
        while (True):
            status, reason = client.get_status()
            print(status)
            if (status == "fail"):
                mes.sync_send(["哎呀，生成失败啦"])
                break
            elif (status == "finish"):
                mes.sync_send(["正在下载.."])
                ok, bytes = client.get_bytes()
                if (ok):
                    pth = get_file_path("wan_video", f"{client.task_id}.mp4")
                    with open(pth, "wb") as f:
                        f.write(bytes)
                    mes.sync_send(["尝试发送视频.."])
                    mes.sync_send([BaseSendVideoFile(pth)])
                else:
                    mes.sync_send([f"获取结果视频失败{str(bytes)[:50]}..."])
                break
            else:
                if (time.time() > verbose_time):
                    mes.sync_send([f"{status} {reason}生成中，已等待{time.time()-start_t:.1f}秒，{wait_t}秒后汇报状态"])
                    verbose_time = time.time()+wait_t
                    wait_t = min(wait_t*2, 120)
                time.sleep(1)
    except Exception as e:
        mes.sync_send([repr(e)])    
@on_message
@threading_run
@on_exception_send_sync
@command("#WANVideo")
def cmd_wan_video(mes: BaseMessage, *args, **kwargs):
    global RUNNING_CLIENT
    prompt = " ".join(args)
    if (RUNNING_CLIENT is not None):
        status, fail_reason = RUNNING_CLIENT.get_status()
        if (status != "fail" and status != "finish"):
            mes.sync_send(["请稍后"])
            return
    im = mes.sender.get_recent_image().get_pil()
    RUNNING_CLIENT = Client(host="http://localhost:8060", prompt=prompt, image=im)
    g_threading.pool.submit(wait_and_send, mes, RUNNING_CLIENT)