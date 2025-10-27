from __future__ import annotations
from .base_message_segment import MessageSegment, add_type
from typing import Union, Dict
from types import NoneType
from yaqianbot.adapters.base_adapter.mseg import BaseImage
from ..external_tools import volce_img_caption
from ..external_tools.volce import img2bytes
from io import BytesIO
from PIL import Image
from ..database.image import get_img_info as db_get_img_info
from ..database.image import get_img_data as db_get_img_data
from ..database.image import update_img as db_write_img
from ..database.image import update_img_info as db_update_img_info
from typing import Protocol
import hashlib
class ImageProvider(Protocol):
    unique_id: str
    def get_bytes(self) -> bytes: ...
    def get_pil(self) -> Image.Image: ...

class LiteralPILProvider(ImageProvider):
    def __init__(self, pil):
        self.pil = pil
        fmt, bio, self._bytes, size = img2bytes(pil)
        sha = hashlib.sha256()
        sha.update(self._bytes)
        self.unique_id = sha.hexdigest()
    def get_bytes(self):
        return self._bytes
    def get_pil(self):
        return self.pil

class MSEGImage(MessageSegment):
    _opened: Dict[str, MSEGImage] = {}
    image_id: str
    desc    : Union[str, NoneType]
    base_img: Union[BaseImage, NoneType]
    
    def __init__(self,
                 image_id: Union[str, NoneType] = None,
                 desc: Union[str, NoneType]=None,
                 base_img: Union[ImageProvider, NoneType]=None
                 ):
        self.desc = desc
        if (base_img is not None):
            self.image_id = base_img.unique_id
            self.base_img = base_img
        elif (image_id is None):
            raise ValueError("Either image_id or base_img should be provided.")
        else:
            self.image_id = image_id
            self.base_img = None
        if (self.image_id not in self._opened):
            self._opened[self.image_id] = self
    def save_data_to_db(self):
        if (db_get_img_data(self.image_id) is not None):
            return
        data = self.base_img.get_bytes()
        db_write_img(self.image_id, data=data)
    def get_pil(self):
        if (self.base_img):
            return self.base_img.get_pil()
        elif (db_get_img_data(self.image_id) is not None):
            bio = BytesIO()
            bio.write(db_get_img_data(self.image_id))
            bio.seek(0)
            pil = Image.open(bio)
            return pil
    def get_desc(self):
        if (self.desc is not None):
            return self.desc
        self.desc = db_get_img_info(self.image_id, "desc", None)
        if (self.desc is not None):
            return self.desc
        pil = self.get_pil()
        self.desc = volce_img_caption(pil)
        db_update_img_info(self.image_id, {"desc": self.desc})
        return self.desc

    @classmethod
    def from_db(cls, j):
        image_id = j["image_id"]
        if (image_id in cls._opened):
            return cls._opened[image_id]
        ret = cls(image_id=image_id)
        cls._opened[image_id] = ret
        return ret
    def to_db(self):
        self.save_data_to_db()
        return {
            "type": "image",
            "image_id": self.image_id
        }
    def to_deepseek(self):
        ret = {
            "type": "image",
            "image_id": self.image_id,
            "desc": self.get_desc()
        }
        if (db_get_img_info(self.image_id, "assistant_gen_desc", None) is not None):
            ret["assistant_gen_desc"] = db_get_img_info(self.image_id, "assistant_gen_desc", None)
        return ret
    def to_send(self):
        return self.get_pil()
add_type("image", MSEGImage)
