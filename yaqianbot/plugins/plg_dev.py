from ..receiver import on_message, command, is_su, on_exception_send_sync
from ..adapters.base_adapter.message import BaseMessage
from PIL import Image
import numpy as np
import json
from ..globals.g_threading import threading_run
from ..utils.debug_obj_schema import obj_schema_str

@on_message
@command("/test")
def cmd_test(mes: BaseMessage, *args, **kwargs):
    print(mes, args, kwargs)
    arr = np.random.uniform(0, 255, (100, 100, 3)).astype(np.uint8)
    im = Image.fromarray(arr)
    mes.sync_send(["hello", im, str(mes.is_su)])

@on_message
@command("/rpic")
def cmd_rpic(mes: BaseMessage, *args, **kwargs):
    mes.sync_send(mes.recent_or_reply_image)

@on_message
@is_su
@on_exception_send_sync
@command("#exec")
def cmd_exec(mes: BaseMessage, *args, **kwargs):
    contents = mes.text_for_command
    exec(contents)

@on_message
def cmd_bili_xcx(mes: BaseMessage):
    if (not hasattr(mes, "json_msg")):
        return
    if (not getattr(mes, "json_msg", None)):
        return
    json_msg = mes.json_msg
    if (not json_msg.get("data", None)):
        return
    data = json_msg["data"]
    print('DEBUG: json_msg["data"]', data)
    if (not data.get("data", None)):
        return
    data = data["data"]
    if (isinstance(data, str)):
        data = json.loads(data)
    print('DEBUG: json_msg["data"]["data"]', data)


    if (not data.get("meta", None)):
        return
    meta = data["meta"]

    if (meta.get("detail_1", None)):
        detail_1 = meta["detail_1"]
        if (detail_1.get("qqdocurl")):
            url = detail_1["qqdocurl"]
            print("URL", url)
            if (url.startswith("https://b23.tv") or url.startswith("https://www.zhihu.com/question")):
                if (url.find("?") != -1):
                    url = url[:url.find("?")]
            mes.sync_send(["小程序链接: "+url])
    elif (meta.get("news", None)):
        news = meta["news"]
        if (news.get("jumpUrl")):
            url = news["jumpUrl"]
            if (url.startswith("https://b23.tv") or url.startswith("https://www.zhihu.com/question")):
                if (url.find("?") != -1):
                    url = url[:url.find("?")]
            mes.sync_send(["小程序链接: "+url])

        
    