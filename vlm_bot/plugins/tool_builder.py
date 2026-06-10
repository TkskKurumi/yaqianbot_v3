"""Tool Builder — 构建 OpenAI 格式的工具定义。"""

from typing import Any, Dict, List


def build_param(param_type: str, desc: str, **kwargs) -> Dict[str, Any]:
    """构建单个参数定义。

    Args:
        param_type: 参数类型（"string", "number", "integer", "boolean", "array", "object"）
        desc: 参数描述
        **kwargs: 额外字段（如 enum, default 等）

    Returns:
        参数定义字典
    """
    return {"type": param_type, "description": desc, **kwargs}


def build_params(**kwargs) -> Dict[str, Any]:
    """构建参数 properties 字典。

    Args:
        **kwargs: 参数名 -> 参数定义（由 build_param 构建）

    Returns:
        properties 字典
    """
    return kwargs


def build_function(
    name: str,
    desc: str,
    required: List[str],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """构建完整的工具定义（OpenAI 格式）。

    Args:
        name: 工具名称
        desc: 工具描述
        required: 必需参数名列表
        params: 参数 properties 字典（由 build_params 构建）

    Returns:
        OpenAI 格式的工具定义字典
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required,
            },
        },
    }
