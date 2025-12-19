from .base_message_segment import MessageSegment, add_type

class MSEGRecvAny:
    def __init__(self, repr):
        self.repr = repr
    
    @classmethod
    def from_db(cls, d):
        return cls(d["repr"])
    def to_db(self):
        return {
            "type": "any",
            "repr": self.repr
        }
    def to_deepseek(self):
        return {
            "type": "any",
            "repr": self.repr
        }
    def to_send(self):
        return str(self.repr)
add_type("any", MSEGRecvAny)

