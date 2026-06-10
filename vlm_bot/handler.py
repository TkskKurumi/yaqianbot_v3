"""Handler — 消息入口处理器。

负责：
- 消息接收（yaqianbot 装饰器，模块导入时自动注册）
- 触发判断
- 消息转换（yaqianbot → vlm_bot）
- 会话管理
- 回复发送

模块导入时通过 get_cfg 读取配置并初始化所有组件。
"""

from __future__ import annotations

import io
import logging
import time
from typing import List, Tuple

from yaqianbot.receiver import on_message, on_exception_send_sync, command, is_su
from yaqianbot.globals.g_threading import threading_run
from yaqianbot.globals.g_cfg import get as get_cfg
from yaqianbot.adapters.base_adapter.message import BaseMessage as YBaseMessage
from yaqianbot.adapters.base_adapter.message import BaseSendVideoFile as YBaseVideo
from yaqianbot.adapters.base_adapter.mseg import BaseImage, BaseText, MessageSegment

from .message.message import Message
from .message.content_ref import ContentRef
from .message.image_ref import ImageRef
from .message.video_ref import VideoRef
from .session.manager import open_session as get_session, init_manager, get_manager
from .inference.client import VLMClient
from .inference.router import ProviderRouter
from .inference.serializer import serialize_messages
from .inference.system_prompt import resolve_prompt_source
from .trigger.scheduler import TriggerScheduler
from .plugins.loader import load_plugins
from .database.image_store import save_image_from_pil

# 导入内置插件（触发 @register_plugin 装饰器）
from .plugins import builtins  # noqa: F401

logger = logging.getLogger(__name__)


def _setup_logger():
    """根据配置设置 logger level。"""
    level_str = get_cfg("vlm_bot", "logging_level", "handler", "INFO")
    logger.setLevel(getattr(logging, level_str.upper(), logging.INFO))


_setup_logger()


# ============================================================
# 模块导入时初始化
# ============================================================

def _init():
    """模块导入时自动初始化所有组件。"""
    # 1. 触发配置
    trigger_cfg = get_cfg("vlm_bot", "trigger", {})
    global _trigger_scheduler
    _trigger_scheduler = TriggerScheduler(trigger_cfg)

    # 2. Provider 路由
    providers_cfg = get_cfg("vlm_bot", "providers", [])
    clients: List[VLMClient] = []
    for p in providers_cfg:
        client = VLMClient(
            name=p.get("name", "unknown"),
            base_url=p["base_url"],
            api_key=p["api_key"],
            model=p.get("model", "default"),
            priority=p.get("priority", 0),
            weight=p.get("weight", 1.0),
            max_tokens=p.get("max_tokens", get_cfg("vlm_bot", "max_tokens", 4096)),
            temperature=p.get("temperature", get_cfg("vlm_bot", "temperature", 0.95)),
            top_p=p.get("top_p", get_cfg("vlm_bot", "top_p", 0.95)),
            timeout=p.get("timeout", 120.0),
        )
        clients.append(client)
    router = ProviderRouter(clients) if clients else None

    # 3. 系统提示词（支持 "source:txt:文件路径" 格式）
    raw_prompt = get_cfg("vlm_bot", "system_prompt", "")
    common_prompt = resolve_prompt_source(raw_prompt)

    # 3.5 加载插件
    plugin_configs = get_cfg("vlm_bot", "plugins", [])
    plugins = load_plugins(plugin_configs) if plugin_configs else []

    # 4. 初始化 SessionManager 全局配置
    init_manager(
        router=router,
        common_prompt=common_prompt,
        plugins=plugins,
        image_vision_mode=get_cfg("vlm_bot", "image_vision_mode", True),
        video_vision_mode=get_cfg("vlm_bot", "video_vision_mode", False),
        max_tool_calls=get_cfg("vlm_bot", "max_tool_calls", 5),
        debug_dump=get_cfg("vlm_bot", "debug_dump", False),
        context_trim_hit=get_cfg("vlm_bot", "context_trim", "hit", None),
        context_trim_trim_to=get_cfg("vlm_bot", "context_trim", "trim_to", None),
    )

    logger.info("vlm_bot initialized")


# 全局触发调度器
_trigger_scheduler: TriggerScheduler
_init()


