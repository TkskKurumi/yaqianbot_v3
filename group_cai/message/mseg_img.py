from __future__ import annotations
from .base_message_segment import MessageSegment, add_type
from typing import Union, Dict
from types import NoneType
from yaqianbot.adapters.base_adapter.mseg import BaseImage
from ..database.image import get_image_data as db_get_image_data
from ..database.image import get_image_desc as db_get_image_desc
from ..database.image import update_image as db_update_image
from ..external_tools import volce_img_caption
from io import BytesIO
from PIL import Image
class MSEGImage(MessageSegment):
    _opened: Dict[str, MSEGImage] = {}
    image_id: str
    desc    : Union[str, NoneType]
    base_img: Union[BaseImage, NoneType]
    def __init__(self,
                 image_id: Union[str, NoneType] = None,
                 desc: Union[str, NoneType]=None,
                 base_img: Union[BaseImage, NoneType]=None
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

    def save_data_to_db(self):
        if (db_get_image_data(self.image_id) is not None):
            return
        data = self.base_img.get_bytes()
        db_update_image(self.image_id, data=data)
    def get_pil(self):
        if (self.base_img):
            return self.base_img.get_pil()
        elif (db_get_image_data(self.image_id) is not None):
            bio = BytesIO()
            bio.write(db_get_image_data(self.image_id))
            bio.seek(0)
            pil = Image.open(bio)
            return pil
    def get_desc(self):
        if (self.desc is not None):
            return self.desc
        self.desc = db_get_image_desc(self.image_id)
        if (self.desc is not None):
            return self.desc
        pil = self.get_pil()
        self.desc = volce_img_caption(pil)
        db_update_image(self.image_id, desc=self.desc)
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
        return {
            "type": "image",
            "image_id": self.image_id,
            "desc": self.get_desc()
        }
    def to_send(self):
        return self.get_pil()
add_type("image", MSEGImage)
