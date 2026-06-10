"""Message — 消息模型。"""

from __future__ import annotations
from typing import Union, Optional, List, Dict, Any
from .content_ref import ContentRef
from .image_ref import ImageRef
from .video_ref import VideoRef

# Content 类型定义（不含 ContentRef）
Content = Union[
    List["Content"],
    Dict[str, "Content"],
    str, float, int, None,
    ImageRef,
    VideoRef,
]


class Message:
    """消息。

    role: "system" | "user" | "assistant" | "tool"
    content: Content 或 ContentRef（二选一）
    """

    def __init__(
        self,
        role: str,
        content: Union[Content, ContentRef],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id
        self.name = name

    def to_db(self) -> Dict[str, Any]:
        """持久化序列化。"""
        from .db_serialization import serialize_db_dict

        d: Dict[str, Any] = {"role": self.role}
        if isinstance(self.content, ContentRef):
            d["content"] = self.content.to_db()
        else:
            d["content"] = serialize_db_dict(self.content)
        if self.tool_calls is not None:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        return d

    @classmethod
    def from_db(cls, data: Dict[str, Any]) -> Message:
        """从持久化数据重建。"""
        from .db_serialization import deserialize_db_dict

        content_raw = data["content"]
        # Check if it's a ContentRef
        if isinstance(content_raw, dict) and content_raw.get("type") == "content_ref":
            content = ContentRef.from_db(content_raw)
        else:
            # Deserialize as Content
            content = deserialize_db_dict(content_raw)

        return cls(
            role=data["role"],
            content=content,
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
        )
