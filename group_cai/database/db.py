import sqlite3
from yaqianbot.globals.g_paths import get_file_path
from threading import RLock
from contextlib import contextmanager
import sqlite3, json
from sqlite3 import Cursor


LCK = RLock()


def json_blob2dict(blb: bytes):
    return json.loads(blb.decode("utf-8"))
def json_dict2blob(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")

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
