"""Session — 群聊会话管理。

管理单个群的对话历史，包括消息裁剪、持久化和 VLM 推理。
"""

from __future__ import annotations

import json
import logging
from typing import List, Dict, Any, Optional, Callable
from threading import RLock

from ..message.message import Message, Content
from ..message.db_serialization import deserialize_db_dict
from ..message.image_ref import ImageRef
from ..message.video_ref import VideoRef
from ..database.session_store import get_messages, save_messages
from ..database.image_store import get_image_data
from ..database.video_store import get_video_data
from ..inference.router import ProviderRouter
from ..inference.system_prompt import build_system_prompt
from ..inference.serializer import serialize_messages
from ..plugins.base import BasePlugin


logger = logging.getLogger(__name__)


def _trim_length(msgs: List[Message], num: Optional[int] = None, ratio: Optional[float] = None) -> List[Message]:
    """裁剪消息历史，保留最近的 num 条或 ratio 比例。"""
    if ratio is not None:
        num = int(len(msgs) * ratio)
    elif num is None:
        num = int(len(msgs) * 0.5)
    start = max(len(msgs) - num, 0)
    # 确保裁剪点在用户消息处
    while start < len(msgs):
        if msgs[start].role == "user":
            break
        start += 1
    return msgs[start:]


class Session:
    """单个群的会话。

    负责消息管理、VLM 推理和持久化。
    """

    def __init__(
        self,
        group_id: str,
        messages: Optional[List[Message]] = None,
        router: Optional[ProviderRouter] = None,
        plugins: Optional[List[BasePlugin]] = None,
        common_prompt: str = "",
        image_vision_mode: bool = True,
        video_vision_mode: bool = False,
        max_tool_calls: int = 5,
        debug_dump: bool = False,
        context_trim_hit: Optional[int] = None,
        context_trim_trim_to: Optional[int] = None,
    ):
        self.group_id = group_id
        self.messages: List[Message] = messages if messages is not None else []
        self.LOCK = RLock()
        self.router = router
        self.plugins = plugins or []
        self.common_prompt = common_prompt
        self.image_vision_mode = image_vision_mode
        self.video_vision_mode = video_vision_mode
        self.max_tool_calls = max_tool_calls
        self.debug_dump = debug_dump
        self.context_trim_hit = context_trim_hit
        self.context_trim_trim_to = context_trim_trim_to
        if (plugins):
            logger.debug("# DEBUG: plugins", [i.type for i in plugins])
        else:
            logger.debug("# DEBUG: plugins []")

    def add_message(self, message: Message):
        """添加消息到历史。"""
        with self.LOCK:
            if (self.messages):
                if (message.role == "assistant" and self.messages[-1].role == "assistant"):
                    raise ValueError("consecutive assistant message")
            self.messages.append(message)

    def trim_length_auto(self, max_count: int, preferred_count: int):
        """自动裁剪消息历史。"""
        with self.LOCK:
            if len(self.messages) > max_count:
                self.messages = _trim_length(self.messages, num=preferred_count)

    def trim_length(self, num: Optional[int] = None, ratio: Optional[float] = None):
        """手动裁剪消息历史。"""
        with self.LOCK:
            self.messages = _trim_length(self.messages, num=num, ratio=ratio)

    def save_to_db(self):
        """持久化到数据库。"""
        with self.LOCK:
            msgs_db = [m.to_db() for m in self.messages]
            save_messages(self.group_id, msgs_db)

    @classmethod
    def load_from_db(cls, group_id: str) -> Session:
        """从数据库加载会话。"""
        msgs_db = get_messages(group_id)
        messages = [Message.from_db(m) for m in msgs_db]
        return cls(group_id, messages)

    def _build_system_prompt(self) -> str:
        """构建系统提示词。"""
        plugin_prompts = [
            p.get_system_message(self)
            for p in self.plugins
            if p.get_system_message(self)
        ]
        return build_system_prompt(self.common_prompt, plugin_prompts)

    def _collect_tools(self) -> tuple:
        """收集所有插件的工具。"""
        tool_ls: List[Dict[str, Any]] = []
        tool_handler_map: Dict[str, Any] = {}

        for plugin in self.plugins:
            tool_ls, tool_handler_map = plugin.add_tools(
                self, tool_ls, tool_handler_map
            )

        return tool_ls, tool_handler_map

    def _execute_tool_call(
        self, tool_name: str, tool_arguments: Any, tool_handler_map: Dict[str, Any],
        send_resp_cb: Optional[Callable[[Message], None]] = None,
    ) -> tuple:
        """执行工具调用。

        工具 handler 签名：
            handler(session: Session, arguments: dict, send_resp_cb: Optional[Callable])
                -> Tuple[List[Content], Union[str, Content]]

        Returns:
            (injected_messages, tool_content_str)
            injected_messages: 需要注入到会话的消息列表
            tool_content_str: 工具返回给 VLM 的字符串内容
        """
        handler = tool_handler_map.get(tool_name)
        if not handler:
            return [], f"Error: Unknown tool '{tool_name}'"

        try:
            # tool_arguments 一定是 dict 或内容为 dict 的 JSON string
            if isinstance(tool_arguments, str):
                tool_arguments = json.loads(tool_arguments)
            if not isinstance(tool_arguments, dict):
                logger.warning(
                    f"Tool {tool_name} arguments is not dict: "
                    f"type={type(tool_arguments)}, value={tool_arguments!r}"
                )
                raise TypeError(
                    f"Tool arguments must be dict, got {type(tool_arguments).__name__}"
                )
            # 调用 handler(session, arguments, send_resp_cb)
            injected_msgs, tool_content = handler(self, tool_arguments, send_resp_cb)

            # 将 tool_content 序列化为字符串
            if isinstance(tool_content, str):
                tool_str = tool_content
            elif isinstance(tool_content, (dict, list)):
                tool_str = json.dumps(tool_content, ensure_ascii=False)
            else:
                tool_str = str(tool_content)

            return injected_msgs, tool_str
        except Exception as e:
            logger.error(f"Tool {tool_name} execution failed: {e}", exc_info=True)
            return [], f"Error executing {tool_name}: {str(e)}"

    def _validate_vlm_content(self, response) -> bool:
        """
        验证 VLM 返回的内容。

        规则：
        - 有 content 时：必须是合法的 JSON 数组 List[str, ImageRef, VideoRef]
        - content 为空时：必须有 tool_calls（纯工具调用响应）
        - content 和 tool_calls 都没有：非法

        Args:
            response: VLM 的 ChatCompletion 响应对象

        Returns:
            True 如果格式正确
        """
        choice = response.choices[0]
        raw_content = choice.message.content or ""
        tool_calls = getattr(choice.message, "tool_calls", None)

        if raw_content:
            # 有 content 时，验证 JSON 格式
            try:
                parsed = json.loads(raw_content)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"content validate error {raw_content} cannot decode json")
                return False

            if not isinstance(parsed, list):
                logger.warning(f"content validate error {raw_content} expect list instead of {type(parsed)}")
                return False

            for item in parsed:
                if isinstance(item, str):
                    continue
                if isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "image":
                        image_id = item.get("id")
                        if not image_id or get_image_data(image_id) is None:
                            logger.warning(f"content validate error {raw_content} image id not found {image_id}")
                            return False
                        continue
                    elif item_type == "video":
                        video_id = item.get("id")
                        logger.warning(f"content validate error {raw_content} image id not found {video_id}")
                        if not video_id or get_video_data(video_id) is None:
                            return False
                        continue
                    logger.warning(f"content validate error {raw_content} unexcpected dict item type {item_type}")
                    return False
                logger.warning(f"content validate error {raw_content} unexcpected item type {type(item)}")
                return False

            return True
        elif tool_calls:
            # content 为空但有 tool_calls — 纯工具调用响应，合法
            return True
        else:
            # content 和 tool_calls 都没有 — 非法
            return False

    def _deserialize_vlm_content(self, raw_content: str) -> Content:
        """
        将 VLM 返回的 JSON 数组反序列化为 Content。

        VLM 只允许回应 List[str, ImageRef, VideoRef]。
        JSON 格式：["text1", {"type": "image", "id": "xxx"}, "text2", ...]

        Args:
            raw_content: VLM 返回的原始字符串（必须是 JSON 数组）

        Returns:
            Content 对象（List[str, ImageRef, VideoRef]）
        """
        if not raw_content:
            return []
        parsed = json.loads(raw_content)
        items = []
        for item in parsed:
            if isinstance(item, dict):
                item = deserialize_db_dict(item)
            items.append(item)
        return items

    def _parse_response(self, response) -> Message:
        """解析 VLM 响应为 Message 对象。"""
        choice = response.choices[0]
        raw_content = choice.message.content or ""
        content = self._deserialize_vlm_content(raw_content)
        raw_tool_calls = getattr(choice.message, "tool_calls", None)
        # 将 OpenAI Pydantic 对象转换为 dict
        if raw_tool_calls:
            tool_calls_0 = [tc.model_dump() for tc in raw_tool_calls]
            tool_calls = []
            for tool_call in tool_calls_0:
                tool_args = tool_call["function"]["arguments"]
                if (isinstance(tool_args, str)):
                    tool_args = json.loads(tool_args)
                tool_call["function"]["arguments"] = tool_args
                tool_calls.append(tool_call)
        else:
            tool_calls = None
        return Message(role="assistant", content=content, tool_calls=tool_calls)

    def respond(
        self,
        send_resp_cb: Optional[Callable[[Message], None]] = None,
    ) -> Message:
        """
        对当前会话消息历史进行 VLM 推理。

        执行 VLM 调用 + 工具循环，将产生的消息写入会话历史，最后持久化。

        Args:
            send_resp_cb: 回复发送回调。收到最终回复时调用，由外部负责将内容转换为框架格式并发送。

        Returns:
            AI 回复消息
        """
        if not self.router:
            raise RuntimeError("Session has no router configured")

        with self.LOCK:
            system_prompt = self._build_system_prompt()
            tool_ls, tool_handler_map = self._collect_tools()

            assistant_msg = None
            # 工具调用去重：防止模型重复调用相同工具+参数
            tool_visited: set[tuple[str, str]] = set()
            # 工具调用剩余次数
            retry_tool = self.max_tool_calls

            while True:
                # Debug: 序列化消息历史（省略 image base64 data）并写入文件
                if self.debug_dump:
                    from ..utils.debug import debug_dump_chat_history

                    debug_dump_chat_history(
                        self.group_id,
                        self.messages,
                        self.image_vision_mode,
                        self.video_vision_mode,
                        logger=logger,
                    )

                # 确定 tool_choice：有工具且还有重试次数时用 "auto"，否则 "none"
                tool_choice = "auto" if (retry_tool >= 0 and tool_ls) else "none"
                try:
                    response, trimmed_msgs = self.router.chat_with_fallback(
                        self.messages,
                        system_prompt=system_prompt,
                        image_vision_mode=self.image_vision_mode,
                        video_vision_mode=self.video_vision_mode,
                        validate_response_cb=lambda r: self._validate_vlm_content(r),
                        tools=tool_ls if tool_ls else None,
                        tool_choice=tool_choice,
                    )
                except RuntimeError as e:
                    logger.error(f"chat with router failed for session {self.group_id} {e}")
                    raise
                # 如果裁剪过，替换 session 消息列表（检查最后一条消息相同）
                assert trimmed_msgs
                assert trimmed_msgs[-1] is self.messages[-1]
                if len(trimmed_msgs) != len(self.messages):
                    logger.info(f"messages is auto trimmed by chat {len(self.messages)} -> {len(trimmed_msgs)}")
                self.messages = trimmed_msgs

                assistant_msg = self._parse_response(response)
                
                if assistant_msg.content and send_resp_cb:
                    try:
                        send_resp_cb(assistant_msg)
                    except:
                        msg = serialize_messages([assistant_msg],
                            image_vision_mode=self.image_vision_mode,
                            video_vision_mode=self.video_vision_mode,omit_data=True,
                        )
                        msg = json.dumps(msg)
                        logger.error(f"Cannot send content {msg}")
                        raise
                self.add_message(assistant_msg)

                if not assistant_msg.tool_calls:
                    break

                for tool_call in assistant_msg.tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]

                    # 去重检查：(tool_name, tool_args) 是否已执行过
                    if (isinstance(tool_args, str)):
                        visited_key = (tool_name, tool_args)
                    else:
                        visited_key = (tool_name, json.dumps(tool_args, ensure_ascii=False))
                    if visited_key in tool_visited:
                        injected, tool_result = [], json.dumps(
                            {"status": "forbidden", "reason": "duplicated tool call"},
                            ensure_ascii=False,
                        )
                    elif retry_tool <= 0:
                        injected, tool_result = [], json.dumps(
                            {"status": "forbidden", "reason": "tool call retry count exceed"},
                            ensure_ascii=False,
                        )
                    else:
                        tool_visited.add(visited_key)
                        injected, tool_result = self._execute_tool_call(
                            tool_name, tool_args, tool_handler_map, send_resp_cb
                        )

                    tool_msg = Message(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tool_call.get("id"),
                        name=tool_name
                    )
                    self.add_message(tool_msg)

                    # 注入工具返回的额外消息（role=user）
                    for content in injected:
                        self.add_message(Message(role="user", content=content))

                retry_tool -= 1

                # 上下文剪裁：检查 response 的 total_tokens 是否超过 hit 阈值
                if (
                    self.context_trim_hit
                    and self.context_trim_trim_to
                ):
                    usage = getattr(response, "usage", None)
                    if usage:
                        total_tokens = getattr(usage, "total_tokens", 0)
                        if total_tokens > self.context_trim_hit:
                            ratio = self.context_trim_trim_to / self.context_trim_hit
                            logger.info(
                                f"Context trim triggered: {total_tokens} > {self.context_trim_hit}, "
                                f"trimming with ratio={ratio:.2f}"
                            )
                            self.trim_length(ratio=ratio)

            # 持久化
            self.save_to_db()

        return assistant_msg
