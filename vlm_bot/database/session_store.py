"""会话存储 — 保存群聊会话消息历史（JSON Blob）。

设计：
- 前缀带下划线的函数接受 cursor
- 前缀不带下划线的函数创建 cursor
- init_table() 先于 cursor 调用（因为建表是写操作）
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
import json
import sqlite3

from .db import read_cursor, write_cursor


def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_store (
            group_id TEXT PRIMARY KEY,
            messages BLOB
        )
    """)


def init_table():
    """初始化表结构。"""
    with write_cursor() as cursor:
        _init_table(cursor)


def _json_blob2dict(blb: bytes) -> Dict[str, Any]:
    return json.loads(blb.decode("utf-8"))


def _json_dict2blob(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _get_messages(cursor: sqlite3.Cursor, group_id: str) -> List[Dict[str, Any]]:
    cursor.execute("SELECT messages FROM session_store WHERE group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return _json_blob2dict(row[0])
    return []


def _save_messages(cursor: sqlite3.Cursor, group_id: str, messages: List[Dict[str, Any]]):
    blob = _json_dict2blob(messages)
    cursor.execute(
        "INSERT OR REPLACE INTO session_store (group_id, messages) VALUES (?, ?)",
        (group_id, blob),
    )


# ── 公开 API ─────────────────────────────────────────────

def get_messages(group_id: str) -> List[Dict[str, Any]]:
    """获取群聊会话的消息历史（原始 dict 列表）。"""
    init_table()
    with read_cursor() as cursor:
        return _get_messages(cursor, group_id)


def save_messages(group_id: str, messages: List[Dict[str, Any]]):
    """保存群聊会话的消息历史。"""
    init_table()
    with write_cursor() as cursor:
        _save_messages(cursor, group_id, messages)
