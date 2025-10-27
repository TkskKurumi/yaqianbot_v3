from .db import read_cursor, write_cursor
from contextlib import contextmanager
import sqlite3
from typing import Optional
import json
def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_info(
            video_id TEXT,
            data     BLOB,
            info     BLOB,
            PRIMARY KEY (video_id)
        );
    """)

def blob2dict(blb: bytes):
    return json.loads(blb.decode("utf-8"))
def dict2blob(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _get_vid_info_all(cursor: sqlite3.Cursor, video_id: str):
    cursor.execute("SELECT info from video_info WHERE video_id = ?", (video_id, ))
    row = cursor.fetchone()
    if (row is None):
        return {}
    else:
        if (row[0] is not None):
            return blob2dict(row[0])
        return {}
def _get_vid_data(cursor: sqlite3.Cursor, video_id: str):
    cursor.execute("SELECT data from video_info WHERE video_id = ?", (video_id, ))
    row = cursor.fetchone()
    if (row is None):
        return None
    else:
        return row[0]
    
def _get_vid_info(cursor: sqlite3.Cursor, video_id: str, key, default):
    return _get_vid_info_all(cursor, video_id).get(key, default)

def update_vid(video_id, data: Optional[bytes]=None, info: Optional[bytes]=None):
    with write_cursor() as cursor:
        _init_table(cursor)
        _update_vid(cursor, video_id, data, info)
def _update_vid(cursor: sqlite3.Cursor, video_id, data: Optional[bytes]=None, info: Optional[bytes]=None):
        if (data is None):
            data = _get_vid_data(cursor, video_id)
        if (info is None):
            info = _get_vid_info_all(cursor, video_id)
        if (not isinstance(info, bytes)):
            info = dict2blob(info)
        cursor.execute("INSERT OR REPLACE INTO video_info (video_id, data, info) VALUES (?, ?, ?)", (video_id, data, info))
        
def update_vid_info(video_id, upd):
    with write_cursor() as cursor:
        _init_table(cursor)

        info = _get_vid_info_all(cursor, video_id)
        info.update(upd)
        _update_vid(cursor, video_id, info=info)
def get_vid_info(video_id, key, default):
    with read_cursor() as cursor:
        _init_table(cursor)
        return _get_vid_info(cursor, video_id, key, default)

def get_vid_data(video_id):
    with read_cursor() as cursor:
        _init_table(cursor)
        return _get_vid_data(cursor, video_id)