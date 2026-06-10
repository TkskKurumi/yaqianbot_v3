"""SessionManager — 按群管理会话。

缓存已打开的 Session 对象，按需从 DB 加载。
创建 Session 时注入全局配置（router, common_prompt, plugins 等）。
"""

from __future__ import annotations
from typing import Dict, List, Optional
from threading import RLock

from .session import Session
from ..inference.router import ProviderRouter
from ..plugins.base import BasePlugin


# 全局配置（由 init_manager 设置）
_global_router: Optional[ProviderRouter] = None
_global_common_prompt: str = ""
_global_plugins: List[BasePlugin] = []
_global_image_vision_mode: bool = True
_global_video_vision_mode: bool = False
_global_max_tool_calls: int = 5
_global_debug_dump: bool = False
_global_context_trim_hit: Optional[int] = None
_global_context_trim_trim_to: Optional[int] = None


def init_manager(
    router: ProviderRouter,
    common_prompt: str = "",
    plugins: Optional[List[BasePlugin]] = None,
    image_vision_mode: bool = True,
    video_vision_mode: bool = False,
    max_tool_calls: int = 5,
    debug_dump: bool = False,
    context_trim_hit: Optional[int] = None,
    context_trim_trim_to: Optional[int] = None,
):
    """
    初始化全局会话配置。模块导入后调用。

    Args:
        router: Provider 路由器
        common_prompt: 通用系统提示词
        plugins: 插件列表
        image_vision_mode: 图片是否使用视觉模式
        video_vision_mode: 视频是否使用视觉模式
        max_tool_calls: 最大工具调用轮次
        debug_dump: 是否每次 respond 前输出序列化消息历史到文件
        context_trim_hit: 上下文 token 数阈值，超过时触发剪裁
        context_trim_trim_to: 剪裁目标 token 数
    """
    global _global_router, _global_common_prompt, _global_plugins
    global _global_image_vision_mode, _global_video_vision_mode, _global_max_tool_calls
    global _global_debug_dump, _global_context_trim_hit, _global_context_trim_trim_to

    _global_router = router
    _global_common_prompt = common_prompt
    _global_plugins = plugins or []
    _global_image_vision_mode = image_vision_mode
    _global_video_vision_mode = video_vision_mode
    _global_max_tool_calls = max_tool_calls
    _global_debug_dump = debug_dump
    _global_context_trim_hit = context_trim_hit
    _global_context_trim_trim_to = context_trim_trim_to


class SessionManager:
    """会话管理器。"""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._lock = RLock()

    def open(self, group_id: str) -> Session:
        """获取或创建指定群的会话。"""
        with self._lock:
            if group_id in self._sessions:
                return self._sessions[group_id]
            session = Session.load_from_db(group_id)
            # 注入全局配置
            session.router = _global_router
            session.common_prompt = _global_common_prompt
            session.plugins = list(_global_plugins)
            session.image_vision_mode = _global_image_vision_mode
            session.video_vision_mode = _global_video_vision_mode
            session.max_tool_calls = _global_max_tool_calls
            print("# DEBUG debug_dump =", _global_debug_dump)
            session.debug_dump = _global_debug_dump
            session.context_trim_hit = _global_context_trim_hit
            session.context_trim_trim_to = _global_context_trim_trim_to
            self._sessions[group_id] = session
            return session

    def get_all(self) -> Dict[str, Session]:
        """获取所有已打开的会话。"""
        with self._lock:
            return dict(self._sessions)


# 全局会话管理器
_manager = SessionManager()


def get_manager() -> SessionManager:
    """获取全局会话管理器。"""
    return _manager


def open_session(group_id: str) -> Session:
    """便捷函数：打开指定群的会话。"""
    return _manager.open(group_id)
