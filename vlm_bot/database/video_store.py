"""视频存储 — 保存视频数据和元信息。

设计：
- 前缀带下划线的函数接受 cursor
- 前缀不带下划线的函数创建 cursor
- init_table() 先于 cursor 调用（因为建表是写操作）
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import json
import sqlite3

from .db import read_cursor, write_cursor


def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_store (
            video_id TEXT PRIMARY KEY,
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


def _get_vid_data(cursor: sqlite3.Cursor, video_id: str) -> Optional[bytes]:
    cursor.execute("SELECT data FROM video_store WHERE video_id = ?", (video_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def _get_vid_info_all(cursor: sqlite3.Cursor, video_id: str) -> Dict[str, Any]:
    cursor.execute("SELECT info FROM video_store WHERE video_id = ?", (video_id,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return _blob2dict(row[0])
    return {}


def _save_video(cursor: sqlite3.Cursor, video_id: str, data: bytes, info: Optional[Dict[str, Any]] = None):
    info_blob = _dict2blob(info) if info else None
    cursor.execute(
        "INSERT OR REPLACE INTO video_store (video_id, data, info) VALUES (?, ?, ?)",
        (video_id, data, info_blob),
    )


# ── 公开 API ─────────────────────────────────────────────

def save_video(video_id: str, data: bytes, info: Optional[Dict[str, Any]] = None):
    """保存视频数据和元信息。"""
    init_table()
    with write_cursor() as cursor:
        _save_video(cursor, video_id, data, info)


def get_video_data(video_id: str) -> Optional[bytes]:
    """获取视频原始 bytes。"""
    init_table()
    with read_cursor() as cursor:
        return _get_vid_data(cursor, video_id)


def get_video_info(video_id: str, key: str, default: Any = None) -> Any:
    """获取视频元信息中的某个字段。"""
    init_table()
    with read_cursor() as cursor:
        info = _get_vid_info_all(cursor, video_id)
        return info.get(key, default)


def update_video_info(video_id: str, updates: Dict[str, Any]):
    """更新视频元信息（合并到现有 info dict）。"""
    init_table()
    with write_cursor() as cursor:
        info = _get_vid_info_all(cursor, video_id)
        info.update(updates)
        _save_video(cursor, video_id, _get_vid_data(cursor, video_id), info)
