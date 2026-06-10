"""图片存储 — 保存图片数据和元信息。

设计：
- 前缀带下划线的函数接受 cursor
- 前缀不带下划线的函数创建 cursor
- init_table() 先于 cursor 调用（因为建表是写操作）
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Tuple
import json
import hashlib
import sqlite3
from PIL import Image
from io import BytesIO

from .db import read_cursor, write_cursor


def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_store (
            image_id TEXT PRIMARY KEY,
            data BLOB,
            info BLOB
        )
    """)


def init_table():
    """初始化表结构。"""
    with write_cursor() as cursor:
        _init_table(cursor)


def _blob2dict(blb: bytes) -> Dict[str, Any]:
    return json.loads(blb.decode("utf-8"))


def _dict2blob(obj: Dict[str, Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _get_img_data(cursor: sqlite3.Cursor, image_id: str) -> Optional[bytes]:
    cursor.execute("SELECT data FROM image_store WHERE image_id = ?", (image_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def _get_img_info_all(cursor: sqlite3.Cursor, image_id: str) -> Dict[str, Any]:
    cursor.execute("SELECT info FROM image_store WHERE image_id = ?", (image_id,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return _blob2dict(row[0])
    return {}


def _save_image(cursor: sqlite3.Cursor, image_id: str, data: bytes, info: Optional[Dict[str, Any]] = None):
    info_blob = _dict2blob(info) if info else None
    cursor.execute(
        "INSERT OR REPLACE INTO image_store (image_id, data, info) VALUES (?, ?, ?)",
        (image_id, data, info_blob),
    )


# ── 公开 API ─────────────────────────────────────────────

def save_image(image_id: str, data: bytes, info: Optional[Dict[str, Any]] = None):
    """保存图片数据和元信息。"""
    init_table()
    with write_cursor() as cursor:
        _save_image(cursor, image_id, data, info)


def save_image_from_pil(image: Image.Image, id: Optional[str] = None) -> Tuple[str, bytes]:
    """
    从 PIL Image 保存图片数据到数据库。

    - id 留空时通过 SHA256 哈希自动生成
    - 不触碰 info，保留数据库中已有的 info（或为空）

    Args:
        image: PIL Image 对象
        id: 可选的图片 ID，None 时自动生成

    Returns:
        (image_id, data_bytes) 元组
    """
    init_table()

    # 序列化为 PNG bytes
    bio = BytesIO()
    image.save(bio, format="PNG")
    bio.seek(0)
    data = bio.getvalue()

    # 生成 ID（如果未提供）
    if id is None:
        id = hashlib.sha256(data).hexdigest()[:16]

    # 保留原有 info
    existing_info = None
    with read_cursor() as cursor:
        existing_info = _get_img_info_all(cursor, id)

    with write_cursor() as cursor:
        _save_image(cursor, id, data, existing_info if existing_info else None)

    return id, data


def get_image_data(image_id: str) -> Optional[bytes]:
    """获取图片原始 bytes。"""
    init_table()
    with read_cursor() as cursor:
        return _get_img_data(cursor, image_id)


def get_image_pil(image_id: str) -> Optional[Image.Image]:
    """获取图片 PIL Image（用于 ImageRef 惰性加载）。"""
    data = get_image_data(image_id)
    if data is None:
        return None
    bio = BytesIO(data)
    return Image.open(bio)


def get_image_info(image_id: str, key: str, default: Any = None) -> Any:
    """获取图片元信息中的某个字段。"""
    init_table()
    with read_cursor() as cursor:
        info = _get_img_info_all(cursor, image_id)
        return info.get(key, default)


def update_image_info(image_id: str, updates: Dict[str, Any]):
    """更新图片元信息（合并到现有 info dict）。"""
    init_table()
    with write_cursor() as cursor:
        info = _get_img_info_all(cursor, image_id)
        info.update(updates)
        _save_image(cursor, image_id, _get_img_data(cursor, image_id), info)
