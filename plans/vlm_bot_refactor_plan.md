# vlm_bot 重构计划

> **背景**：vlm_bot 是对 [`group_cai/`](group_cai/) 进行功能近似的全新实现。
> 目标是重构架构、简化设计、统一 API，同时保持原有功能完整。

## 设计决策汇总

| 决策项 | 选择 |
|--------|------|
| 新文件夹名 | `vlm_bot` (visual-language-model bot) |
| 内容模型 | `Content = Union[List[Content], Dict[str, Content], str, float, int, None, ImageRef, VideoRef]` — 递归嵌套的 JSON-like 结构，不含 ContentRef |
| 图片/视频 | 内存中 `image_id` + `pil/bytes`，持久化 `image_id` + `data blob` + `info dict` |
| ContentRef | 消息级引用对象（非 ABC），`id: str` + `data: Dict`，去重时整条消息丢弃，可持久化 |
| 消息模型 | `Message(role, content, tool_calls?, tool_call_id?)` — content 为 Content 或 ContentRef，二选一 |
| 序列化模式 | 配置切换：文本模式（JSON 字符串）或视觉模式（JSON 流中断注入 image_url） |
| 去重机制 | 两阶段：ContentRef 消息级去重（丢弃整条消息）→ ImageRef/VideoRef 去重 + JSON 展平 → OpenAI 格式 |
| Provider 路由 | 优先级排序 + 同优先级随机负载均衡，失败自动降级 |
| 系统提示词 | 静态不变（KV Cache 友好），不含动态上下文 |
| 持久化 | JSON Blob 方式，简单实现 |
| 触发机制 | 3 种（@提及、关键词、时间概率），全局配置 |
| 插件钩子 | 4 个接口均接收 `session: Session`，完全包含 session_id（`session.group_id`），且允许工具异步再触发 respond |
| 插件 API | `get_system_message(session) -> str`，`get_message(session) -> List[Content]`，`add_tools(session, tool_ls, tool_map)` |
| 工具返回 | `tool_handler(session, arguments, send_resp_cb) -> Tuple[List[Content], Union[str, Content]]` — 第一个是注入消息列表（空列表=无注入），第二个是 tool content；send_resp_cb 用于异步再触发时传递回复回调 |
| 工具限流 | 工具自行管理（通过 session.group_id 实现区分对话的限流） |
| 用户消息 | 用户详细信息（username/gender/role 等）通过 ContentRef 提供，同用户多次发言可 dedup |
| 独立性 | vlm_bot 完全独立，不引用 group_cai 任何代码 |

---

## 插件机制详解

### 插件接口

所有接口均接收 `session: Session`（会话对象），而非 `session_id: str`。

设计理由：
1. `session.group_id` 完全包含 session_id 信息
2. 工具可在后台线程中调用 `session.add_message()` + `session.respond()` 实现异步再触发（如异步视频生成任务完成后通知 VLM）

```python
class BasePlugin(ABC):
    type: str = ""  # 子类必须定义

    @abstractmethod
    def get_system_message(self, session: Session) -> str:
        """返回系统提示词片段。空字符串 = 不提供。"""

    @abstractmethod
    def get_message(self, session: Session) -> List[Content]:
        """返回要注入的消息列表。空列表 = 无消息。
        外层 List 是必须的区分层（因为 Content 本身可以是列表）。"""

    @abstractmethod
    def add_tools(
        self, session: Session,
        tool_ls: List[Dict], tool_handler_map: Dict[str, ToolHandler]
    ) -> tuple:
        """添加工具定义和 handler。
        ToolHandler 签名：handler(session, arguments, send_resp_cb) -> Tuple[List[Content], Union[str, Content]]"""
```

### 工具返回机制

工具 handler 返回 `Tuple[List[Content], Union[str, Content]]`：
- **第一个值**（`List[Content]`）：需要注入到会话的额外消息列表。空列表 = 无注入。
  - 用于工具需要返回图片等 Content 的场景（如图片生成工具返回 ImageRef）。
  - 注入的消息 role 为 "user"，name 为插件 type。
