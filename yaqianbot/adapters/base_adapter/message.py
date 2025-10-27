from __future__ import annotations
from typing import List, Union, Any, Dict
from .sender import BaseSender
from abc import ABC, abstractmethod
from .mseg import *
class BaseMessage(ABC):
    _message_by_id: Dict[Any, BaseMessage] = {}
    texts: List[BaseText]
    images: List[BaseImage]
    sender: BaseSender
    rich: List[MessageSegment]
    reply: Any
    @abstractmethod
    def __init__(self):
        raise NotImplementedError()
    @property
    @abstractmethod
    def is_to_me(self):
        raise NotImplementedError()
    @property
    def is_su(self):
        return self.sender.is_su
    @property
    def text_for_command(self):
        return " ".join(i.txt for i in self.texts)
    @property
    def recent_or_reply_image(self):
        if (self.reply and (self.reply in self._message_by_id)):
            mes = self._message_by_id[self.reply]
            if (mes.images):
                return mes.images[-1]
        return self.sender.get_recent_image()
    
    @abstractmethod
    def get_group_name(self):
        raise NotImplementedError()

    @abstractmethod
    def sync_send(self, message):
        raise NotImplementedError()

    @property
    @abstractmethod
    def is_group(self):
        pass

    @property
    @abstractmethod
    def self_id(self):
        pass