from .base_message_segment import MessageSegment, add_type

class MSEGText:
    def __init__(self, content):
        self.content = content
    
    @classmethod
    def from_db(cls, d):
        return cls(d["content"])
    def to_db(self):
        return {
            "type": "text",
            "content": self.content
        }
    def to_deepseek(self):
        return {
            "type": "text",
            "content": self.content
        }
    def to_send(self):
        return self.content
add_type("text", MSEGText)

