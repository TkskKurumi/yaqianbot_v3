from PIL import Image
from openai import OpenAI
from typing import Dict, Optional
from yaqianbot.globals.g_cfg import get as get_cfg

from openai import APIConnectionError

from PIL import Image
from io import BytesIO
import base64
from math import sqrt
from os import path
import os

def bytes2pil(bytes):
    bio = BytesIO()
    bio.write(bytes)
    bio.seek(0)
    return Image.open(bio)

def img2bytes(img: Image.Image, max_bytes=500000):
    if (img.mode == "P"):
        img = img.convert("RGBA")
    if ("A" in img.mode):
        fmt = "PNG"
        kwa = {}
    else:
        fmt = "JPEG"
        kwa = {"quality": 90}
    w, h = img.size
    def to_bytes(ratio):
        w1, h1 = round(ratio*w), round(ratio*h)
        bio = BytesIO()
        img.resize((w1, h1), resample=Image.Resampling.LANCZOS).save(bio, format=fmt, **kwa)
        size = bio.tell()
        
        bio.seek(0)
        data = bio.read()

        bio.seek(0)
        
        return bio, data, size
    
    ratio = 1
    while (ratio*w>1 and ratio*h>1):
        bio, data, size = to_bytes(ratio)
        if (size<=max_bytes):
            return fmt, bio, data, size
        else:
            ratio = min(ratio*0.9, ratio*sqrt(max_bytes/size))

def img2b64url(img: Image.Image, max_bytes=500000):
    fmt, bio, data, size = img2bytes(img, max_bytes=max_bytes)

    if (fmt == "PNG"):
        mime = "image/png"
    elif (fmt == "JPEG"):
        mime = "image/jpeg"
    else:
        raise ValueError("Format="+str(fmt))

    b64 = base64.b64encode(data).decode("ascii")

    url = f"data:{mime};base64,{b64}"
    return url

API_KEY = get_cfg("vl_model", "api_key", "")
BASE_URL = get_cfg("vl_model", "base_url", "http://192.168.31.175:12355/v1")
MODEL = get_cfg("vl_model", "model", "qwen/qwen3-vl-30b")

CLIENT = OpenAI(api_key=API_KEY, base_url=BASE_URL)
