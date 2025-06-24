from __future__ import annotations
from PIL import Image as _PILImage
from aiocqhttp import CQHttp
from aiocqhttp.message import MessageSegment as AIOCQHTTPMessage
from ..base_adapter.message import *
from ...globals import g_requests_cache
from os import path
from typing import TYPE_CHECKING, Any, Union
from PIL.Image import Image as PILImageType
from PIL import Image as PILImage
import base64
from math import sqrt
from io import BytesIO
if (TYPE_CHECKING):
    from .message import CQMessage
def check_pil_is_animated(im: PILImageType):
    try:
        return im.n_frames > 1
    except AttributeError as e:
        return False

class CQSendText(BaseText):
    def as_send_segment(self):
        return AIOCQHTTPMessage.text(self.txt)

class CQSendImage(BaseImage):
    def __init__(self, pil: PILImageType):
        self._pil = pil
    @property
    def is_animated(self):
        return False
    def get_pil(self):
        return self._pil
    def get_animation(self):
        return [self._pil]
    @property
    def unique_id(self):
        return id(self)
    def as_send_segment(self):
        im = self._pil
        if ('A' in im.mode):
            format = "PNG"
            format_kwargs = {}
        else:
            format = "JPEG"
            format_kwargs= {"quality": 95}
        
        _1MB = 1<<20
        bytes_limit = 5*_1MB
        bytes_orig, bytes_curr, bio = None, None, None
        orig_w, orig_h = im.size
        scale = 1
        def _save():
            nonlocal bytes_limit, bytes_orig, bytes_curr, bio, orig_w, orig_h, scale
            bio = BytesIO()
            thumbnail = im.resize((round(orig_w*scale), round(orig_h*scale)), PILImage.Resampling.BICUBIC)
            thumbnail.save(bio, format=format, **format_kwargs)
            bytes_curr = bio.tell()
            if (scale==1):
                bytes_orig = bytes_curr
            else:
                print("DEBUG: images is compressed (%d x %d) %.1fMB -> (%d x %d) %.1f MB %s"%(orig_w, orig_h, bytes_orig/_1MB, orig_w*scale, orig_h*scale, bytes_curr/_1MB, format))
            return bytes_curr
        while (_save() > bytes_limit):
            scale = 0.95*sqrt(bytes_limit/bytes_curr)*scale
        
        bio.seek(0)
        bytes = bio.read()
        bio.close()

        b64ascii = base64.b64encode(bytes).decode("ascii")
        return AIOCQHTTPMessage.image(file="base64://"+b64ascii)
    @property
    def repr_text(self):
        return "[图片]"

class CQImage(BaseImage):
    @classmethod
    def from_cq(cls, onebot: CQHttp, data) -> CQImage:
        return cls(onebot, data)
    def __init__(self, onebot: CQHttp, data):
        self.onebot = onebot
        self.data = data
        self._pil = None
        self._anim = []
    @property
    def repr_text(self):
        if (self.data.get("summary")):
            return self.data["summary"]
        return "[图片]"
    def get_pil(self) -> _PILImage.Image:
        if (self._pil is not None):
            return self._pil
        try:
            img_pth = self.onebot.sync.get_image(self.data["file"])
            ok = path.exists(img_pth)
        except Exception:
            ok = False
        if (ok):
            self._pil = _PILImage.open(img_pth)
        else:
            self._pil = g_requests_cache.get_image(self.data["url"])
        if (check_pil_is_animated(self._pil)):
            self._anim = []
            for i in range(self._pil.n_frames):
                self._pil.seek(i)
                self._anim.append(self._pil.convert("RGBA"))
            self._pil.seek(0)
        else:
            self._anim = []
        return self._pil
    @property
    def is_animated(self):
        return check_pil_is_animated(self.get_pil())
    def get_animation(self):
        if (not self.is_animated):
            return [self.get_pil()]
        anim = []
        pil = self.get_pil()
        for i in range(pil.n_frames):
            pil.seek(i)
            anim.append(pil.convert("RGBA"))
        return anim
    def as_send_segment(self):
        return self.data
    @property
    def unique_id(self):
        return self.data["file"]

class CQAt(BaseAt):
    def __init__(self, onebot, event, atid):
        self.atid = atid
        self.onebot = onebot
        self.event = event
    def as_send_segment(self):
        return {"type": "at", "data":{"qq": self.atid}}

class CQReply(BaseReply):
    def __init__(self, onebot, event, mid):
        self.mid = mid
        self.onebot = onebot
        self.event = event
    def as_send_segment(self):
        return {"type": "reply", "data":{"id": self.mid}}
    
def prepare_contents_for_send(mes: CQMessage, contents: Union[List[Any], Any]):
    if (not isinstance(contents, list)):
        contents = [contents]
    
    segments: List[MessageSegment] = []
    for i in contents:
        if (isinstance(i, str)):
            seg = CQSendText(i)
        elif (isinstance(i, PILImageType)):
            seg = CQSendImage(i)
        else:
            raise TypeError("未知消息内容类型 %s"%type(i))
        segments.append(seg)
    segments = [i.as_send_segment() for i in segments]
    return segments
