"""TimestampPlugin — 时间戳注入插件。

当距上次发送时间戳超过指定间隔（默认60秒）时，
在 get_message 中注入一条时间戳 Content。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, List

from ..base import BasePlugin, register_plugin
from ...message.message import Content


@register_plugin
class TimestampPlugin(BasePlugin):
    """时间戳注入插件。

    按 session 跟踪上次注入时间戳的时间。
    超过间隔后注入 {"type": "timedate", "timedate": "..."}。
    """

    type = "timestamp"

    def __init__(self, interval: float = 60.0):
        """
        Args:
            interval: 注入间隔（秒），默认 60 秒。
        """
        self.interval = interval
        # {group_id: last_inject_time}
        self._last_inject: Dict[str, float] = {}

    def get_system_message(self, session) -> str:
        return ""

    def get_message(self, session) -> List[Content]:
        now = time.time()
        group_id = session.group_id
        last = self._last_inject.get(group_id, 0.0)

        if now - last < self.interval:
            return []

        # 注入时间戳
        self._last_inject[group_id] = now
        timedate_str = datetime.now().strftime("%Y-%m-%d %A %H-%M-%S")
        return [{"type": "timedate", "timedate": timedate_str}]

    def add_tools(self, session, tool_ls, tool_handler_map):
        return tool_ls, tool_handler_map
