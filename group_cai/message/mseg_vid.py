from __future__ import annotations
from os import path
import traceback
from .base_message_segment import MessageSegment, add_type
from typing import Union, Dict
from types import NoneType
from yaqianbot.globals.g_paths import get_file_path
from yaqianbot.adapters.base_adapter.mseg import BaseImage, BaseVideo
from ..database.video import get_vid_data as db_get_vid_data
from ..database.video import get_vid_info as db_get_vid_info
from ..database.video import update_vid_info as db_update_vid_info
from ..database.video import update_vid as db_write_vid
from ..external_tools.volce_video import compress as compress_video
from ..external_tools.volce_video import vid_caption as volce_vid_caption
from ..external_tools.volce_video import bytes2file
from io import BytesIO
from PIL import Image
from moviepy import VideoFileClip
from yaqianbot.utils.profile import Profiler
from yaqianbot.globals.g_util import debug_if_cfg
class MSEGVideo(MessageSegment):
    _opened: Dict[str, MSEGVideo] = {}
    video_id: str
    desc    : Union[str, NoneType]
    base_vid: Union[BaseVideo, NoneType]
    def __init__(self,
                 video_id: Union[str, NoneType] = None,
                 desc: Union[str, NoneType]=None,
                 base_vid: Union[BaseVideo, NoneType]=None
                 ):
        self.desc = desc
        if (base_vid is not None):
            self.video_id = base_vid.unique_id
            self.base_vid = base_vid
        elif (video_id is None):
            raise ValueError("Either image_id or base_img should be provided.")
        else:
            self.video_id = video_id
            self.base_vid = None
        self._saved = False
        self._file = None
    def save_data_to_db(self):
        if (self._saved):
            return
        if (db_get_vid_data(self.video_id) is not None):
            self._saved = True
            return
        data = self.base_vid.get_bytes()
        db_write_vid(self.video_id, data=data)
        self._saved = True
    def get_saved_file(self):
        def f():
            if (self.base_vid):
                return self.base_vid.get_saved_file()
            if (getattr(self, "_file", None) is not None):
                if (path.exists(self._file)):
                    return self._file
            data = db_get_vid_data(self.video_id)
            if (data is None):
                raise Exception("Video %s data not found"%self.video_id)
            pth = get_file_path("temp", 'video', "sqldump", self.video_id)
            with open(pth, "wb") as f:
                f.write(data)
            self._file = pth
            return pth
        ret = f()
        debug_if_cfg(("debug", "get_video"), "MSEGVideo get file", self.video_id, ret)
        return ret
    def get_bytes(self):
        if (self.base_vid):
            return self.base_vid.get_bytes()
        data = db_get_vid_data(self.video_id)
        if (data is None):
            raise Exception("Video %s data not found"%self.video_id)
        return data
    def get_desc(self):
        if (self.desc is not None):
            return self.desc
        self.desc = db_get_vid_info(self.video_id, "desc", None)
        if (self.desc is not None):
            return self.desc
        try:
            if (True):
                self.desc = volce_vid_caption(self.get_bytes())
            else:
                pth = self.get_saved_file()
                
                with VideoFileClip(pth, audio=False) as clip:
                    self.desc = volce_vid_caption(clip)
            db_update_vid_info(self.video_id, {"desc": self.desc})
            return self.desc
        except Exception as e:
            self.desc = None
            traceback.print_exc()
            print(self.video_id)
            return "获取视频内容失败"
        

    @classmethod
    def from_db(cls, j):
        video_id = j["video_id"]
        if (video_id in cls._opened):
            return cls._opened[video_id]
        ret = cls(video_id=video_id)
        cls._opened[video_id] = ret
        return ret
    def to_db(self):
        self.save_data_to_db()
        return {
            "type": "video",
            "video_id": self.video_id
        }
    def to_deepseek(self):
        return {
            "type": "video",
            "video_id": self.video_id,
            "desc": self.get_desc()
        }
    def to_send(self):
        if (self.base_vid):
            return self.base_vid
        else:
            return "[视频暂不支持发送^v^]"
add_type("video", MSEGVideo)
