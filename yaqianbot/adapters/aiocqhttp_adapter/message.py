from __future__ import annotations
from aiocqhttp import CQHttp
from ...globals import g_requests_cache
from ...globals.g_cfg import get as get_cfg
from os import path
import traceback
from PIL import Image as _PILImage
from ..base_adapter import BaseMessage
from ..base_adapter.message import *
from ...utils.debug_obj_schema import obj_schema_str
from .sender import CQSender
from typing import Any, List
from .mseg import *
from ...globals import g_threading
import json

MID2IMG = {}
def set_mes_img(mid, img):
    while (len(MID2IMG) > 512):
        MID2IMG.pop(next(iter(MID2IMG)), None)
    MID2IMG[mid] = img
def _any_sent_img(contents: List[MessageSegment]):
    for i in contents:
        if (isinstance(i, BaseImage)):
            return i.get_pil()
    return None

def cqmsg_from_event(onebot, event):
    texts = []
    rich = []
    images = []
    atids = set()
    reply = None
    json_msg = None
    for i in event["message"]:
        if (isinstance(i, dict)):
            if (i["type"] == 'image'):
                img = CQImage(onebot, event, i["data"])
                images.append(img)
                rich.append(img)
            elif (i["type"] == "text"):
                t = i["data"]["text"]
                texts.append(BaseText(t))
                rich.append(BaseText(t))
            elif (i["type"] == "json"):
                json_msg = i
            elif (i["type"] == "at"):
                atid = str(i["data"]["qq"])
                at = CQAt(onebot, event, i["data"]["qq"])
                atids.add(atid)
                rich.append(at)
            elif (i["type"] == "reply"):
                mid = i["data"]["id"]
                reply = CQReply(onebot, event, mid)
                rich.append(reply)
            elif (i["type"] == "video"):
                if (get_cfg("debug", "cqvideo", False)):
                    print("found video", i)
                vid = CQVideo(onebot, event, i["data"])
                rich.append(vid)
                if (get_cfg("debug", "cqvideo", False)):
                    try:
                        print(vid.get_saved_file())
                    except Exception as e:
                        traceback.print_exc()
            else:
                debug_if_cfg(("debug", "cq_unsupported_mseg"), "Unsupported message segment", i)
                if (i["type"] == "forward" and get_cfg("debug", "debug_dump_forward", False)):
                    print("debug dump fwd")
                    def f():
                        nonlocal i, onebot, event
                        print("debug dump fwd threading")
                        try:
                            fwd_id = i.get("data", {}).get("id", "")
                            fwd_msg = onebot.sync.get_forward_msg(self_id=event["self_id"], id=fwd_id)
                            with open(g_paths.get_file_path("debug", "forward", f"{fwd_id}.json"), "w", encoding="utf-8") as f:
                                json.dump(fwd_msg, f, ensure_ascii=False)
                        except Exception:
                            traceback.print_exc()
                    g_threading.pool.submit(f)

        elif (isinstance(i, str)):
            t = i["data"]["text"]
            texts.append(BaseText(t))
            rich.append(BaseText(t))
    sender = CQSender.from_onebot(onebot, event)
    msg = CQMessage(onebot, event, sender, texts, images, atids, reply, json_msg, rich)
    return msg

class CQMessage(BaseMessage):
    @classmethod
    def from_cq(cls, onebot, event):
        return cqmsg_from_event(onebot, event)
    def __init__(self, onebot: CQHttp, event, sender: CQSender, texts, images, atids, reply, json_msg, rich: List[MessageSegment]):
        self._message_by_id[event["message_id"]] = self
        self.onebot = onebot
        self.event = event
        self.texts = texts
        self.images = images
        self.sender = sender
        self.reply = reply
        self.json_msg = json_msg
        self.rich = rich
        self.atids = atids
        self.repr_text = "".join(i.repr_text for i in rich)
        if (self.images):
            self.sender.set_recent_image(self.images[-1])
            set_mes_img(self.event["message_id"], self.images[-1])
    @property
    def is_to_me(self):
        if (self.event["message_type"] == "private"):
            return True
        else:
            return str(self.event["self_id"]) in self.atids
    
    @property
    def is_group(self):
        return self.event["message_type"] == "group"

    def get_group_name(self):
        if (self.sender.group_id == "private"):
            return f"私聊-{self.sender.username}"
        else:
            gid = self.sender.group_id
            info = self.onebot.sync.get_group_info(group_id=gid, self_id=self.event["self_id"])
            return info.get("group_name", "未知群名")

    def sync_send(self, contents):
        def trial(c, alter_img):
            contents = prepare_contents_for_send(self, c, alter_img=alter_img)

            send_kwargs = {
                "message_type": self.event["message_type"],
                "self_id": self.event["self_id"],
                "user_id": self.event["user_id"]
            }
            if (self.event["message_type"] != "private"):
                send_kwargs["group_id"] = self.event["group_id"]
            send_kwargs["message"] = contents
            
            result = self.onebot.sync.send_msg(**send_kwargs)
            mid = result["message_id"]
            if (_any_sent_img(contents)):
                mid = set_mes_img(mid, _any_sent_img(contents))
            return contents
        for alter_image in [0, 0.2, 0.4, 0.6, 0.8, 1]:
            try:
                return trial(contents, alter_img=alter_image)
            except Exception as exc:
                if (alter_image==1):
                    raise exc
                

    @property
    def self_id(self):
        return str(self.event["self_id"])
    
    def get_user_avatar(self, uid=None):
        if (uid is None):
            return self.sender.get_avatar()
        url = r"http://q.qlogo.cn/headimg_dl?dst_uin=%s&spec=640&img_type=jpg"%uid
        return g_requests_cache.get_image(url)