from __future__ import annotations
from PIL import Image as _PILImage
import numpy as np
import requests
from functools import partial
from aiocqhttp import CQHttp
from os import path
from aiocqhttp.message import MessageSegment as AIOCQHTTPMessage
from ..base_adapter.message import *
from ...globals import g_requests_cache
from os import path
from typing import TYPE_CHECKING, Any, Union
from PIL.Image import Image as PILImageType
from PIL import Image as PILImage
from ...globals import g_paths
from ...globals.g_cfg import get as get_cfg
from ...globals.g_util import debug_if_cfg
from ...globals.g_threading import pool
from ...utils.pil.misc import image_randnoise
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

class CQSendVideoFile(BaseSendVideoFile):
    def as_send_segment(self):
        
        b64 = base64.b64encode(self._bytes).decode("ascii")
        return AIOCQHTTPMessage.video(
            file="base64://"+b64
        )
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
    
    def get_bytes(self):
        im = self._pil
        if ("P" in im.mode):
            format = "GIF"
            format_kwargs = {"save_all": True}
        elif ('A' in im.mode):
            format = "PNG"
            format_kwargs = {}
        
        else:
            format = "JPEG"
            format_kwargs= {"quality": 95}
        
        _1MB = 1<<20
        bytes_limit = 5*_1MB
        bytes_orig, bytes_curr, bio = None, None, None
        orig_w, orig_h = im.size
        scale = min(1, min(65000/orig_w, 65000/orig_h)) # max supported pixels
        def _save():
            nonlocal bytes_limit, bytes_orig, bytes_curr, bio, orig_w, orig_h, scale
            bio = BytesIO()
            thumbnail = im.resize((round(orig_w*scale), round(orig_h*scale)), PILImage.Resampling.BICUBIC)
            thumbnail.save(bio, format=format, **format_kwargs)
            bytes_curr = bio.tell()
            if (scale==1):
                bytes_orig = bytes_curr
            else:
                pass
            return bytes_curr
        while (_save() > bytes_limit):
            scale = 0.95*sqrt(bytes_limit/bytes_curr)*scale
        
        bio.seek(0)
        bytes = bio.read()
        bio.close()
        return bytes
    def as_send_segment(self):
        bytes = self.get_bytes()

        b64ascii = base64.b64encode(bytes).decode("ascii")
        return AIOCQHTTPMessage.image(file="base64://"+b64ascii)
    @property
    def repr_text(self):
        return "[图片]"

class CQVideo(BaseVideo):
    def __init__(self, onebot: CQHttp, event, data):
        self.onebot = onebot
        self.data = data
        self.event = event
        self.file = data["file"]
        self._saved_file = None
    @property
    def unique_id(self):
        return self.file
    def get_saved_file(self):
        dbg = partial(debug_if_cfg, ("debug", "cqvideo_down"))
        if (getattr(self, "_saved_file", None) is not None):
            if (path.exists(self._saved_file)):
                return self._saved_file
        dbg("CQVideo get video", self.data, repr(self.file))

        f = self.data["file"]
        
        url = self.data["url"]

        task = pool.submit(self.onebot.sync.get_file, file=f, self_id=self.event["self_id"])
        dbg("trying onebot.sync get video", self.unique_id, self.file)
        try:
            result = task.result(timeout=10)
            st = str(result)
            if (len(st)>1000):
                print(st[:1000] + "...")
            dbg("onebot.sync got video", self.unique_id, self.file)
            
            if ("file" in result):
                if (path.exists(result["file"])):
                    self._saved_file = result["file"]
                    return result["file"]
            if ("base64" in result):
                svpth = g_paths.get_file_path("video", self.file)
                b64 = result["base64"]
                bytes = base64.b64decode(b64)
                with open(svpth, "wb") as f:
                    f.write(bytes)
                self._bytes = bytes
                self._saved_file = svpth
                return self._saved_file
            url = result["url"]
        except Exception as e:
            # traceback.print_exc()
            dbg("Exception: ", repr(e))
        raise Exception("无法获取视频")
        dbg("CQVideo get_saved_file request", self.unique_id, url)
        resp = requests.get(url)
        
        

        self._bytes = resp.content
        self._saved_file = g_paths.get_file_path("video", self.file)
        with open(self._saved_file, "wb") as f:
            f.write(resp.content)
        return self._saved_file
    def as_send_segment(self):
        return self.data
    @property
    def repr_text(self):
        return "[视频]"
class CQImage(BaseImage):
    @classmethod
    def from_cq(cls, onebot: CQHttp, event, data) -> CQImage:
        return cls(onebot, event, data)
    def __init__(self, onebot: CQHttp, event, data):
        self.onebot = onebot
        self.data = data
        self.event = event
    @property
    def repr_text(self):
        if (self.data.get("summary")):
            return self.data["summary"]
        return "[图片]"
    def get_pil(self) -> _PILImage.Image:
        if (getattr(self, "_pil", None) is not None):
            return self._pil
        bytes = self.get_bytes()
        if (getattr(self, "_pil", None) is None):
            raise Exception("_pil not found after getting bytes")
        return self._pil
    def get_bytes(self):
        if (getattr(self, "_bytes", None) is not None):
            return self._bytes
        try:
            img_pth = self.onebot.sync.get_image(file=self.data["file"], self_id=self.event["self_id"])
            found_local_file = path.exists(img_pth)
            self._pil = _PILImage.open(img_pth)
            with open(img_pth, "rb") as f:
                self._bytes = f.read()
        except Exception:
            found_local_file = False
        
        if (not found_local_file):
            sess = g_requests_cache._goc_sess()
            r = sess.get(self.data['url'])
            bio = BytesIO()
            bio.write(r.content)
            bio.seek(0)
            self._pil = _PILImage.open(bio)
            self._bytes = r.content
        return self._bytes
            
        
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


def prepare_contents_for_send(mes: CQMessage, contents: Union[List[Any], Any], alter_img=False):
    if (not isinstance(contents, list)):
        contents = [contents]
    
    segments: List[MessageSegment] = []
    for i in contents:
        if (isinstance(i, str)):
            seg = CQSendText(i)
        elif (isinstance(i, PILImageType)):
            seg = CQSendImage(i)
        elif (isinstance(i, BaseSendVideoFile)):
            seg = CQSendVideoFile(i.fn)
        elif (isinstance(i, BaseImage)):
            seg = CQSendImage(i.get_pil())
        elif (isinstance(i, MessageSegment)):
            seg = i
        else:
            raise TypeError("未知消息内容类型 %s"%type(i))
        segments.append(seg)
    if (alter_img):
        for idx, i in enumerate(segments):
            if (isinstance(i, BaseImage)):
                pil = i.get_pil()
                alt = image_randnoise(pil, alter_img, mode=3)
                segments[idx] = CQSendImage(alt)
    segments = [i.as_send_segment() for i in segments]
    return segments

