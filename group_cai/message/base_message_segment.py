from abc import ABC, abstractmethod
from typing import Dict, Type



class MessageSegment(ABC):
    @classmethod
    @abstractmethod
    def from_db(cls, j):
        pass
    @abstractmethod
    def to_deepseek(self):
        pass
    @abstractmethod
    def to_db(self):
        pass
    @abstractmethod
    def to_send(self):
        pass

TYPE2CLS: Dict[str, Type[MessageSegment]] = {}
def add_type(typename, cls):
    TYPE2CLS[typename] = cls
def from_db(d):
    typename = d["type"]
    cls = TYPE2CLS[typename]
    return cls.from_db(d)


