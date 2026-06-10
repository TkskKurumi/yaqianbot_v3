"""Provider Router — 优先级 + 负载均衡路由。"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Any, Callable
import traceback
from .client import VLMClient

logger = logging.getLogger(__name__)


class ProviderRouter:
    """
    Provider 路由器。

    路由策略：
    1. 优先级数字越小越优先
    2. 同一优先级的 provider 之间进行负载均衡（基于请求计数）
    3. 失败时自动降级到下一个 provider（同优先级内先尝试完，再降下一级）
    """

    def __init__(self, clients: List[VLMClient]):
        self.clients = list(clients)
        # 按优先级升序排序（数字越小越优先）
        self.clients.sort(key=lambda c: c.priority)

    def get_next_client(self) -> VLMClient:
        """
        获取下一个 provider（负载均衡）。

        返回优先级最高（数字最小）、同优先级内负载最低的 provider。
        """
        if not self.clients:
            raise RuntimeError("No available providers")

        sorted_clients = self._get_sorted_clients()
        return sorted_clients[0]

    def _get_sorted_clients(self) -> List[VLMClient]:
        """
        返回展平的 provider 列表。

        排序规则：优先级升序（数字越小越优先），同优先级内按加权 cost 升序（负载最低在前）。
        cost 每次增加 1/weight，weight 越大 cost 增长越慢，越容易被选中。
        """
        return sorted(self.clients, key=lambda c: (c.priority, c.cost, 1/c.weight))

    def chat_with_fallback(
        self,
        messages,
        system_prompt: Optional[str] = None,
        image_vision_mode: bool = True,
        video_vision_mode: bool = False,
        max_retries: int = 2,
        validate_response_cb: Optional[Callable[[Any], bool]] = None,
        **kwargs,
    ) -> Any:
        """
        带自动降级的对话请求。

        路由策略：按优先级升序 + 负载升序展平列表，依次尝试每个 provider。

        Args:
            messages: 消息列表
            system_prompt: 系统提示词
            image_vision_mode: 图片是否使用原生视觉模式
            video_vision_mode: 视频是否使用原生视觉模式
            max_retries: 最大重试次数（尝试的 provider 数 - 1）
            validate_response_cb: 响应验证回调。返回 False 时降级到下一个 provider。
            **kwargs: 额外参数传递给 client.chat()

        Returns:
            API 响应对象

        Raises:
            RuntimeError: 所有 provider 都失败时
        """
        errors = []
        sorted_clients = self._get_sorted_clients()
        clients_to_try = sorted_clients[:max_retries + 1]

        for client in clients_to_try:
            try:
                response, trimmed_msgs = client.chat(
                    messages,
                    system_prompt=system_prompt,
                    image_vision_mode=image_vision_mode,
                    video_vision_mode=video_vision_mode,
                    **kwargs,
                )
                # 验证响应
                if validate_response_cb and not validate_response_cb(response):
                    raise ValueError("Response validation failed")
                logger.debug(f"Successfully responded by provider: {client.name}")
                return response, trimmed_msgs
            except Exception as e:
                errors.append((client.name, str(e)))
                logger.warning(f"Provider {client.name} failed: {e}", exc_info=True)

        # 所有 provider 都失败
        error_summary = "\n".join(f"- {name}: {err}" for name, err in errors)
        raise RuntimeError(
            f"All {len(errors)} providers failed:\n{error_summary}"
        )

    def chat_stream_with_fallback(
        self,
        messages,
        system_prompt: Optional[str] = None,
        image_vision_mode: bool = True,
        video_vision_mode: bool = False,
        max_retries: int = 2,
        **kwargs,
    ):
        """
        带自动降级的流式对话请求。

        路由策略：按优先级降序 + 负载升序展平列表，依次尝试每个 provider。

        Args:
            messages: 消息列表
            system_prompt: 系统提示词
            image_vision_mode: 图片是否使用原生视觉模式
            video_vision_mode: 视频是否使用原生视觉模式
            max_retries: 最大重试次数（尝试的 provider 数 - 1）
            **kwargs: 额外参数

        Yields:
            流式响应块
        """
        errors = []
        sorted_clients = self._get_sorted_clients()
        clients_to_try = sorted_clients[:max_retries + 1]

        for client in clients_to_try:
            try:
                response = client.chat_stream(
                    messages,
                    system_prompt=system_prompt,
                    image_vision_mode=image_vision_mode,
                    video_vision_mode=video_vision_mode,
                    **kwargs,
                )
                logger.debug(f"Successfully streamed by provider: {client.name}")
                yield from response
                return
            except Exception as e:
                errors.append((client.name, str(e)))
                logger.warning(f"Stream provider {client.name} failed: {e}")

        error_summary = "\n".join(f"- {name}: {err}" for name, err in errors)
        raise RuntimeError(
            f"All {len(errors)} providers failed for stream:\n{error_summary}"
        )

    def add_client(self, client: VLMClient):
        """动态添加 provider。"""
        self.clients.append(client)
        self.clients.sort(key=lambda c: c.priority)

    def remove_client(self, name: str) -> bool:
        """按名称移除 provider。返回是否成功移除。"""
        original_len = len(self.clients)
        self.clients = [c for c in self.clients if c.name != name]
        return len(self.clients) < original_len

    def get_status(self) -> List[dict]:
        """获取所有 provider 的状态。"""
        status = []
        for client in self.clients:
            status.append({
                "name": client.name,
                "model": client.model,
                "priority": client.priority,
                "request_count": client.request_count,
                "last_request_time": client.last_request_time,
            })
        return status
