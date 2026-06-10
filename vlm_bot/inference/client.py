"""VLM Client — OpenAI Compatible API 封装。"""

from __future__ import annotations

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
import re

from openai import OpenAI
from yaqianbot.globals.g_cfg import get as get_cfg

from .serializer import serialize_messages
from ..message.message import Message

import traceback

logger = logging.getLogger(__name__)

from ..utils.debug import debug_vlm_response


def _setup_logger():
    """根据配置设置 logger level。"""
    level_str = get_cfg("vlm_bot", "logging_level", "vlm_client", "INFO")
    print("client logg level", level_str)
    logger.setLevel(getattr(logging, level_str.upper(), logging.INFO))


_setup_logger()


def _trim_messages(msgs: List[Message], ratio: float) -> List[Message]:
    """按 ratio 裁剪消息列表，保留尾部。在 user 消息处裁剪。"""
    new_len = max(1, int(len(msgs) * ratio))
    start = len(msgs) - new_len
    while start < len(msgs):
        if msgs[start].role == "user":
            break
        start += 1
    return msgs[start:]


def _parse_n_prompt_tokens(error_message) -> Optional[int]:
    """从错误消息中解析 n_prompt_tokens。"""
    msg_str = str(error_message)
    m = re.search(r'"n_prompt_tokens"\s*:\s*(\d+)', msg_str)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*tokens?\s+exceeds', msg_str, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _compute_trim_ratio(error_message) -> float:
    """计算裁剪比例。优先使用 trim_to / n_prompt_tokens，否则 0.5。"""
    trim_to = get_cfg("vlm_bot", "context_trim", "trim_to", None)
    n_tokens = _parse_n_prompt_tokens(error_message)
    if trim_to and n_tokens and n_tokens > 0:
        return trim_to / n_tokens
    return 0.5


class VLMClient:
    """单个 VLM provider 客户端。"""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        priority: int = 0,
        weight: float = 1.0,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 1.0,
        timeout: float = 120.0,
    ):
        self.name = name
        self.model = model
        self.priority = priority
        self.weight = max(weight, 0.001)  # 防止除零
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        # 负载均衡计数
        self._request_count = 0
        self._cost = 0.0  # 加权 cost = sum(1/weight)
        self._last_request_time = 0.0

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def last_request_time(self) -> float:
        return self._last_request_time

    def chat(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        image_vision_mode: bool = True,
        video_vision_mode: bool = False,
        max_context_trim: int = 3,
        **kwargs,
    ) -> Tuple[Any, List[Message]]:
        """
        调用 VLM 进行对话。超出上下文时自动裁剪重试。

        Returns:
            (API 响应对象, 消息列表) 元组。消息列表可能是裁剪后的。
        """
        from openai import BadRequestError

        msg_list = list(messages)

        def _do_request(msgs):
            try:
                if (system_prompt):
                    msgs = [Message(role="system", content=system_prompt)] + msgs
                api_messages = serialize_messages(
                    msgs,
                    image_vision_mode=image_vision_mode,
                    video_vision_mode=video_vision_mode,
                )
            except Exception as e:
                traceback.print_exc()
                raise e

            request_kwargs = {
                "model": self.model,
                "messages": api_messages,
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
                "top_p": kwargs.get("top_p", self.top_p),
            }

            if "tools" in kwargs:
                request_kwargs["tools"] = kwargs["tools"]
            if "tool_choice" in kwargs:
                request_kwargs["tool_choice"] = kwargs["tool_choice"]

            self._request_count += 1
            self._cost += 1.0 / self.weight

            t0 = time.time()
            logger.info(
                f"Calling {self.name} ({self.model}), request #{self._request_count}"
            )

            response = self._client.chat.completions.create(**request_kwargs)
            elapsed = time.time() - t0
            self._last_request_time = time.time()

            debug_vlm_response(response, self.name, msgs, elapsed, logger)
            return response

        trim_count = 0
        current_msgs = msg_list

        while True:
            try:
                response = _do_request(current_msgs)
                return response, current_msgs
            except BadRequestError as e:
                if e.code == 400 and hasattr(e, 'message') and 'exceed_context_size_error' in str(e.message):
                    if trim_count >= max_context_trim:
                        logger.error(f"Context trim exceeded max retries ({max_context_trim}) for {self.name}")
                        raise
                    trim_count += 1
                    ratio = _compute_trim_ratio(e.message)
                    current_msgs = _trim_messages(current_msgs, ratio)
                    logger.warning(
                        f"Context exceeded for {self.name}, trimming "
                        f"{len(msg_list)} -> {len(current_msgs)} (ratio={ratio:.2f}, trim #{trim_count})"
                    )
                    continue
                logger.error(f"Request to {self.name} failed: {e}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Request to {self.name} failed: {e}", exc_info=True)
                raise

    def chat_stream(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        image_vision_mode: bool = True,
        video_vision_mode: bool = False,
        **kwargs,
    ):
        """
        流式调用 VLM 进行对话。

        Args:
            messages: 消息列表
            system_prompt: 系统提示词
            image_vision_mode: 图片是否使用原生视觉模式
            video_vision_mode: 视频是否使用原生视觉模式
            **kwargs: 额外参数传递给 API

        Yields:
            流式响应块
        """
        # 构建消息列表
        msg_list = list(messages)
        if system_prompt:
            system_msg = Message(role="system", content=system_prompt)
            msg_list.insert(0, system_msg)

        # 序列化
        api_messages = serialize_messages(
            msg_list,
            image_vision_mode=image_vision_mode,
            video_vision_mode=video_vision_mode,
        )

        # 构建请求参数
        request_kwargs = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "stream": True,
        }

        # 添加 tools（如果提供）
        if "tools" in kwargs:
            request_kwargs["tools"] = kwargs["tools"]
        if "tool_choice" in kwargs:
            request_kwargs["tool_choice"] = kwargs["tool_choice"]

        try:
            self._request_count += 1
            self._last_request_time = time.time()

            logger.info(
                f"Streaming from {self.name} ({self.model}), request #{self._request_count}"
            )

            response = self._client.chat.completions.create(**request_kwargs)
            yield from response

        except Exception as e:
            logger.error(f"Stream request to {self.name} failed: {e}")
            raise
