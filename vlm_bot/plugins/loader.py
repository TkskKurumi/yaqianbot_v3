"""Plugin Loader — 插件加载器。

根据配置文件加载插件实例。
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from .base import BasePlugin, get_plugin_class, list_plugin_types

logger = logging.getLogger(__name__)


class PluginLoader:
    """插件加载器。

    从配置创建插件实例，管理插件生命周期。
    """

    def __init__(self):
        self._plugins: List[BasePlugin] = []

    def load_from_config(self, configs: List[Dict[str, Any]]) -> List[BasePlugin]:
        """
        从配置列表加载插件。

        每个配置字典必须包含 "type" 字段，指定插件类型。

        Args:
            configs: 插件配置列表，如 [{"type": "image_search", ...}, ...]

        Returns:
            加载成功的插件实例列表
        """
        self._plugins = []

        for i, config in enumerate(configs):
            plugin_type = config.get("type")
            if not plugin_type:
                logger.warning(f"Plugin config [{i}] missing 'type', skipping")
                continue

            # 检查是否启用
            if not config.get("enabled", True):
                logger.info(f"Plugin config [{i}] type={plugin_type} disabled, skipping")
                continue

            # 查找插件类
            plugin_cls = get_plugin_class(plugin_type)
            if plugin_cls is None:
                available = list_plugin_types()
                logger.error(
                    f"Unknown plugin type: {plugin_type}. "
                    f"Available types: {available}"
                )
                continue

            try:
                plugin = plugin_cls.from_config(config)
                self._plugins.append(plugin)
                logger.info(f"Loaded plugin: {plugin_type}")
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_type}: {e}")

        logger.info(f"Loaded {len(self._plugins)} plugins")
        return list(self._plugins)

    @property
    def plugins(self) -> List[BasePlugin]:
        return list(self._plugins)

    def reload(self, configs: List[Dict[str, Any]]) -> List[BasePlugin]:
        """重新加载插件。"""
        return self.load_from_config(configs)


def load_plugins(configs: List[Dict[str, Any]]) -> List[BasePlugin]:
    """
    便捷函数：从配置加载插件。

    Args:
        configs: 插件配置列表

    Returns:
        插件实例列表
    """
    loader = PluginLoader()
    return loader.load_from_config(configs)
