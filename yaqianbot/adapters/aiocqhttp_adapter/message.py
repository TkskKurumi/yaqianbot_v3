from __future__ import annotations
from aiocqhttp import CQHttp
from ...globals import g_requests_cache
from os import path
from PIL import Image as _PILImage
from ..base_adapter import BaseMessage
from ..base_adapter.message import *
from ...utils.debug_obj_schema import obj_schema_str
from .sender import CQSender
from typing import Any, List
from .mseg import *
from ...globals import g_threading

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
                img = CQImage(onebot, i["data"])
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
    
    def sync_send(self, contents):
        contents = prepare_contents_for_send(self, contents)

        send_kwargs = {
            "message_type": self.event["message_type"],
            "self_id": self.event["self_id"],
            "user_id": self.event["user_id"]
        }
        if (self.event["message_type"] != "private"):
            send_kwargs["group_id"] = self.event["group_id"]
        send_kwargs["message"] = contents
        if (True):
            print("DEBUG: send kwargs", obj_schema_str(send_kwargs))
        result = self.onebot.sync.send_msg(**send_kwargs)
        mid = result["message_id"]
        if (_any_sent_img(contents)):
            mid = set_mes_img(mid, _any_sent_img(contents))
        print("DEBUG: send success, result", obj_schema_str(result))
        return contents
