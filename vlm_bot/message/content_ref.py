"""ContentRef — 消息级引用对象，用于插件注入的可去重内容。"""

from __future__ import annotations
from typing import Dict, Optional


class ContentRef:
    """消息级引用对象。

    - `id`: 唯一标识
    - `data`: 可序列化的纯数据 dict
    - 去重：data dict 相同时整条消息被丢弃
    - 持久化：{"type": "content_ref", "id": id, **data}
    """

    def __init__(self, id: str, data: Optional[Dict] = None):
        self.id = id
        self.data: Dict = data if data is not None else {}

    def to_db(self) -> Dict:
        """持久化序列化。"""
        from .db_serialization import serialize_db_dict
        serialized_data = serialize_db_dict(self.data)
        return {"type": "content_ref", "id": self.id, "data": serialized_data}

    @classmethod
    def from_db(cls, data: Dict) -> ContentRef:
        """从持久化数据重建对象。"""
        if data.get("type") != "content_ref":
            raise ValueError(f"Expected type 'content_ref', got '{data.get('type')}'")
        ref_id = data.get("id")
        if ref_id is None:
            raise ValueError("Missing 'id' field")
        ref_data = data.get("data", {})
        # data 中可能递归包含 ImageRef/VideoRef，需要反序列化
        from .db_serialization import deserialize_db_dict
        ref_data = deserialize_db_dict(ref_data)
        return cls(id=ref_id, data=ref_data)

    def is_updated(self, other: ContentRef) -> bool:
        """内容是否有更新：直接比较 data dict。"""
        return self.data != other.data
