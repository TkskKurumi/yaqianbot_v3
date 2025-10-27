from ...receiver import on_message, command, on_exception_send_sync
from ...adapters.base_adapter.message import BaseMessage
from PIL import Image, ImageFilter
from collections import defaultdict
from threading import RLock
import numpy as np
import traceback, random
from ...globals.g_threading import threading_run
from .tag_abbr import *
from .client import Layer, LayerDiffusionRun
from ...globals import g_cfg
import yaml
from math import sqrt
from typing import Any
from .permute import get_texts
_COMMON = "high quality, highres, masterpiece, absurdres, best quality/*lowres, low quality, worst quality, blurry, jpeg artifacts, censored, bar censor, blank censor, blur censor, censored by text, glitch censor, heart censor, light censor, mosaic censoring, bad anatomy, bad face, bad hands, bad legs, bad feet, bad vulva, bad neck, bad proportions, artistic error, extra arms, fewer digits, extra digits, too many fingers*/"
@on_message
@threading_run
@on_exception_send_sync
@command("#XL标签")
def cmd_sdxl_tag(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    if (not args):
        mes.sync_send("?")
    else:
        if ("=" in args):
            idx = args.index("=")
            abbr = " ".join(args[:idx])
            if (not abbr):
                mes.sync_send("请输入缩写源")
                return
            detail = " ".join(args[idx+1:])
            # mes.sync_send("DEBUG: updating DB %s"%detail)
            detail = process_prompt(uid, detail).result
            # mes.sync_send("DEBUG: updating DB %s -> %s"%(abbr, detail))
            update_db(mes.sender.uid, abbr, detail)
            mes.sync_send("%s -> %s"%(abbr, detail))
        else:
            abbr = " ".join(args)
            detail = get_db(uid, abbr)
            if (detail is None):
                mes.sync_send("还未设定")
            else:
                mes.sync_send("%s -> %s"%(abbr, detail))
def _get_host():
    return g_cfg.get("sdxl", "host", "http://localhost:8001")
@on_message
@threading_run
@on_exception_send_sync
@command("#XL画")
def cmd_sdxl_draw(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    p = " ".join((_COMMON,)+args)
    p = process_prompt(uid, p).result

    layer = Layer(_get_host(), p)
    ldr = LayerDiffusionRun(_get_host(), [layer])
    result = ldr.run()
    mes.sync_send([result])

@on_message
@threading_run
@on_exception_send_sync
@command("#XL以图画图", kw_options={"-s", "-l", "-r"})
def cmd_sdxl_img2img(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    p = " ".join((_COMMON,)+args)
    p = process_prompt(uid, p).result

    im = mes.sender.get_recent_image()
    im = im.get_pil()

    l = kwargs.get("-l", None)
    r = kwargs.get("-r", None)
    if (l is not None and r is not None):
        mask = float((float(l)+float(r))/2)
        mes.sync_send([f"s={mask:.2f}"])
    else:
        mask = float(kwargs.get("-s", 0.65))

    # mes.sync_send(["mask=%s,kwa=%s"%(mask, kwargs)])
    l0 = Layer(_get_host(), prompt_expr=p)
    l1 = Layer(_get_host(), image=im, mask=1-mask)
    run = LayerDiffusionRun(_get_host(), [l0, l1])
    mes.sync_send([run.run()])




def for_deepseek(mes: BaseMessage, prompt):
    try:
        p = ", ".join((_COMMON, prompt))
        p = process_prompt(mes.sender.uid, p).result
        layer = Layer(_get_host(), p)
        ldr = LayerDiffusionRun(_get_host(), [layer])
        result = ldr.run()
        mes.sync_send([result])
        return "SUCCESS"
    except Exception as e:
        traceback.print_exc()
        print("deepseek requested image gen fail", e)
        return "FAIL: %s"%e

MAX_PERMUTE_QUEUE = 32
USER_PERMUTE = defaultdict(lambda:None)
USER_PERMUTE_QUEUE = defaultdict(list)
UQLOCK = RLock()
@on_message
@threading_run
@on_exception_send_sync
@command("#XLpermute")
def cmd_sdxl_permute(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    lns = "\n".join(mes.text_for_command.splitlines()[1:])
    if (not lns):
        yml = USER_PERMUTE[uid]
        if (not yml):
            mes.sync_send(["还未设定"])
            return
    else:
        yml = yaml.safe_load(lns)
        USER_PERMUTE[uid] = yml
    texts = get_texts(yml, order=True)
    with UQLOCK:
        
        USER_PERMUTE_QUEUE[uid].extend(texts)
        if (len(USER_PERMUTE_QUEUE[uid])>MAX_PERMUTE_QUEUE):
            mes.sync_send(["队列长度太长了, 缩减到%d个"%MAX_PERMUTE_QUEUE])
            ls = list(enumerate(USER_PERMUTE_QUEUE[uid]))
            ls = random.sample(ls, MAX_PERMUTE_QUEUE)
            ls.sort()
            USER_PERMUTE_QUEUE[uid] = [i for idx, i in ls]
    while (True):
        with UQLOCK:
            if (not USER_PERMUTE_QUEUE[uid]):
                break
            t = USER_PERMUTE_QUEUE[uid][0]
            USER_PERMUTE_QUEUE[uid] = USER_PERMUTE_QUEUE[uid][1:]
        mes.sync_send(["正在生成",t])
        for_deepseek(mes, t)
        if (not USER_PERMUTE_QUEUE[uid]):
            mes.sync_send(["结束了"])



REDRAW_SRC: Dict[Any, Image.Image] = {}
REDRAW_DST: Dict[Any, Image.Image] = {}

@on_message
@threading_run
@on_exception_send_sync
@command("#XL部分重画", kw_options={"-lo", "-hi", "-mix", "-t", "-blur", "-lo_dead", "-hi_dead"}, bool_options={"-src"})
def cmd_sdxl_partial(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    mes.sync_send(["DEBUG: kwa=%s"%(kwargs)])
    if (kwargs.get("-src", None)):
        REDRAW_SRC[uid] = mes.sender.get_recent_image().get_pil()
        mes.sync_send([REDRAW_SRC[uid], "底图"])
    else:
        dst = mes.sender.get_recent_image().get_pil().convert("RGB")
        src = REDRAW_SRC[uid].resize(dst.size).convert("RGB")
        w, h = src.size
        blur_r = sqrt(w*w+h*h)/100*float(kwargs.get('-blur', 1))
        tempr = sqrt(float(kwargs.get("-t", 0.2)))
        def do_tempr(arr):
            return arr**tempr
        def do_deadzone(arr, lo, hi):
            arr = arr*(1+lo+hi)-lo
            arr = np.clip(arr, a_min=0, a_max=1)
            return arr
        lo_mask = float(kwargs.get("-lo", 0))
        lo_dead = float(kwargs.get("-lo_dead", 0.3))/2
        hi_mask = float(kwargs.get("-hi", 1))
        hi_dead = float(kwargs.get("-hi_dead", 0.1))/2

        arr_src = np.asarray(src).astype(np.float32)
        arr_dst = np.asarray(dst).astype(np.float32)
        arr_dif = arr_src-arr_dst
        arr_dis = np.sqrt(np.square(arr_dif).sum(axis=-1))
        arr_dis = (arr_dis-arr_dis.min())/(arr_dis.max()-arr_dis.min())
        arr_dis = do_deadzone(arr_dis, lo_dead, hi_dead)
        arr_dis = do_tempr(arr_dis)
        img_dis = Image.fromarray((arr_dis*255).astype(np.uint8))
        if (blur_r>1):
            img_dis = img_dis.filter(ImageFilter.GaussianBlur(blur_r))
        arr_dis = np.asarray(img_dis).astype(np.float32)
        arr_dis = (arr_dis-arr_dis.min())/(arr_dis.max()-arr_dis.min())
        arr_dis = do_deadzone(arr_dis, lo_dead, hi_dead)
        arr_dis = do_tempr(arr_dis)
        arr_dis = arr_dis*(hi_mask-lo_mask) + lo_mask

        img_mask = Image.fromarray(((1-arr_dis)*255).astype(np.uint8))
        mes.sync_send([img_mask, "MASK"])

        p = ", ".join((_COMMON, " ".join(args)))
        p = process_prompt(mes.sender.uid, p).result

        l0 = Layer(_get_host(), p)
        l1 = Layer(_get_host(), image=src, mask=img_mask)

        result = LayerDiffusionRun(_get_host(), [l0, l1]).run()

        mes.sync_send([result])

