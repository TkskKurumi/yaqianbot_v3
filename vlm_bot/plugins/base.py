"""Plugin Base — 插件基类。

插件设计：
- ABC 基类，子类必须实现 type 属性
- 类型注册表：type (str) -> class
- 工厂方法：from_config(config: dict) -> BasePlugin
- 所有接口均接收 session: Session，完全包含 session_id 且允许异步再触发
- 每个插件可提供：系统提示词、消息注入、工具定义

插件 API：
- get_system_message(session) -> str
- get_message(session) -> List[Content]  （空列表 = 无消息）
- add_tools(session, tool_ls, tool_map)
- tool_handler(session, arguments) -> Tuple[List[Content], Union[str, Content]]
  第一个返回值：需要注入的消息列表（空列表 = 无注入）
  第二个返回值：tool content（字符串或 Content）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Tuple, Type, Optional, Union, Any, TYPE_CHECKING

from ..message.message import Content, ContentRef, Message

if TYPE_CHECKING:
    from ..session.session import Session

logger = logging.getLogger(__name__)

# 工具处理函数类型：
# 返回 (injected_messages, tool_content)
# injected_messages: 需要注入到会话的消息列表（空列表 = 无注入）
# tool_content: 工具返回给 VLM 的内容（字符串或 Content）
# send_resp_cb: 回复发送回调（用于异步再触发时传递）
ToolHandler = Callable[["Session", Dict[str, Any], Optional[Callable[[Message], None]]], Tuple[List[Content], Union[str, Content]]]

# 类型注册表：type (str) -> plugin class
_PLUGIN_REGISTRY: Dict[str, Type["BasePlugin"]] = {}


def register_plugin(cls: Type["BasePlugin"]):
    """注册插件类型。"""
    _PLUGIN_REGISTRY[cls.type] = cls
    logger.info(f"Registered plugin type: {cls.type}")


def get_plugin_class(plugin_type: str) -> Optional[Type["BasePlugin"]]:
    """根据类型名获取插件类。"""
    return _PLUGIN_REGISTRY.get(plugin_type)


def list_plugin_types() -> List[str]:
    """列出所有已注册的插件类型。"""
    return list(_PLUGIN_REGISTRY.keys())


class BasePlugin(ABC):
    """插件基类。所有插件必须继承此类。

    所有接口均接收 session: Session，完全包含 session_id 且允许异步再触发。
    """

    # 子类必须定义插件类型标识（字符串类属性）
    type: str = ""

    @classmethod
    def from_config(cls, config: dict) -> "BasePlugin":
        """
        从配置字典创建插件实例。

        Args:
            config: 配置字典（来自配置文件的插件配置，包含 type 字段）

        Returns:
            插件实例

        Raises:
            ValueError: 当配置无效时
        """
        # 移除 type 字段（用于查找插件类，不是构造函数参数）
        config_copy = dict(config)
        config_copy.pop("type", None)
        return cls(**config_copy)

    @abstractmethod
    def get_system_message(self, session: Session) -> str:
        """
        返回插件的系统提示词片段。

        Args:
            session: 会话对象（通过 session.group_id 获取群 ID）

        Returns:
            系统提示词片段。如果不需要提供，返回空字符串。
        """
        pass

    @abstractmethod
    def get_message(self, session: Session) -> List[Content]:
        """
        返回插件要注入到会话的消息内容列表。

        Args:
            session: 会话对象（通过 session.group_id 获取群 ID）

        Returns:
            Content 列表。空列表表示没有消息要注入。
            注意：Content 本身可以是列表，所以外层 List 是必须的区分层。
        """
        pass

    @abstractmethod
    def add_tools(
        self,
        session: Session,
        tool_ls: List[Dict[str, Any]],
        tool_handler_map: Dict[str, ToolHandler],
    ) -> tuple:
        """
        向工具列表和工具处理映射中添加本插件提供的工具。

        Args:
            session: 会话对象（通过 session.group_id 获取群 ID）
            tool_ls: 工具定义列表（OpenAI 格式）
            tool_handler_map: 工具名称 -> 处理函数映射
                              处理函数签名：
                              handler(session: Session, arguments: dict,
                                      send_resp_cb: Optional[Callable[[Message], None]])
                                  -> Tuple[List[Content], Union[str, Content]]

        Returns:
            (tool_ls, tool_handler_map) 修改后的列表和映射
        """
        return tool_ls, tool_handler_map
