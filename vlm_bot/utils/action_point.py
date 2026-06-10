"""ActionPoint — 令牌桶限流器（按 group_id + section 区分）。

使用方式：
    from vlm_bot.utils.action_point import get_action_point

    with get_action_point(group_id, "sdcpp_img_gen", ap_max=100, ap_rec=0.004) as ap:
        if not ap.can_consume(50):
            wait = ap.wait_time(50)
            print(f"需要等待 {wait} 秒")
        ap.consume(50)
        # ... 执行操作 ...
    # 退出 context manager 时自动保存
"""

import json
import time
from contextlib import contextmanager
from threading import RLock
from typing import Optional

from ..database.db import read_cursor, write_cursor


# ──────────────────────────────────────────────
# 数据库
# ──────────────────────────────────────────────

_DB_TABLE = "action_point"


def _init_table(cursor):
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {_DB_TABLE}(
            key TEXT PRIMARY KEY,
            ap_last REAL,
            ts_last REAL
        )
    """)


def _load(cursor, key: str) -> Optional[dict]:
    cursor.execute(f"SELECT ap_last, ts_last FROM {_DB_TABLE} WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row is None:
        return None
    return {"ap_last": row[0], "ts_last": row[1]}


def _save(cursor, key: str, ap_last: float, ts_last: float):
    cursor.execute(
        f"INSERT OR REPLACE INTO {_DB_TABLE} (key, ap_last, ts_last) VALUES (?, ?, ?)",
        (key, ap_last, ts_last),
    )


# ──────────────────────────────────────────────
# 锁（按 key hash 分片）
# ──────────────────────────────────────────────

_NUM_LOCKS = 16
_LOCKS = [RLock() for _ in range(_NUM_LOCKS)]


def _get_lock(key: str):
    return _LOCKS[hash(key) % _NUM_LOCKS]


# ──────────────────────────────────────────────
# ActionPoint
# ──────────────────────────────────────────────


class ActionPoint:
    """令牌桶限流器。

    Parameters
    ----------
    group_id : str
        群 ID。
    section : str
        限流分区名（如 "sdcpp_img_gen"）。
    ap_max : float
        最大令牌数。
    ap_rec : float
        每秒恢复速率。
    """

    def __init__(self, group_id: str, section: str, ap_max: float, ap_rec: float):
        self.group_id = group_id
        self.section = section
        self.key = f"{group_id}:{section}"
        self.ap_max = ap_max
        self.ap_rec = ap_rec
        self.ap_last: float = ap_max
        self.ts_last: float = time.time()
        self._dirty = False

    def _load_from_db(self, cursor):
        row = _load(cursor, self.key)
        if row:
            self.ap_last = row["ap_last"]
            self.ts_last = row["ts_last"]

    def update(self) -> float:
        """根据时间恢复令牌，返回当前令牌数。"""
        elapsed = time.time() - self.ts_last
        if elapsed <= 0:
            return self.ap_last
        self.ap_last = min(self.ap_max, self.ap_last + elapsed * self.ap_rec)
        self.ts_last = time.time()
        return self.ap_last

    def can_consume(self, cost: float) -> bool:
        """检查是否有足够令牌。"""
        return self.update() >= cost

    def consume(self, cost: float) -> float:
        """消费令牌，返回剩余令牌数。不足则抛出 :class:`RateLimitError`。

        支持负值 cost 来返还令牌。
        """
        curr = self.update()
        if cost < 0:
            # 负值 = 返还
            self.ap_last -= cost  # 减去负值 = 增加
            self._dirty = True
            return self.ap_last
        if curr < cost:
            raise RateLimitError(
                group_id=self.group_id,
                section=self.section,
                cost=cost,
                available=curr,
                rec_speed=self.ap_rec,
                wait_time=(cost - curr) / self.ap_rec if self.ap_rec > 0 else float("inf"),
            )
        self.ap_last -= cost
        self._dirty = True
        return self.ap_last

    def wait_time(self, cost: float) -> float:
        """计算需要等待多少秒才能消费指定 cost。足够则返回 0。"""
        curr = self.update()
        if curr >= cost:
            return 0.0
        if self.ap_rec <= 0:
            return float("inf")
        return (cost - curr) / self.ap_rec

    def _save_if_dirty(self, cursor):
        if self._dirty:
            _save(cursor, self.key, self.ap_last, self.ts_last)
            self._dirty = False


class RateLimitError(Exception):
    """限流异常。"""

    def __init__(
        self,
        group_id: str,
        section: str,
        cost: float,
        available: float,
        rec_speed: float,
        wait_time: float,
    ):
        self.group_id = group_id
        self.section = section
        self.cost = cost
        self.available = available
        self.rec_speed = rec_speed
        self.wait_time = wait_time
        super().__init__(
            f"Rate limited: need {cost}, have {available:.1f}, "
            f"wait {wait_time:.0f}s"
        )


# ──────────────────────────────────────────────
# Context Manager
# ──────────────────────────────────────────────


@contextmanager
def get_action_point(group_id: str, section: str, ap_max: float, ap_rec: float):
    """获取 ActionPoint 的上下文管理器。

    进入时从 DB 加载，退出时自动保存（仅当有修改时）。
    同一 key 在同一时刻只有一个 context manager 能进入（锁保护）。

    Example
    -------
    >>> with get_action_point("123", "img_gen", 100, 0.01) as ap:
    ...     ap.consume(10)
    """
    lock = _get_lock(f"{group_id}:{section}")
    with lock:
        ap = ActionPoint(group_id, section, ap_max, ap_rec)
        with read_cursor() as cursor:
            _init_table(cursor)
            ap._load_from_db(cursor)
        try:
            yield ap
        finally:
            with write_cursor() as cursor:
                _init_table(cursor)
                ap._save_if_dirty(cursor)
