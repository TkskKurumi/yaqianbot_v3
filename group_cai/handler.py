from yaqianbot.receiver import on_message, command, on_exception_send_sync, on_tome
from yaqianbot.globals.g_threading import threading_run
from yaqianbot.adapters.base_adapter.message import BaseMessage as YBaseMessage
from yaqianbot.adapters.base_adapter.mseg import MessageSegment as YMessageSegment
from yaqianbot.adapters.base_adapter.mseg import BaseImage as YBaseImage
from yaqianbot.adapters.base_adapter.mseg import BaseText as YBaseText
from yaqianbot.globals.g_cfg import get as get_cfg
from .group_sess import GroupSess
import random
import time
import traceback
from collections import defaultdict

WAIT_T = dict()
LAST_T = defaultdict(lambda:time.time())

def get_schedule_key(mes: YBaseMessage):
    if (get_cfg("message_schedule", "by_group", True)):
        return mes.sender.group_id
    return "happy"


def trigger_by_time(mes):
    global LAST_T
    key = get_schedule_key(mes)
    t = time.time()
    last_t = LAST_T[key]
    min_t = get_cfg("message_schedule", "trigger_sec_min", 30)
    max_t = get_cfg("message_schedule", "trigger_sec_max", 30)
    
    ratio = (t-last_t)/(max_t-min_t)
    min_prob = get_cfg("message_schedule", "trigger_prob_min", 0)
    max_prob = get_cfg("message_schedule", "trigger_prob_max", 1)
    prob = min_prob + ratio*(max_prob-min_prob)
    if (prob<min_prob):
        # elapse_t < min_t
        return False
    rnd = random.random()
    return rnd<prob
def trigger_by_kwd(mes: YBaseMessage):
    mes_repr = "".join(i.repr_text for i in mes.rich)
    prob = get_cfg("message_schedule", "trigger_kwd_prob", 0.1)
    for kwd in get_cfg("message_schedule", "trigger_kwd", ["菜包"]):
        if (kwd in mes_repr):
            if (random.random() < prob):
                return True
    return False
def wait_and_reply(mes: YBaseMessage):
    global WAIT_T, LAST_T
    gid = mes.sender.group_id
    key = get_schedule_key(mes)
    this_time = time.time()
    WAIT_T[key] = this_time
    wait_batch = get_cfg("message_schedule", "wait_batch_sec", 30)
    wait_ated  = get_cfg("message_schedule", "wait_ated_sec", wait_batch)
    if (mes.is_to_me):
        wait = wait_ated
    else:
        wait = wait_batch
    time.sleep(wait)
    if (WAIT_T[key] != this_time):
        print("new message comes")
        return
    else:
        print("is newest message")
    gsess = GroupSess.open(gid)
    with gsess.LOCK:
        trigger = mes.is_to_me
        if (not trigger):
            trigger = trigger_by_kwd(mes)
        if (not trigger):
            trigger = trigger_by_time(mes)
        if (not trigger):
            return
        gsess.response(mes)
        LAST_T[key] = time.time()
@on_message
@threading_run
@on_exception_send_sync
@command("#CBClear", kw_options=set())
def cb_clear(mes: YBaseMessage, *args, **kwargs):
    if (mes.sender.is_su):
        for gid in args:
            gsess = GroupSess.open(gid)
            with gsess.LOCK:
                lenth = len(gsess.msgs)
                gsess.msgs = []
                gsess.save_to_db()
            mes.sync_send([f"清除{lenth}条记录"])

@on_message
@threading_run
def cb_on_every_message(mes: YBaseMessage):
    try:
        if (not mes.rich):
            return
        gid = mes.sender.group_id

        gsess = GroupSess.open(gid)
        with gsess.LOCK:
            gsess.trim_length()
            gsess.add_user_ymes(mes)
        wait_and_reply(mes)
    except Exception as e0:
        traceback.print_exc()