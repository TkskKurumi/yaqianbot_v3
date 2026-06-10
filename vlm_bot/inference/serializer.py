"""序列化器 — 将消息列表转换为 OpenAI API 兼容格式。

三阶段流程：
1. ContentRef 消息级去重（data 未变则丢弃整条消息）
2. ImageRef/VideoRef 去重 + JSON 展平
3. OpenAI 格式（合并连续文本段，生成分段内容）
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Union
import json
import base64
from io import BytesIO
from PIL import Image
from ..message.message import Message, Content
from ..message.content_ref import ContentRef
from ..message.image_ref import ImageRef
from ..message.video_ref import VideoRef
import logging
from yaqianbot.globals.g_cfg import get as get_cfg


logger = logging.getLogger(__name__)
level_str = get_cfg("vlm_bot", "logging_level", "serializer", "INFO")
logger.setLevel(getattr(logging, level_str.upper(), logging.INFO))


# ── 阶段 1 — ContentRef 消息级去重 ─────────────────────────

def dedup_contentref(messages: List[Message]) -> List[Message]:
    """ContentRef 消息级去重。

    遍历消息列表，对 content 为 ContentRef 的消息：
    - data 未变 → 整条消息丢弃
    - data 已变 → 将 ContentRef 替换为 data dict（变为普通 Content）
    """
    seen: Dict[str, ContentRef] = {}
    result: List[Message] = []
    num_ref = 0
    num_new = 0
    num_changed = 0
    num_unchanged = 0
    for msg in messages:
        if not isinstance(msg.content, ContentRef):
            result.append(msg)
            continue
        num_ref += 1
        cr = msg.content
        if cr.id in seen:
            # 检查 data 是否更新
            
            if not cr.is_updated(seen[cr.id]):
                # data 未变，丢弃整条消息
                num_unchanged += 1
                logger.debug(f"{cr.id} unchanged")
                continue
            logger.debug(f"{cr.id} changed")
            num_changed += 1
            # data 已更新，替换为完整数据
            seen[cr.id] = cr
            new_msg = Message(
                role=msg.role,
                content=cr.data,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
            result.append(new_msg)
        else:
            # 首次出现，替换为完整数据
            logger.debug(f"{cr.id} new")
            num_new += 1
            seen[cr.id] = cr
            new_msg = Message(
                role=msg.role,
                content=cr.data,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
            result.append(new_msg)
    logger.debug(f"ContentRef num/new/unchange/change {num_ref}/{num_new}/{num_unchanged}/{num_changed}")
    return result


# ── 阶段 2 — JSON 展平 + ImageRef/VideoRef 去重 ───────────

def _json_dumps_scalar(obj: Any) -> str:
    """将标量序列化为 JSON 字符串。"""
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if obj is None:
        return "null"
    raise TypeError(f"Unexpected scalar type: {type(obj)}")


def _flatten_content(
    content: Content,
    buffer: List[Union[str, ImageRef, VideoRef]],
    seen_images: Dict[str, bool],
    seen_videos: Dict[str, bool],
    image_vision_mode: bool,
    video_vision_mode: bool,
) -> None:
    """递归展平 Content 树为文本流 + 媒体对象。"""
    if isinstance(content, str):
        buffer.append(json.dumps(content, ensure_ascii=False))
    elif isinstance(content, bool):
        buffer.append("true" if content else "false")
    elif isinstance(content, (int, float)):
        buffer.append(str(content))
    elif content is None:
        buffer.append("null")
    elif isinstance(content, ImageRef):
        if content.id in seen_images:
            # 去重：保持与首次相同的格式
            buffer.append(json.dumps({"type": "image", "id": content.id}, ensure_ascii=False))
        else:
            seen_images[content.id] = True
            if image_vision_mode:
                # 视觉模式：注入 image_url
                buffer.append('{"type": "image", "id": ' + json.dumps(content.id) + ', "data": ')
                buffer.append(content)
                buffer.append("}")
            else:
                # 文本模式：用描述
                desc = _get_image_desc(content)
                buffer.append(json.dumps({"type": "image", "id": content.id, "desc": desc}, ensure_ascii=False))
    elif isinstance(content, VideoRef):
        if content.id in seen_videos:
            # 去重：保持与首次相同的格式
            buffer.append(json.dumps({"type": "video", "id": content.id}, ensure_ascii=False))
        else:
            seen_videos[content.id] = True
            if video_vision_mode:
                # 视频视觉模式：转为首帧图片注入
                buffer.append('{"type": "video", "id": ' + json.dumps(content.id) + ', "data": ')
                # TODO: 提取首帧作为 ImageRef 注入
                buffer.append(content)
                buffer.append("}")
            else:
                # 文本模式：用描述
                desc = _get_video_desc(content)
                buffer.append(json.dumps({"type": "video", "id": content.id, "desc": desc}, ensure_ascii=False))
    elif isinstance(content, dict):
        buffer.append("{")
        first = True
        for k, v in content.items():
            if not first:
                buffer.append(", ")
            buffer.append(json.dumps(k, ensure_ascii=False))
            buffer.append(": ")
            _flatten_content(v, buffer, seen_images, seen_videos, image_vision_mode, video_vision_mode)
            first = False
        buffer.append("}")
    elif isinstance(content, list):
        buffer.append("[")
        for idx, item in enumerate(content):
            if idx:
                buffer.append(", ")
            _flatten_content(item, buffer, seen_images, seen_videos, image_vision_mode, video_vision_mode)
        buffer.append("]")
    else:
        raise TypeError(f"Unexpected content type: {type(content)}")


def _get_image_desc(img_ref: ImageRef) -> str:
    """获取图片描述（从缓存或调用视觉模型）。"""
    from ..database.image_store import get_image_info
    desc = get_image_info(img_ref.id, "desc", None)
    if desc is not None:
        return desc
    # TODO: 调用视觉模型生成描述，缓存到 DB
    return f"[图片 {img_ref.id}]"


def _get_video_desc(vid_ref: VideoRef) -> str:
    """获取视频描述（从缓存或调用视觉模型）。"""
    from ..database.video_store import get_video_info
    desc = get_video_info(vid_ref.id, "desc", None)
    if desc is not None:
        return desc
    # TODO: 调用视觉模型生成描述，缓存到 DB
    return f"[视频 {vid_ref.id}]"


def _image_to_base64(img_ref: ImageRef, max_bytes: int = 500_000) -> str:
    """将 ImageRef 转为 base64 data URL。

    Args:
        img_ref: 图片引用
        max_bytes: 最大允许字节数，超过则自动缩放
    """
    from math import sqrt

    pil = img_ref.get_pil()

    # P 模式（调色板）无法保存为 JPEG，先转换
    if pil.mode == "P":
        pil = pil.convert("RGBA")

    # 有 Alpha 通道用 PNG，否则用 JPEG
    if "A" in pil.mode:
        fmt = "PNG"
        mime = "image/png"
        kwa = {}
    else:
        fmt = "JPEG"
        mime = "image/jpeg"
        kwa = {"quality": 85}

    w, h = pil.size

    def to_bytes(ratio: float):
        w1, h1 = round(ratio * w), round(ratio * h)
        bio = BytesIO()
        pil.resize((w1, h1), resample=Image.Resampling.LANCZOS).save(
            bio, format=fmt, **kwa
        )
        bio.seek(0)
        return bio

    # 尝试缩放直到满足大小限制
    ratio = 1.0
    for _ in range(10):
        bio = to_bytes(ratio)
        bio.seek(0)
        data = bio.read()
        if len(data) <= max_bytes:
            bio.seek(0)
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
        # 缩小比例
        ratio = min(ratio * 0.9, ratio * sqrt(max_bytes / len(data)))

    # 最终尝试（可能仍然超限，但已经缩到很小了）
    bio = to_bytes(ratio)
    bio.seek(0)
    b64 = base64.b64encode(bio.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ── 阶段 3 — OpenAI 格式 ─────────────────────────────────

def _merge_segments(
    segments: List[Union[str, ImageRef, VideoRef]],
    omit_data: bool = False,
) -> List[Dict[str, Any]]:
    """合并连续文本段，生成 OpenAI 分段内容。

    Args:
        segments: 展平后的片段列表
        omit_data: True 时省略 image base64 data（用于 debug 输出）
    """
    result: List[Dict[str, Any]] = []
    curr_text_parts: List[str] = []

    for seg in segments:
        if isinstance(seg, str):
            curr_text_parts.append(seg)
        elif isinstance(seg, ImageRef):
            if curr_text_parts:
                result.append({"type": "text", "text": "".join(curr_text_parts)})
                curr_text_parts = []
            if omit_data:
                result.append({"type": "image_url", "image_url": {"url": "..."}})
            else:
                b64_url = _image_to_base64(seg)
                result.append({"type": "image_url", "image_url": {"url": b64_url}})
        elif isinstance(seg, VideoRef):
            # VideoRef 已经在展平时转为文本描述，不会到这里
            pass

    if curr_text_parts:
        result.append({"type": "text", "text": "".join(curr_text_parts)})

    return result


# ── 主 API ───────────────────────────────────────────────

def serialize_messages(
    messages: List[Message],
    image_vision_mode: bool = True,
    video_vision_mode: bool = False,
    omit_data: bool = False,
) -> List[Dict[str, Any]]:
    """将消息列表序列化为 OpenAI 兼容格式。

    Args:
        messages: 消息列表
        image_vision_mode: True=图片视觉模式（注入 image_url），False=文本模式（用 desc）
        video_vision_mode: True=视频视觉模式（注入首帧），False=文本模式（用 desc）
        omit_data: True 时省略 image base64 data（用于 debug 输出）

    Returns:
        OpenAI 格式的消息列表
    """
    # 阶段 1: ContentRef 去重
    messages = dedup_contentref(messages)

    # 阶段 2 + 3: 展平 + OpenAI 格式
    result: List[Dict[str, Any]] = []
    seen_images: Dict[str, bool] = {}
    seen_videos: Dict[str, bool] = {}

    for msg in messages:
        if msg.role == "system":
            # system 消息直接处理
            if isinstance(msg.content, str):
                result.append({"role": "system", "content": msg.content})
            else:
                # system 消息也可能是 Content，展平处理
                buffer: List[Union[str, ImageRef, VideoRef]] = []
                _flatten_content(msg.content, buffer, {}, {}, image_vision_mode, video_vision_mode)
                segments = _merge_segments(buffer, omit_data=omit_data)
                result.append({"role": "system", "content": segments})
            continue

        # user/assistant/tool 消息
        # 纯字符串 content 直接作为文本（如 tool 消息）
        # 否则走 Content 树展平逻辑（JSON 编码）
        if isinstance(msg.content, str):
            segments = msg.content
        else:
            buffer: List[Union[str, ImageRef, VideoRef]] = []
            _flatten_content(msg.content, buffer, seen_images, seen_videos, image_vision_mode, video_vision_mode)
            segments = _merge_segments(buffer, omit_data=omit_data)

        msg_dict: Dict[str, Any] = {"role": msg.role, "content": segments}
        if msg.tool_calls is not None:
            msg_dict["tool_calls"] = msg.tool_calls
        if msg.tool_call_id is not None:
            msg_dict["tool_call_id"] = msg.tool_call_id
        if msg.name is not None:
            msg_dict["name"] = msg.name

        result.append(msg_dict)

    return result
