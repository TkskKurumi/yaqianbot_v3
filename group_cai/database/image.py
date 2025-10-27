from .db import read_cursor, write_cursor
from contextlib import contextmanager
import sqlite3
from typing import Optional, Union
from types import NoneType
import json, random

def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_info(
            image_id TEXT,
            data     BLOB,
            info     BLOB,
            PRIMARY KEY (image_id)
        );
    """)

def blob2dict(blb: bytes):
    return json.loads(blb.decode("utf-8"))
def dict2blob(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _get_img_info_all(cursor: sqlite3.Cursor, image_id: str):
    cursor.execute("SELECT info from image_info WHERE image_id = ?", (image_id, ))
    row = cursor.fetchone()
    if (row is None):
        return {}
    else:
        if (row[0] is not None):
            return blob2dict(row[0])
        return {}
def _get_img_data(cursor: sqlite3.Cursor, image_id: str):
    cursor.execute("SELECT data from image_info WHERE image_id = ?", (image_id, ))
    row = cursor.fetchone()
    if (row is None):
        return None
    else:
        return row[0]
    
def _get_img_info(cursor: sqlite3.Cursor, image_id: str, key, default):
    return _get_img_info_all(cursor, image_id).get(key, default)

def update_img(image_id, data: Optional[bytes]=None, info: Optional[bytes]=None):
    with write_cursor() as cursor:
        _init_table(cursor)
        _update_img(cursor, image_id, data, info)
def _update_img(cursor: sqlite3.Cursor, image_id, data: Optional[bytes]=None, info: Optional[bytes]=None):
        if (data is None):
            data = _get_img_data(cursor, image_id)
        if (info is None):
            info = _get_img_info_all(cursor, image_id)
        if (not isinstance(info, bytes)):
            info = dict2blob(info)
        cursor.execute("INSERT OR REPLACE INTO image_info (image_id, data, info) VALUES (?, ?, ?)", (image_id, data, info))
        
def update_img_info(image_id, upd):
    with write_cursor() as cursor:
        _init_table(cursor)

        info = _get_img_info_all(cursor, image_id)
        info.update(upd)
        _update_img(cursor, image_id, info=info)
def get_img_info(image_id, key, default):
    with read_cursor() as cursor:
        _init_table(cursor)
        return _get_img_info(cursor, image_id, key, default)

def get_img_data(image_id) -> Union[bytes, NoneType]:
    with read_cursor() as cursor:
        _init_table(cursor)
        return _get_img_data(cursor, image_id)
def rand_img():
    with read_cursor() as cursor:
        _init_table(cursor)
        cursor.execute("SELECT MIN(ROWID), MAX(ROWID) FROM image_info")
        min_id, max_id = cursor.fetchone()

        for i in range(10):
            rid = random.randint(min_id, max_id)
            cursor.execute("SELECT image_id FROM image_info where ROWID >= ? ORDER BY ROWID LIMIT 1", (rid, ))
            row = cursor.fetchone()
            if (row is not None):
                return row[0]
        
        raise Exception("Cannot rand from table")