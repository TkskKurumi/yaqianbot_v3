from abc import ABC, abstractmethod
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
    def get_pil(self):
        pass
    @abstractmethod
    def get_animation(self):
        pass
    @abstractmethod
    def get_bytes(self):
        pass
    @property
    @abstractmethod
    def unique_id(self):
        pass
class BaseVoice(MessageSegment):
    @abstractmethod
    def as_wave_data(self, samplerate=16000):
        pass
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