- **第二个值**（`Union[str, Content]`）：工具返回给 VLM 的 content。
  - 简单场景直接返回字符串结果。
  - 复杂场景返回 Content（如 `{"image_id": "xxx"}`），由 session 序列化为 JSON 字符串。

**使用示例**：
- 简单工具：`return [], "搜索完成，找到 3 个结果"`
- 图片生成：`return [[ImageRef(id="xxx")], "图片已生成"], "success"`

### 工具异步再触发

工具 handler 接收 `session: Session` + `send_resp_cb` 回调，因此可以在后台线程中实现异步再触发：

```python
def video_gen_handler(session: Session, arguments: dict, send_resp_cb) -> Tuple[List[Content], str]:
    # 1. 提交异步任务
    task_id = submit_video_task(arguments["prompt"])

    # 2. 启动后台线程，任务完成后再次触发 respond
    #    send_resp_cb 通过闭包传递，后台线程直接调用 session.respond(send_resp_cb=send_resp_cb)
    def on_complete():
        video_data = wait_for_task(task_id)
        video_ref = save_video(video_data)
        session.add_message(Message(role="user", content=[
            f"视频生成完成: {arguments['prompt']}", video_ref
        ]))
        session.respond(send_resp_cb=send_resp_cb)  # 再次触发 VLM 推理

    threading.Thread(target=on_complete, daemon=True).start()

    # 3. 立即返回"已提交"状态
    return [], "视频生成任务已提交，完成后会通知你"
```

这种模式适用于耗时较长的异步任务（视频生成、图片生成、大文件处理等），工具先返回"已提交"，任务完成后通过 `session.respond(send_resp_cb=...)` 再次触发 VLM 推理并发送结果。

### 用户消息与 ContentRef 去重

用户消息分为两条消息：
1. **用户信息 ContentRef**：`ContentRef(id="qq_user_{userid}", data={"username": "...", "gender": "...", "role": "..."})`
2. **用户消息 Content**：`{"qq_id": "qq_user_{userid}", "content": [...]}`

去重时，ContentRef 的 data 未变则整条消息被丢弃，但用户消息保留（通过 `qq_id` 关联用户信息）。

**示例**：
```
去重前：
  ContentRef(id="qq_user_123", data={username: "千千", ...})  # 用户信息
  {"qq_id": "qq_user_123", "content": ["你好"]}                # 消息 1
  ContentRef(id="qq_user_123", data={username: "千千", ...})  # 用户信息（重复）
  {"qq_id": "qq_user_123", "content": ["在吗"]}                # 消息 2

去重后：
  ContentRef(id="qq_user_123", data={username: "千千", ...})  # 保留首次
  {"qq_id": "qq_user_123", "content": ["你好"]}                # 消息 1
  {"qq_id": "qq_user_123", "content": ["在吗"]}                # 消息 2（通过 qq_id 知道是谁）
```
| API 统一 | 仅 OpenAI Compatible API，不再支持 Volce 专有 API |
| 术语 | 不再出现 "deepseek"，统一使用 "vlm" / "provider" |
| 视频处理 | 默认用 desc 文字描述，设计上允许切换为首帧图片 |
| 配置管理 | 由 yaqianbot 框架统一提供，vlm_bot 无独立 config.py |
| 消息累积 | 消息始终添加到会话，trigger 只控制 respond（支持批处理） |
| 图片缩放 | base64 序列化时自动缩放，max_bytes=500KB |
| Debug 功能 | debug_dump 开关：序列化消息历史（省略 base64）写入文件 |

---

## 目录结构（实际实现）

