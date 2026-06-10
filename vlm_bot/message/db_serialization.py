"""持久化序列化/反序列化 — 递归处理 Content 树中的 ImageRef/VideoRef。"""

from __future__ import annotations
from typing import Union, List, Dict, Any

from .image_ref import ImageRef
from .video_ref import VideoRef

Content = Union[
    List["Content"],
    Dict[str, "Content"],
    str, float, int, None,
    ImageRef,
    VideoRef,
]


def serialize_db_dict(obj: Content) -> Any:
    """递归序列化 Content 树为纯 JSON 可持久化数据。

    - ImageRef → {"type": "image", "id": "..."}
    - VideoRef → {"type": "video", "id": "..."}
    - dict → 递归序列化每个值
    - list → 递归序列化每个元素
    - 标量 → 直接返回
    """
    if isinstance(obj, ImageRef):
        return obj.to_db()
    if isinstance(obj, VideoRef):
        return obj.to_db()
    if isinstance(obj, dict):
        return {k: serialize_db_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_db_dict(i) for i in obj]
    return obj


def deserialize_db_dict(obj: Any) -> Content:
    """递归反序列化 DB dict 为 Content 树。

    - {"type": "image", "id": "..."} → ImageRef
    - {"type": "video", "id": "..."} → VideoRef
    - dict → 递归反序列化每个值
    - list → 递归反序列化每个元素
    - 标量 → 直接返回
    """
    if isinstance(obj, dict):
        ctype = obj.get("type")
        if ctype == "image" and "id" in obj:
            return ImageRef.from_db(obj)
        if ctype == "video" and "id" in obj:
            return VideoRef.from_db(obj)
        # Plain dict
        return {k: deserialize_db_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deserialize_db_dict(i) for i in obj]
    return obj
