"""System Prompt — 静态系统提示词构建。

系统提示词是静态的，构建一次后重复使用（KV-cache 友好）。

组成：
1. 通用系统提示词（从配置文件指定文件或内置字符串）
2. 插件系统提示词（各插件提供）
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def build_system_prompt(
    common_prompt: str,
    plugin_prompts: Optional[List[str]] = None,
) -> str:
    """
    构建完整系统提示词。

    Args:
        common_prompt: 通用系统提示词（从文件或内置字符串加载）
        plugin_prompts: 各插件提供的系统提示词列表

    Returns:
        完整系统提示词字符串
    """
    parts: List[str] = [common_prompt]

    if plugin_prompts:
        # 过滤空字符串
        active_prompts = [p for p in plugin_prompts if p.strip()]
        if active_prompts:
            parts.append("以下为插件说明：")
            parts.extend(active_prompts)

    return "\n\n".join(parts)


def resolve_prompt_source(raw: str) -> str:
    """
    解析系统提示词来源。

    支持两种格式：
    - "source:txt:文件路径" → 读取文件内容
    - 其他 → 直接作为内联提示词返回

    Args:
        raw: 原始提示词字符串

    Returns:
        解析后的提示词内容
    """
    if raw.startswith("source:txt:"):
        file_path = raw[len("source:txt:"):]
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return raw.strip() if raw else ""
