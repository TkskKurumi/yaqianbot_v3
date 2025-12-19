from .db import read_cursor, write_cursor
from contextlib import contextmanager
import sqlite3
from typing import Optional, Union
from types import NoneType
import json, random
from math import gcd
from ..utils.number_theory import factorize
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
    print("update", image_id)
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
def get_img_info_recur(image_id, *args):
    with read_cursor() as cursor:
        _init_table(cursor)
        ret = _get_img_info_all(cursor, image_id)
        keys, dft = args[:-1], args[-1]
        for k in keys:            
            if (k not in ret):
                return args[-1]
            ret = ret[k]
        return ret
def set_img_info_recur(image_id, *args):
    with write_cursor() as cursor:
        _init_table(cursor)
        ret = _get_img_info_all(cursor, image_id)
        keys, value = args[:-1], args[-1]
        level = ret
        for k in keys[:-1]:
            if (k not in level):
                level[k] = {}
            level = level[k]
        level[keys[-1]] = value
        print(image_id, ret)
        _update_img(cursor, image_id, info=ret)

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
    
class Sampler:
    def __init__(self, seed=114514):
        self._state = seed
        self._ac_cache = {}
    def find_ac(self, m):
        if (m in self._ac_cache):
            return self._ac_cache[m]
        L = 1
        factors = factorize(m)
        for k, v in factors.items():
            if (k==2):
                if (v>1):
                    L *= 4
                else:
                    L *= 2
            else:
                L *= k
        a = L+1

        c = m//2
        while (gcd(c, m)!=1):
            c = c+1
        self._ac_cache[m] = (a, c)
        return (a, c)

    def _next_rid(self, cursor):
        cursor.execute("SELECT MIN(ROWID), MAX(ROWID) FROM image_info")
        min_id, max_id = cursor.fetchone()

        m = max_id-min_id
        if (m==0):
            raise Exception("db empty")
        a, c = self.find_ac(m)
        
        
        self._state = (self._state*a + c)%m
        return self._state + min_id
    def next_image(self):
        with read_cursor() as cursor:
            _init_table(cursor)
            for i in range(10):
                rid = self._next_rid(cursor)
                cursor.execute("SELECT image_id FROM image_info where ROWID >= ? ORDER BY ROWID LIMIT 1", (rid, ))
                row = cursor.fetchone()
                if (row is not None):
                    return row[0]
            raise Exception("cannot find image in db")