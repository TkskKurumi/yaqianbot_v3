from ...receiver import on_message, command, on_exception_send_sync
from ...adapters.base_adapter.message import BaseMessage
from PIL import Image, ImageFilter
from collections import defaultdict
from threading import RLock
import numpy as np
import math
import traceback, random
from ...globals.g_threading import threading_run
from .tag_abbr import *
from .client import Layer, LayerDiffusionRun
from ...globals import g_cfg
import yaml
from math import sqrt
from typing import Any
from .permute import get_texts
from . import plg_sdxl
from ...utils.pil.pal_img import img_pal

@on_message
@threading_run
@on_exception_send_sync
@command("#XLtest", kw_options={"-lo", "-hi", "-hi_area"})
def cmd_xl_test(msg: BaseMessage, *args, **kwargs):
    p = ", ".join((plg_sdxl._COMMON, " ".join(args)))
    p = process_prompt(msg.sender.uid, p).result

    im = msg.sender.get_recent_image().get_pil().convert("RGB")
    THUMB_AREA = 450*800
    
    w, h = im.size
    if (w*h>THUMB_AREA):
        ratio = sqrt(THUMB_AREA/w/h)
        im_thumb = im.resize((round(w*ratio), round(h*ratio)), Image.Resampling.LANCZOS)
    else:
        im_thumb = im
    w_mask, h_mask = im_thumb.size

    
    hi_area = float(kwargs.get("-hi_area", 0.7))
    ep = eps_gcd(1, hi_area, eps=0.03)
    block = round(1/ep)
    if (block<4):
        block = math.ceil(4/block)*block

    clu_colors, clu_num, clu_idx, clu_im = img_pal(im_thumb, k=block)

    lo = 1-float(kwargs.get("-lo", 0.05))
    hi = 1-float(kwargs.get("-hi", 0.49))

    def f(idx):
        if (idx/block < hi_area):
            return hi
        else:
            return lo

    # mask_arr = [lo if idx%2 else hi for idx in clu_idx]
    mask_arr = [f(idx) for idx in clu_idx]
    mask_arr = np.array(mask_arr).astype(np.float16).reshape((h_mask, w_mask))*255
    
    mask_im = Image.fromarray(mask_arr.astype(np.uint8))
    msg.sync_send([mask_im])

    l0 = Layer(plg_sdxl._get_host(), prompt_expr=p)
    l1 = Layer(plg_sdxl._get_host(), image=im, mask=mask_im)
    result = LayerDiffusionRun(plg_sdxl._get_host(), layers=[l0, l1]).run()

    msg.sync_send([result])


def lim_area(im: Image.Image, area=500*500):
    w, h = im.size
    if (w*h<=area):
        return im
    ratio = sqrt(area/w/h)
    w, h =round(w*ratio), round(h*ratio)
    return im.resize((w, h), Image.Resampling.LANCZOS)

def eps_gcd(a, b, eps=0.05):
    if (b<=eps):
        return a
    return eps_gcd(b, a%b, eps)

@on_message
@threading_run
@on_exception_send_sync
@command("#XL1test", kw_options={"-lo", "-hi", "-block", "-s"})
def cmd_xl1test(msg: BaseMessage, *args, **kwargs):
    im1 = msg.sender.get_recent_image().get_pil().convert("RGB")

    p = ", ".join([plg_sdxl._COMMON, "<seed:1>", " ".join(args)])
    p = process_prompt(msg.sender.uid, p).result
    host = plg_sdxl._get_host()
    l0 = Layer(host, prompt_expr=p)
    l1 = Layer(host, image=im1, mask=0.01)
    im0 = LayerDiffusionRun(host, [l0, l1]).run()
    w, h = im1.size

    block = int(kwargs.get("-block", 16))

    col0, _, _, _ = img_pal(im0, k=block)
    _, _, idxs, _ = img_pal(im1, k=block)
    im1_recolor = [col0[idx] for idx in idxs]
    im1_recolor = np.array(im1_recolor).astype(np.uint8).reshape((h, w, -1))
    im1_recolor = Image.fromarray(im1_recolor)
    msg.sync_send([im0, im1_recolor])

    if ("-lo" in kwargs and "-hi" in kwargs):
        lo = float(kwargs["-lo"])
        hi = float(kwargs["-hi"])
        s = (lo+hi)/2
    else:
        s = float(kwargs.get("-s", 0.4))

    l1 = Layer(host, image=im1_recolor, mask=1-s)
    msg.sync_send([LayerDiffusionRun(host, [l0, l1]).run(), f"s={s}"])