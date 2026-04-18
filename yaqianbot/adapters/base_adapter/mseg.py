from abc import ABC, abstractmethod
from PIL import Image
from typing import List
class MessageSegment(ABC):

    @abstractmethod
    def __init__(self):
        pass
    @abstractmethod
    def as_send_segment(self) -> dict:
        pass
    @property
    @abstractmethod
    def repr_text(self):
        pass
class BaseText(MessageSegment):
    def __init__(self, t):
        self.txt = t
    @property
    def repr_text(self):
        return self.txt
    def as_send_segment(self):
        return self.txt
class BaseImage(MessageSegment):
    @property
    @abstractmethod
    def is_animated(self):
        pass
    @abstractmethod
    def get_pil(self) -> Image.Image:
        pass
    @abstractmethod
    def get_animation(self) -> List[Image.Image]:
        pass
    @abstractmethod
    def get_bytes(self):
        pass
    @property
    @abstractmethod
    def unique_id(self):
        pass

class BaseSendImageSeqAnim(BaseImage):
    def __init__(self, unique_id, frames, fps):
        self.frames = frames
        self.fps = fps
        self.unique_id = unique_id
    @property
    def is_animated(self):
        return True
    def get_animation(self):
        return self.frames


class BaseVoice(MessageSegment):
    @abstractmethod
    def as_wave_data(self, samplerate=16000):
        pass

class BaseVideo(MessageSegment):
    @abstractmethod
    def get_saved_file(self):
        pass
    @property
    @abstractmethod
    def unique_id(self):
        pass
    def get_bytes(self):
        if (getattr(self, "_bytes", None) is not None):
            return self._bytes
        with open(self.get_saved_file(), "rb") as f:
            self._bytes = f.read()
        return self._bytes
class BaseSendVideoFile(BaseVideo):
    
    def get_saved_file(self):
        return self.fn
    def __init__(self, fn):
        
        self.fn = fn
        with open(fn, "rb") as f:
            self._bytes = f.read()
    @property
    def unique_id(self):
        return self.fn
    def as_send_segment(self):
        raise NotImplementedError(f"Video: {self.fn}")
    @property
    def repr_text(self):
        return "[视频]"
class BaseAt(MessageSegment):
    def __init__(self, atid):
        self.atid = atid
    @property
    def repr_text(self):
        return "@%s"%(self.atid)
class BaseReply(MessageSegment):
    def __init__(self, mid):
        self.mid = mid
    @property
    def repr_text(self):
        return "[回复]"
