from abc import ABC, abstractmethod
from typing import List
from .base_message_segment import MessageSegment
from .base_message_segment import from_db as mseg_from_db
from typing import Dict, Mapping, Optional, Any
import json
class Message(ABC):
    @classmethod
    @abstractmethod
    def from_db(cls, j):
        pass
    @abstractmethod
    def to_db(self):
        pass
    @abstractmethod
    def to_deepseek(self):
        pass
class MessageTool(Message):
    def __init__(self, data):
        self.data = data
    def to_db(self):
        return {
            "type": "tool",
            "data": self.data
        }
    @classmethod
    def from_db(cls, j):
        return cls(j["data"])
    def to_deepseek(self):
        return self.data
class MessageUser(Message):
    content: List[MessageSegment]
    def __init__(self, username, userid, date, content: List[MessageSegment], optional: Optional[Mapping[str, Any]]=None):
        self.username = username
        self.userid   = userid
        self.date     = date
        self.content = content
        self.optional = optional
    @classmethod
    def from_db(cls, d: Dict):
        username = d["username"]
        userid   = d["userid"]
        date     = d["date"]
        content  = [mseg_from_db(i) for i in d["content"]]
        opt      = d.get("optional", None)
        return cls(username, userid, date, content, opt)
    def to_db(self):
        return {
            "type": "user",
            "username": self.username,
            "userid"  : self.userid,
            "date"    : self.date,
            "content": [i.to_db() for i in self.content],
            "optional": self.optional
        }
    def to_deepseek(self):
        data = {
            "username": self.username,
            "userid"  : self.userid,
            "date"    : self.date,
            "content" : [i.to_deepseek() for i in self.content],
            "optional": self.optional
        }
        datastr = json.dumps(data, ensure_ascii=False)
        return {
            "role": "user",
            "content": datastr
        }
class MessageAssistant(Message):
    content: List[MessageSegment]
    def __init__(self, content: List[MessageSegment]):
        self.content = content
    @classmethod
    def from_db(cls, d: Dict):
        content = [mseg_from_db(i) for i in d["content"]]
        return cls(content)
    def to_db(self):
        return {
            "type": "assistant",
            "content": [i.to_db() for i in self.content]
        }
    def to_deepseek(self):
        content = [i.to_deepseek() for i in self.content]
        datastr = json.dumps(content, ensure_ascii=False)
        return {
            "role": "assistant",
            "content": datastr
        }
def mes_from_db(d):
    if (d["type"] == "assistant"):
        return MessageAssistant.from_db(d)
    elif (d["type"] == "user"):
        return MessageUser.from_db(d)
    elif (d["type"] == "tool"):
        return MessageTool.from_db(d)
    else:
        raise ValueError("DB Message Type %s"%d["type"])