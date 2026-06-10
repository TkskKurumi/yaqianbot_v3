"""SQLite 数据库连接管理。"""

from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from threading import RLock

from yaqianbot.globals.g_paths import get_file_path

LCK = RLock()
DB_PATH = get_file_path("vlm_bot", "db.sqlite3")


@contextmanager
def read_cursor():
    """只读游标上下文管理器。"""
    with LCK:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        try:
            yield conn.cursor()
        finally:
            conn.close()


@contextmanager
def write_cursor():
    """写入游标上下文管理器（自动 commit/rollback）。"""
    with LCK:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        try:
            yield conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