def _vlm_message_to_segments(vlm_msg: Message) -> List[MessageSegment]:
    """
    将 vlm_bot Message 转换为 yaqianbot MessageSegment 列表。

    Content 格式必须为 str 或 List[str, ImageRef, VideoRef]。

    Args:
        vlm_msg: vlm_bot Message

    Returns:
        yaqianbot MessageSegment 列表

    Raises:
        ValueError: 当 content 类型不支持时
    """

    content = vlm_msg.content

    # 如果 content 是字符串，直接作为文本
    if isinstance(content, str):
        return [content]

    # 如果 content 是列表（List[str, ImageRef, VideoRef]）
    if isinstance(content, list):
        segments: List[MessageSegment] = []
        for item in content:
            if isinstance(item, str):
                segments.append(item)
            elif isinstance(item, ImageRef):
                segments.append(item.get_pil())
            elif isinstance(item, VideoRef):
                logger.warning("sending video is currently not supported")
            else:
                raise ValueError(
                    f"Unsupported content item type in VLM response: {type(item)}"
                )
        return segments

    # 其他类型不支持
    raise ValueError(
        f"Unsupported content type for sending: {type(content)}. "
        f"Expected str or List[str, ImageRef, VideoRef]."
    )


def _default_send_resp_cb(vlm_msg: Message, ymes: YBaseMessage):
    """
    默认回复发送回调。

    将 vlm_bot Message 转换为 yaqianbot segments 并通过 ymes.sync_send() 发送。

    Args:
        vlm_msg: vlm_bot Message
        ymes: yaqianbot BaseMessage（用于调用 sync_send）
    """
    try:
        segments = _vlm_message_to_segments(vlm_msg)
        if not segments:
            logger.warning("VLM response has empty content, skipping send")
            return
        if (len(segments) <= 5):
            for i in segments:
                ymes.sync_send([i])
        else:
            ymes.sync_send(segments)
    except ValueError as e:
        logger.error(f"Content type error when sending response: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Failed to send response: {e}", exc_info=True)


def _ymes_to_vlm_message(ymes: YBaseMessage) -> Tuple[Message, Message]:
    """
    将 yaqianbot 消息转换为 vlm_bot Message 对。

    返回两条消息：
    1. 用户信息 ContentRef 消息 — 包含 username/gender/role 等身份信息，
       同一用户多次发言时由 dedup_contentref 去重。
    2. 用户内容消息 — 包含 qq_id 引用和实际发言内容，
       qq_id 让 VLM 在 ContentRef 被去重后仍能识别发言者。

    Args:
        ymes: yaqianbot BaseMessage

    Returns:
        (user_info_msg, user_content_msg) 元组
    """
    from datetime import datetime

    content_items = []

    for segment in ymes.rich:
        if isinstance(segment, BaseText):
            content_items.append(segment.repr_text)
        elif isinstance(segment, BaseImage):
            # 将图片存入数据库，获取 ImageRef

            pil_img = segment.get_pil()
            image_id, _ = save_image_from_pil(pil_img)
            content_items.append(ImageRef(image_id))
        elif isinstance(segment, YBaseVideo):
            # 视频暂不处理，转为文本占位
            try:
                segment.get_saved_file()
                content_items.append("[视频]")
            except Exception:
                content_items.append("[视频文件获取失败]")
        else:
            # 其他类型转为文本
            content_items.append(getattr(segment, "repr_text", repr(segment)))

    # 构建用户身份 ID
    uid = ymes.sender.uid
    user_ref_id = f"qq_user_{uid}"

    # 构建 sender metadata（进入 ContentRef，可去重）
    try:
        role = ymes.sender.group_privilege
    except Exception:
        role = "UNKNOWN"

    user_info_data = {
        "username": ymes.sender.username,
        "gender": getattr(ymes.sender, "gender_str", "unknown"),
        "role": role,
        "qqid": user_ref_id
    }
    try:
        avatar = ymes.sender.get_avatar()
    except Exception as e:
        logger.warning(f"get user {user_ref_id} avatar fail {e}")
        avatar = None
    if (avatar):
        avatar_id, data = save_image_from_pil(avatar)
        user_info_data["avatar"] = ImageRef(avatar_id)

    # 消息 1：用户信息 ContentRef（同一用户多次发言时去重）
    user_info_msg = Message(
        role="user",
        content=ContentRef(id=user_ref_id, data=user_info_data),
    )

    # 消息 2：用户内容（带 qq_id 引用，即使 ContentRef 被去重也能识别发言者）
    user_content = {
        "qq_id": user_ref_id,
        # "date": datetime.now().strftime("%Y-%m-%d %A %H-%M-%S"),
        "content": content_items if content_items else [],
    }

    user_content_msg = Message(
        role="user",
        content=user_content,
    )

    return user_info_msg, user_content_msg


