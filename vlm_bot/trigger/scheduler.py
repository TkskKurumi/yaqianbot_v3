"""Trigger Scheduler — 触发调度器。

三种触发方式：
1. @提及（is_to_me）
2. 关键词匹配（带概率）
3. 时间概率（随时间增长概率增加）
"""

from __future__ import annotations

import logging
import random
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class TriggerResult:
    """触发结果。"""

    def __init__(self, triggered: bool, trigger_type: str, wait_sec: float):
        self.triggered = triggered
        self.trigger_type = trigger_type  # "at_mention" | "keyword" | "time" | ""
        self.wait_sec = wait_sec


class TriggerScheduler:
    """触发调度器。

    记录每个群的最后触发时间，用于时间概率计算和批处理等待。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 触发配置字典，键同计划中的 trigger 配置
        """
        self.config = config
        # group_id -> last trigger time
        self._last_trigger_time: Dict[str, float] = {}

    def _get_last_trigger_time(self, group_id: str) -> float:
        return self._last_trigger_time.setdefault(group_id, time.time())

    def _set_last_trigger_time(self, group_id: str, t: float):
        self._last_trigger_time[group_id] = t
        return t

    def check_trigger(
        self,
        group_id: str,
        message_text: str,
        is_to_me: bool = False,
    ) -> TriggerResult:
        """
        检查消息是否触发回复。

        优先级：@提及 > 关键词 > 时间概率

        Args:
            group_id: 群 ID
            message_text: 消息文本内容
            is_to_me: 是否 @了机器人

        Returns:
            TriggerResult 对象
        """
        now = time.time()

        # 1. @提及触发
        if is_to_me and self.config.get("at_mention", True):
            logger.info(f"Group {group_id}: triggered by @mention")
            return TriggerResult(True, "at_mention", self.config.get("wait_ated_sec", 5.0))

        # 2. 关键词触发
        keywords = self.config.get("keywords", [])
        if keywords:
            for keyword in keywords:
                if keyword in message_text:
                    if random.random() < self.config.get("keyword_prob", 1.0):
                        logger.info(f"Group {group_id}: triggered by keyword '{keyword}'")
                        return TriggerResult(True, "keyword", self.config.get("wait_ated_sec", 5.0))
                    else:
                        logger.debug(
                            f"Group {group_id}: keyword '{keyword}' matched "
                            f"but probability check failed ({self.config.keyword_prob})"
                        )
                    break  # 只检查第一个匹配的关键词

        # 3. 时间概率触发
        last_t = self._get_last_trigger_time(group_id)
        elapsed = now - last_t

        time_min = self.config.get("time_min_sec", 300.0)
        time_max = self.config.get("time_max_sec", 1800.0)
        if elapsed >= time_min:
            ratio = min((elapsed - time_min) / (time_max - time_min), 1.0)
            prob = self.config.get("time_prob_min", 0.1) + ratio * (
                self.config.get("time_prob_max", 1.0) - self.config.get("time_prob_min", 0.1)
            )

            if random.random() < prob:
                logger.info(
                    f"Group {group_id}: triggered by time "
                    f"(elapsed={elapsed:.0f}s, prob={prob:.2f})"
                )
                return TriggerResult(True, "time", self.config.get("wait_batch_sec", 5.0))

        return TriggerResult(False, "", 0.0)

    def record_trigger(self, group_id: str):
        """记录触发时间。"""
        return self._set_last_trigger_time(group_id, time.time())

    def get_wait_time(self, group_id: str, trigger_type: str) -> float:
        """
        获取等待时间（用于批处理）。

        Args:
            group_id: 群 ID
            trigger_type: 触发类型

        Returns:
            等待秒数
        """
        if trigger_type == "time":
            return self.config.get("wait_batch_sec", 5.0)
        return self.config.get("wait_ated_sec", 5.0)
