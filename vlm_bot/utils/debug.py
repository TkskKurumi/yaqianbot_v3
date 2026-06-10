"""Debug 工具函数。"""

from __future__ import annotations

import json
import logging
from typing import List

from ..message.message import Message
from ..inference.serializer import serialize_messages


def debug_vlm_response(response, provider_name: str, messages: List[Message], elapsed: float, logger: logging.Logger) -> None:
    """输出 VLM 响应的 debug 日志。从 response 对象提取信息。"""
    choice = response.choices[0]
    content = choice.message.content or "(empty)"
    tool_calls = getattr(choice.message, "tool_calls", None)
    reasoning_content = getattr(choice.message, "reasoning_content", None)
    usage = response.usage
    msg_count = len(messages)
    msg_count_role = {}
    for i in messages:
        msg_count_role[i.role] = msg_count_role.get(i.role, 0) + 1
    debug_lines = [
        f"{provider_name} response:",
        f"  content message length: {msg_count} {msg_count_role}",
        f"  elapsed: {elapsed:.2f}s",
        f"  content: {content[:200]}",
    ]

    if tool_calls:
        debug_lines.append(f"  tool_calls: {tool_calls}")
        n = len(tool_calls)
        debug_lines.append(f"  num tool_calls: {n}")
    if usage:
        debug_lines.append(
            f"  tokens prompt/completion/total: "
            f"{usage.prompt_tokens}/{usage.completion_tokens}/{usage.total_tokens}"
        )
    debug_lines.append(f"  finish_reason: {choice.finish_reason}")
    if reasoning_content is not None:
        debug_lines.append(f"  reasoning: {reasoning_content}")
    logger.debug("\n".join(debug_lines))


def debug_dump_chat_history(
    group_id: str,
    messages: List[Message],
    image_vision_mode: bool = True,
    video_vision_mode: bool = False,
    logger: logging.Logger = None,
) -> None:
    """将消息历史序列化（省略 image base64 data）并写入 debug 文件。"""
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        from yaqianbot.globals.g_paths import get_file_path

        debug_path = get_file_path(
            "vlm_bot", "debug", str(group_id), "chat_history.json"
        )

        debug_messages = serialize_messages(
            messages,
            image_vision_mode=image_vision_mode,
            video_vision_mode=video_vision_mode,
            omit_data=True,
        )
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_messages, f, ensure_ascii=False, indent=2)
        logger.debug(f"Debug dump written to {debug_path}")
    except Exception as e:
        logger.warning(f"Failed to write debug dump: {e}")