```
vlm_bot/
├── __init__.py
├── handler.py              # 入口：消息监听、触发判断、调度
│
├── message/                # 消息模型
│   ├── __init__.py
│   ├── message.py          # Message + Content 类型定义
│   ├── content_ref.py      # ContentRef（消息级引用）
│   ├── image_ref.py        # ImageRef（图片引用）
│   ├── video_ref.py        # VideoRef（视频引用）
│   └── db_serialization.py # 持久化序列化/反序列化
│
├── session/                # 会话管理
│   ├── __init__.py
│   ├── manager.py          # SessionManager（按群管理会话）
│   └── session.py          # Session（消息历史、裁剪、持久化、respond）
│
├── inference/              # VLM 推理层
│   ├── __init__.py
│   ├── client.py           # VLMClient（OpenAI Compatible 封装）
│   ├── router.py           # ProviderRouter（优先级路由 + 负载均衡）
│   ├── system_prompt.py    # 系统提示词组装
│   └── serializer.py       # 序列化器（Content → OpenAI 格式）
│
├── plugins/                # 插件系统（工具由插件提供）
│   ├── __init__.py
│   ├── base.py             # BasePlugin 抽象基类
│   ├── loader.py           # 插件加载器
│   └── builtins/           # 内置插件
│       ├── __init__.py
│       ├── timestamp.py    # TimestampPlugin（时间戳注入）
│       └── sticker_pack.py # StickerPackPlugin（表情包）
│
├── database/               # 数据库层
│   ├── __init__.py
│   ├── db.py               # SQLite 连接管理
│   ├── session_store.py    # 会话存储
│   ├── image_store.py      # 图片存储
│   └── video_store.py      # 视频存储
│
├── trigger/                # 触发机制
│   ├── __init__.py
│   └── scheduler.py        # 触发调度器
│
└── utils/                  # 工具函数
    ├── __init__.py
    └── debug.py            # debug 工具函数
```

---

## 内容序列化设计

### 消息模型

```python
class Message:
    role: str                              # "system" | "user" | "assistant" | "tool"
    content: Union[Content, ContentRef]    # 二选一：纯 Content 树 或 ContentRef 对象
    tool_calls: Optional[List[Dict]]       # assistant 消息的工具调用
    tool_call_id: Optional[str]            # tool 消息的关联 ID
    name: Optional[str]                    # 可选名称
```

### 内容类型定义（不含 ContentRef）

```python
Content = Union[
    List[Content],
    Dict[str, Content],
    str, float, int, None,
    ImageRef, VideoRef
]
```

### 引用对象

**ImageRef / VideoRef**
- `id: str` — 唯一标识（SHA256 哈希）
- 去重：基于 id，相同 id 只输出一次完整数据
- 持久化：`{"type": "image/video", "id": "..."}`
- **描述缓存**：文本模式下调用视觉模型生成描述，结果缓存在数据库 `info dict` 中
  - 存储格式：`{"desc": "描述文字", "desc_salt": "xxx"}`
  - Salt 由配置文件手动指定 + prompt 组合，用于手动失效缓存（换模型/改 providers/修 bug 时改 salt 即可）

**ContentRef**（消息级，普通类，非 ABC）
- `id: str` — 唯一标识
- `data: Dict` — 可序列化的纯数据（可能包含 ImageRef/VideoRef）
- 去重：**消息级去重** — data 未变则整条消息丢弃（不输出任何 token）
- 持久化：`{"type": "content_ref", "id": id, "data": {...}}` — data 嵌套在 `"data"` 键下，避免与 data 内部的 `"type"` 字段冲突
- 反序列化：检测到 `dict.get("type") == "content_ref"` 且含 `"id"` → 从 `"data"` 键读取并反序列化

### 序列化流程

```
阶段 1 — ContentRef 消息级去重
  遍历消息列表，对 content 为 ContentRef 的消息：
  - data 未变 → 整条消息丢弃
  - data 已变 → 将 ContentRef 替换为 data dict（变为普通 Content）

阶段 2 — ImageRef/VideoRef 去重 + JSON 展平
  递归展平 Content 树为文本流 + 媒体对象
  - ImageRef 首次 → `{"type": "image", "id": "xxx", "data": ...}`（视觉模式）或 `{"type": "image", "id": "xxx", "desc": "..."}`（文本模式）
  - ImageRef 后续 → `{"type": "image", "id": "xxx"}`（保持相同格式，无 dedup:true）

阶段 3 — OpenAI 格式
  合并连续文本段，生成分段内容
```

