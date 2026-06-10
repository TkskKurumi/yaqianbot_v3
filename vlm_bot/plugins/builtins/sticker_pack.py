"""StickerPackPlugin — 内置表情包插件。

将指定文件夹的图片加载到数据库，作为 ContentRef 注入上下文。
VLM 回复时可以引用这些表情包表达情绪。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from ..base import BasePlugin, register_plugin
from ...message.message import Content
from ...message.content_ref import ContentRef
from ...message.image_ref import ImageRef
from ...database.image_store import save_image_from_pil, get_image_data

logger = logging.getLogger(__name__)


@register_plugin
class StickerPackPlugin(BasePlugin):
    """内置表情包插件。

    从指定文件夹加载图片到数据库，每次 get_message 返回所有表情包的
    ContentRef（去重保证只输出一次）。
    """

    type = "sticker_pack"

    def __init__(self, folder: str, name: str = "sticker_pack"):
        """
        Args:
            folder: 表情包文件夹路径
            name: 表情包包名称（用于 ContentRef id 前缀）
        """
        self.folder = folder
        self.name = name
        self._sticker_refs: List[ContentRef] = []
        self._loaded = False

    def _load_stickers(self):
        """加载表情包文件夹中的所有图片到数据库。"""
        if self._loaded:
            return

        folder_path = Path(self.folder)
        if not folder_path.exists():
            logger.warning(f"Sticker pack folder not found: {self.folder}")
            self._loaded = True
            return

        # 支持的图片格式
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

        stickers = []
        for file_path in sorted(folder_path.iterdir()):
            if file_path.suffix.lower() not in image_extensions:
                continue
            if not file_path.is_file():
                continue

            try:
                pil_img = Image.open(file_path)
                # 使用文件名（不含扩展名）作为 id 前缀
                image_id, _ = save_image_from_pil(pil_img)

                # 创建 ContentRef: 包含 ImageRef 和表情名称
                sticker_ref = ContentRef(
                    id=f"sticker_{self.name}_{file_path.stem}",
                    data={
                        "type": "sticker",
                        "image": ImageRef(image_id),
                        "desc": "This is an built-in sticker provided by system (not sent by user), you can send it to user on need."
                    },
                )
                stickers.append(sticker_ref)
                logger.debug(f"Loaded sticker: {file_path.name} -> {image_id}")
            except Exception as e:
                logger.error(f"Failed to load sticker {file_path}: {e}")

        self._sticker_refs = stickers
        self._loaded = True
        logger.info(f"Loaded {len(stickers)} stickers from {self.folder}")

    def get_system_message(self, session) -> str:
        """返回系统提示词，告知 VLM 可以使用表情包。"""
        self._load_stickers()
        if not self._sticker_refs:
            return ""
        names = ", ".join(r.data["image"].id for r in self._sticker_refs)
        return (
            f"\n你可以使用表情包表达情绪。表情包列表: {names}。"
            f"使用时在回复中包含对应的图片。"
        )

    def get_message(self, session) -> List[Content]:
        """返回所有表情包的 ContentRef（去重保证只输出一次）。"""
        self._load_stickers()
        return list(self._sticker_refs)

    def add_tools(self, session, tool_ls, tool_handler_map):
        return tool_ls, tool_handler_map