def _on_every_message(ymes: YBaseMessage):
    """处理每条收到的消息。

    消息始终添加到会话历史（用于批处理：多条用户消息 trigger 后统一回复）。
    只有 trigger 触发时才调用 respond。
    """
    try:
        if not ymes.rich:
            return

        gid = ymes.sender.group_id

        # 获取会话
        session = get_session(gid)

        # 转换并添加用户消息（ContentRef + 内容消息对）— 始终添加
        user_info_msg, user_content_msg = _ymes_to_vlm_message(ymes)

        with session.LOCK:
            
            session.add_message(user_info_msg)
            session.add_message(user_content_msg)
            last_mes = user_content_msg
            for plugin in session.plugins:
                try:
                    plugin_msgs = plugin.get_message(session)
                    for content in plugin_msgs:
                        plugin_msg = Message(
                            role="user",
                            content=content,
                            name=plugin.type,
                        )
                        last_mes = plugin_msg
                        session.add_message(plugin_msg)
                except Exception as e:
                    logger.error(f"Plugin {plugin.type} get_message failed: {e}", exc_info=True)
        # Debug: 序列化单条消息用于调试
        try:
            for msg in (user_info_msg, user_content_msg):
                api_msg = serialize_messages([msg], omit_data=True)
                import json
                debug_str = json.dumps(api_msg, ensure_ascii=False)[:1024]
                logger.debug(f"Received message gid={gid}: {debug_str}")
        except Exception:
            pass

        # 触发检查 — 只有触发时才 respond
        message_text = "".join(
            s.repr_text for s in ymes.rich if hasattr(s, "repr_text")
        )
        trigger = _trigger_scheduler.check_trigger(
            gid, message_text, ymes.is_to_me
        )

        if not trigger.triggered:
            return

        # 等待批处理时间
        time.sleep(trigger.wait_sec)
        _trigger_scheduler.record_trigger(gid)

        # 裁剪消息历史
        session.trim_length_auto(
            max_count=get_cfg("vlm_bot", "mes_cnt_max", 30000),
            preferred_count=get_cfg("vlm_bot", "mes_cnt_pref", 10000),
        )

        # VLM 推理 + 回复发送
        with session.LOCK:
            if (session.messages[-1].role == "user"):
                session.respond(send_resp_cb=lambda msg: _default_send_resp_cb(msg, ymes))
                _trigger_scheduler.record_trigger(gid)
            else:
                logger.warning(f"message sequence disorder, maybe respond is run between trigger wait")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


# ============================================================
# yaqianbot 消息接收器注册（模块导入时自动注册）
# ============================================================

@on_message
@threading_run
@on_exception_send_sync
def cb_on_every_message(mes: YBaseMessage):
    """消息接收器。模块导入时自动注册到 yaqianbot 框架。"""
    _on_every_message(mes)


@on_message
@is_su
@threading_run
@on_exception_send_sync
@command("#session_clear", kw_options={"-n"}, bool_options={"-a", "-o"})
def cb_session_clear(mes: YBaseMessage, *args, **kwargs):
    """清空会话消息历史。super user only.
    
    用法:
        #session_clear [群ID] [-n 保留数] [-a 清除assistant] [-o 所有会话]
    """
    mes_buffer = []
    
    def trim_by_num(gid, session, n):
        nonlocal mes_buffer
        le0 = len(session.messages)
        session.trim_length(num=n)
        le1 = len(session.messages)
        if le0 != le1:
            mes_buffer.append(f"{gid} 消息 {le0} -> {le1}")
    
    def trim_assistant(gid, session):
        nonlocal mes_buffer
        le0 = len(session.messages)
        # 只保留 user 消息
        session.messages = [m for m in session.messages if m.role == "user"]
        le1 = len(session.messages)
        if le0 != le1:
            mes_buffer.append(f"{gid} 清除 assistant 消息 {le0} -> {le1}")
    
    manager = get_manager()
    gids = set(args) if args else set()
    
    if kwargs.get("-o", False):
        # 操作所有已打开的会话
        gids.update(manager.get_all().keys())
    
    if not gids:
        # 默认操作当前群
        gids.add(mes.sender.group_id)
    
    for gid in gids:
        try:
            session = manager.open(gid)
            with session.LOCK:
                n = int(kwargs.get("-n", 0))
                if n > 0:
                    trim_by_num(gid, session, n)
                if kwargs.get("-a", False):
                    trim_assistant(gid, session)
                if n == 0 and not kwargs.get("-a", False):
                    # 完全清空
                    le0 = len(session.messages)
                    session.messages = []
                    mes_buffer.append(f"{gid} 清空所有消息 ({le0} -> 0)")
                session.save_to_db()
        except Exception as e:
            mes_buffer.append(f"{gid} 处理失败: {e}")
    
    if mes_buffer:
        to_send = "\n".join(mes_buffer)
        if len(to_send) > 256:
            to_send = to_send[:252] + "..."
        mes.sync_send(to_send)
