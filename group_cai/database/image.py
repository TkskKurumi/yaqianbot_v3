from .db import read_cursor, write_cursor
from contextlib import contextmanager
import sqlite3
def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_info(
            image_id TEXT,
            desc     TEXT,
            data     BLOB,
            PRIMARY KEY (image_id)
        );
    """)


def _get_image_data(image_id, cursor):
    cursor.execute("SELECT data from image_info WHERE image_id = ?", (image_id, ))
    result = cursor.fetchone()
    if (result is None):
        return None
    else:
        return result[0]
def get_image_data(image_id):
    with read_cursor() as cursor:
        _init_table(cursor)
        return _get_image_data(image_id, cursor)


def _get_image_desc(image_id, cursor):
    cursor.execute("SELECT desc from image_info WHERE image_id = ?", (image_id, ))
    result = cursor.fetchone()
    if (result is None):
        return None
    else:
        return result[0]
def get_image_desc(image_id):
    with read_cursor() as cursor:
        _init_table(cursor)
        return _get_image_desc(image_id, cursor)


def update_image(image_id, data=None, desc=None):
    with write_cursor() as cursor:
        _init_table(cursor)
        if (data is None):
            data = _get_image_data(image_id, cursor)
        if (desc is None):
            desc = _get_image_desc(image_id, cursor)
            
        cursor.execute("""
            INSERT OR REPLACE INTO image_info (image_id, desc, data)
            VALUES (?, ?, ?)
        """, (image_id, desc, data))
        