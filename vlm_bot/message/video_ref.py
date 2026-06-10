"""VideoRef — 视频引用对象。"""

from __future__ import annotations
from typing import Optional
import hashlib


class VideoRef:
    """视频引用。

    - `id`: SHA256 哈希（默认从 bytes 计算）
    - `data`: 原始视频 bytes（可选，可从 DB 加载）
    """

    def __init__(self, id: str, data: Optional[bytes] = None):
        self.id = id
        self._data: Optional[bytes] = data

    @classmethod
    def from_bytes(cls, data: bytes) -> VideoRef:
        """从 bytes 创建，自动计算 id。"""
        vid_id = hashlib.sha256(data).hexdigest()[:16]
        return cls(id=vid_id, data=data)

    def get_data(self) -> bytes:
        """获取视频 bytes，惰性加载。"""
        if self._data is not None:
            return self._data
        # 从数据库加载
        from ..database.video_store import get_video_data
        self._data = get_video_data(self.id)
        if self._data is None:
            raise FileNotFoundError(f"Video data not found for id={self.id}")
        return self._data

    def to_db(self) -> dict:
        return {"type": "video", "id": self.id}

    @classmethod
    def from_db(cls, data: dict) -> VideoRef:
        if data.get("type") != "video":
            raise ValueError(f"Expected type 'video', got '{data.get('type')}'")
        return cls(id=data["id"])
    def __eq__(self, other):
        if (isinstance(other, VideoRef)):
            return self.id == other.id
        return False
