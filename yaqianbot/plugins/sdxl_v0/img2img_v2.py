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

from ...utils.algo.km import KuhnMunkres
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

    col0, _, idx0, _ = img_pal(im0, k=block)
    col1, _, idx1, _ = img_pal(im1, k=block)
    km = KuhnMunkres()
    dists = []
    maxd = 0
    for idx, i in enumerate(col0):
        for jdx, j in enumerate(col1):
            diff = i-j
            dist = np.sqrt(np.sum(np.square(diff)))
            maxd = max(maxd, dist)
            dists.append((idx, jdx, dist))
    for idx, jdx, d in dists:
        km.add_edge(idx, jdx, maxd-d+0.001)
    matches = km.solve_match()
    ji_map = [0 for i in range(block)]
    for idx, jdx, weight in matches:
        ji_map[jdx] = idx
    ji_map = np.array(ji_map)
    idx1_remapped = ji_map[idx1]
    arr1_remapped = col0[idx1_remapped]
    im1_remapped = Image.fromarray(arr1_remapped.reshape((h, w, -1)).astype(np.uint8))

    msg.sync_send([im1_remapped])
    
    s = 1-float(kwargs.get("-s", 0.36))

    if (s<0.5):
        mn, mx = 0, s*2
    else:
        mn, mx = 2*s-1, 1
    ss = [mn+(mx-mn)*i/(block-1) for i in range(block)]
    ss = np.array(ss)
    arr_mask = ss[idx1]
    arr_mask = arr_mask.reshape((h, w))
    im_mask = Image.fromarray((arr_mask*255).astype(np.uint8))
    msg.sync_send([im_mask])
    l1 = Layer(host, image=im1_remapped, mask=im_mask)
    msg.sync_send([LayerDiffusionRun(host, [l0, l1]).run()])
    


def meow(kernel: np.ndarray, arr: np.ndarray):
    kh, kw = kernel.shape
    h, w, ch = arr.shape
    ret = 0
    newh, neww = h-kh+1, w-kw+1
    for dy in range(kh):
        for dx in range(kw):
            ret = arr[dy:dy+newh, dx:dx+neww, :]*kernel[dx, dy] + ret
    return ret

@on_message
@threading_run
@on_exception_send_sync
@command("#XL2test", kw_options={"-lo", "-hi", "-block", "-s"})
def cmd_xl2test(msg: BaseMessage, *args, **kwargs):
    im = msg.sender.get_recent_image().get_pil().convert("RGB")
    arr = np.asarray(im).astype(np.float32)
    
    kernel0 = np.array([[1, 1], [-1, -1]])
    diff0 = meow(kernel0, arr)
    dist0 = np.sqrt(np.sum(np.square(diff0), axis=-1))

    kernel1 = np.array([[-1, 1], [-1, 1]])
    diff1 = meow(kernel1, arr)
    dist1 = np.sqrt(np.sum(np.square(diff1), axis=-1))

    dist = dist0+dist1
    dist = (dist-dist.min())/(dist.max()-dist.min())
    dist_im = Image.fromarray((dist*255).astype(np.uint8))
    msg.sync_send([dist_im])


@on_message
@threading_run
@on_exception_send_sync
@command("#XL左右", kw_options={"-l", "-r", "-gap", "-ar"}, list_options={"-l", "-r"})
def cmd_xl_left_right(mes: BaseMessage, *args, **kwargs):
    cpro = " ".join(args)
    lpro = " ".join(kwargs.get("-l"))
    lpro = process_prompt(mes.sender.uid, ", ".join([plg_sdxl._COMMON, "<seed:1>", lpro, cpro])).result
    rpro = " ".join(kwargs.get("-r"))
    rpro = process_prompt(mes.sender.uid, ", ".join([plg_sdxl._COMMON, "<seed:1>", rpro, cpro])).result

    aspect_ratio = float(kwargs.get("-ar", 9/16))
    width, height = round(800*sqrt(aspect_ratio)), round(800/sqrt(aspect_ratio))

    arr = np.linspace(-1, 1, width).reshape((1, width)) + np.zeros(shape=(height, 1))
    
    gap = float(kwargs.get("-gap", 1/10))
    if (gap<1e-3):
        sat = 1e3
    else:
        sat = 1/gap
    arr = np.clip(arr*sat, -1, 1)

    arr = (arr+1)/2*255

    mask_img = Image.fromarray(arr.astype(np.uint8))

    
    host = plg_sdxl._get_host()
    l0 = Layer(host, prompt_expr=lpro)
    l1 = Layer(host, prompt_expr=rpro, mask=mask_img)
    mes.sync_send([LayerDiffusionRun(host, [l0, l1]).run()])


    