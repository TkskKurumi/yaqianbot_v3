import sqlite3
from yaqianbot.globals.g_paths import get_file_path
from threading import RLock
from contextlib import contextmanager
import sqlite3


LCK = RLock()

@contextmanager
def read_cursor():
    with LCK:
        conn = sqlite3.connect(get_file_path("db.sqlite3"), check_same_thread=False)
        try:
            yield conn.cursor()
        finally:
            conn.close()
@contextmanager
def write_cursor():
    with LCK:
        conn = sqlite3.connect(get_file_path("db.sqlite3"), check_same_thread=False)
        try:
            yield conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