### 视觉模式示例

输入内容树：
```python
{"foo": "bar", "image": ImageRef(id="1234", pil=...)}
```

序列化输出：
```python
[
    {"type": "text", "text": '{"foo": "bar", "image": {"type": "image", "id": "1234", "data": '},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    {"type": "text", "text": "}"},
]
```

VLM 逻辑上看到的等价内容：
```json
{"foo": "bar", "image": {"type": "image", "id": "1234", "data": <图片像素>}}
```

### 文本模式示例

同一内容树在文本模式下：
```python
[
    {"type": "text", "text": '{"foo": "bar", "image": {"type": "image", "id": "1234", "desc": "图片描述"}}'}
]
```

### 持久化序列化

```python
{"foo": "bar", "image": {"type": "image", "id": "1234"}}
```

读取时 `{"type": "image", "id": "1234"}` → `ImageRef(id="1234")`

### 去重与上下文剪裁

每次 VLM 请求前：
1. 剪裁消息历史
2. 在剪裁后的消息上重建 `dedup_map: {id: first_instance}`
3. 序列化时使用新的 dedup_map

---

## 核心数据流

详见 [`plans/vlm_bot_dataflow.dot`](vlm_bot_dataflow.dot)（Graphviz DOT 格式）。

**简要流程：**
1. QQ 消息 → handler 接收
2. **始终**添加消息到会话（ContentRef + Content 消息对）
3. 检查 trigger → 未触发则返回（消息已累积）
4. 触发后：批处理等待 → 裁剪历史 → 插件注入消息 → respond
5. respond 内：构建系统提示词 → 收集工具 → 序列化 → VLM 调用 → 工具循环
6. 循环结束后：持久化 → 发送回复

**关键设计：**
- 消息始终添加，trigger 只控制 respond（支持批处理）
- 插件通过 `get_message(session)` 注入消息
- 工具可异步再触发：后台线程 `add_message + respond`

---

## 配置管理

**vlm_bot 没有独立的配置文件。** 所有配置参数由 yaqianbot 框架统一提供，通过 `init_handler()` 或类似入口函数传入。

框架负责：
- 加载 YAML 配置文件
- 验证配置
- 将配置传递给 vlm_bot 各模块

vlm_bot 各模块接收配置的方式：
- `TriggerScheduler` — 通过 `TriggerConfig.from_config()` 创建
- `VLMClient` — 通过构造函数参数传入 provider 配置
- `Session` — 通过构造函数参数传入 common_prompt、vision_mode 等
- `Plugin` — 通过 `from_config()` 工厂方法创建

---

## 实施步骤

### 阶段 1：基础框架
1. 创建目录结构
2. 实现消息模型 (`message/`)
3. 实现数据库层 (`database/`)

### 阶段 2：会话与推理
4. 实现会话管理 (`session/`)
5. 实现 Provider 路由 (`inference/router.py`)
6. 实现 VLM 客户端 (`inference/client.py`)
7. 实现提示词组装 (`inference/system_prompt.py`)
8. 实现序列化器 (`inference/serializer.py`)

### 阶段 3：插件系统 ✅ 完成
9. 实现插件基类和加载器 (`plugins/base.py`, `plugins/loader.py`)
10. 实现内置插件：TimestampPlugin、StickerPackPlugin

### 阶段 4：触发与入口 ✅ 完成
11. 实现触发调度器 (`trigger/scheduler.py`)
12. 实现入口处理器 (`handler.py`)

### 阶段 5：图片检索 ⏳ 待实现
13. 实现图片语义检索（独立实现，不依赖 group_cai）

### 阶段 6：清理与迁移 ⏳ 待实现
14. 移除 vlm_bot 中所有 group_cai 引用
15. 单元测试
16. 集成测试
17. 从 group_cai 迁移数据
