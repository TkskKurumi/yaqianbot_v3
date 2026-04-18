from ..database.db import read_cursor, write_cursor, json_blob2dict, json_dict2blob
from sqlite3 import Cursor
from threading import RLock, Lock
import time
from contextlib import contextmanager
from typing import Dict
from collections import defaultdict
def _init_db(cursor: Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_point(
            user_id TEXT,
            data BLOB,
            PRIMARY KEY (user_id)
        )
    """)

def _get_user_data(cursor, uid):
    cursor.execute("SELECT data from action_point WHERE user_id = ?", (uid, ))
    row = cursor.fetchone()
    if (row is None):
        return {}
    else:
        if (row[0] is not None):
            return json_blob2dict(row[0])
        return {}

class InsufficientCost(Exception):
    def __init__(self, user_id, section_name, cost, available, rec_speed):
        self.user_id = user_id
        self.section_name = section_name
        self.cost = cost
        self.available = available
        self.rec_speed = rec_speed
        self.rec_time = (cost-available)/rec_speed
    def __repr__(self):
        return (f"{self.__class__.__name__}("
                f"user_id={self.user_id}, "
                f"section_name={self.section_name}, "
                f"cost={self.cost}, "
                f"available={self.available}, "
                f"rec_speed={self.rec_speed}, "
                f"rec_time={self.rec_time}")
USER_LOCK = [RLock() for i in range(32)]
@contextmanager
def get_user_section(user_id, section_name, dft_max, dft_rec):
    lck = USER_LOCK[hash(user_id)%32]

    with lck:
        with read_cursor() as cursor:
            _init_db(cursor)
            data = _get_user_data(cursor, user_id)
            sd = data.get(section_name, {})
            usd = UserSectionData(user_id, section_name, sd, dft_max, dft_rec)
        try:
            yield usd
        finally:
            usd.write_db()


class UserSectionData:
    def __init__(self, user_id, section_name, section_dict: Dict[str, float], dft_max, dft_rec):
        self.user_id = user_id
        self.section_name = section_name
        self.ap_last = section_dict.get("ap_last", dft_max)
        self.ap_max  = section_dict.get("ap_max" , dft_max)
        self.ap_rec  = section_dict.get("ap_rec" , dft_rec)
        self.ts_last = section_dict.get("ts_last", time.time())
    def asdict(self):
        return {
            "ap_last": self.ap_last,
            "ap_max": self.ap_max,
            "ap_rec": self.ap_rec,
            "ts_last": self.ts_last
        }
    def update(self):
        ts_curr = time.time()
        recovered = (ts_curr-self.ts_last)*self.ap_rec
        if (self.ap_last >= self.ap_max):
            ap_curr = self.ap_last # allow overflow
        else:
            ap_curr = min(self.ap_max, self.ap_last + recovered)
        self.ap_last = ap_curr
        self.ts_last = ts_curr
        return self.ap_last
    def check_recovery_time(self, cost):
        curr = self.update()
        if (cost > curr):
            return (cost-curr)/self.ap_rec
        return 0
    def consume(self, cost, no_check=False):
        curr = self.update()
        if (cost>curr and not no_check):
            raise InsufficientCost(self.user_id, self.section_name, cost, curr, self.ap_rec)
        self.ap_last -= cost
    def write_db(self):
        with write_cursor() as cursor:
            _init_db(cursor)
            ud = _get_user_data(cursor, self.user_id)
            ud[self.section_name] = self.asdict()
            cursor.execute("INSERT OR REPLACE INTO action_point (user_id, data) VALUES (?, ?)", (self.user_id, json_dict2blob(ud)))
    

    
        