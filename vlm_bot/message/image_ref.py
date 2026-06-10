"""ImageRef — 图片引用对象。"""

from __future__ import annotations
from typing import Optional
from PIL import Image
import hashlib


class ImageRef:
    """图片引用。

    - `id`: SHA256 哈希（默认从 pil 计算）
    - `pil`: PIL Image 对象（惰性加载，需要时从 DB 读取）
    """

    def __init__(self, id: str, pil: Optional[Image.Image] = None):
        self.id = id
        self._pil: Optional[Image.Image] = pil

    @classmethod
    def from_pil(cls, pil: Image.Image) -> ImageRef:
        """从 PIL Image 创建，自动计算 id。"""
        from io import BytesIO
        bio = BytesIO()
        pil.save(bio, format="PNG")
        bio.seek(0)
        img_id = hashlib.sha256(bio.read()).hexdigest()[:16]
        return cls(id=img_id, pil=pil)

    def get_pil(self) -> Image.Image:
        """获取 PIL Image，惰性加载。"""
        if self._pil is not None:
            return self._pil
        # 从数据库加载
        from ..database.image_store import get_image_pil
        self._pil = get_image_pil(self.id)
        if self._pil is None:
            raise FileNotFoundError(f"Image data not found for id={self.id}")
        return self._pil

    def to_db(self) -> dict:
        return {"type": "image", "id": self.id}

    @classmethod
    def from_db(cls, data: dict) -> ImageRef:
        if data.get("type") != "image":
            raise ValueError(f"Expected type 'image', got '{data.get('type')}'")
        return cls(id=data["id"])
    def __eq__(self, other):
        if (isinstance(other, ImageRef)):
            return self.id == other.id
        return self.id == other.id