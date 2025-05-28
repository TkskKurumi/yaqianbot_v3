from ...receiver import on_message, command, on_exception_send_sync
from ...adapters.base_adapter.message import BaseMessage
from PIL import Image
import numpy as np
from ...globals.g_threading import threading_run
from .tag_abbr import *
from .client import Layer, LayerDiffusionRun
from ...globals import g_cfg
_COMMON = "best quality, high quality, absurdres, highres, masterpiece/*worst quality, low quality, lowres, blurry, unfinished, sketch, artifacts*/"
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
    p = " ".join(args) + _COMMON
    p = process_prompt(uid, p).result

    layer = Layer(_get_host(), p)
    ldr = LayerDiffusionRun(_get_host(), [layer])
    result = ldr.run()
    mes.sync_send([result])
