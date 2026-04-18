from yaqianbot.receiver import on_message, command, on_exception_send_sync, on_tome
from yaqianbot.globals.g_threading import threading_run
from yaqianbot.adapters.base_adapter.message import BaseMessage as YBaseMessage
from yaqianbot.adapters.base_adapter.mseg import MessageSegment as YMessageSegment
from yaqianbot.adapters.base_adapter.mseg import BaseImage as YBaseImage
from yaqianbot.adapters.base_adapter.mseg import BaseText as YBaseText
from .message.base_mes import MessageUser
from yaqianbot.globals.g_cfg import get as get_cfg
from .group_sess import GroupSess
from .group_sess import _trim_length as trim_msg_length
import random
import time
import traceback
from collections import defaultdict

SCHED_T = defaultdict(lambda:time.time())

def get_schedule_key(mes: YBaseMessage):
    return mes.sender.group_id


def trigger_by_time(mes):
    global SCHED_T
    key = get_schedule_key(mes)
    t = time.time()
    last_t = SCHED_T[key]
    min_t = get_cfg("message_schedule", "trigger_sec_min", 300)
    max_t = get_cfg("message_schedule", "trigger_sec_max", 600)
    
    ratio = (t-last_t-min_t)/(max_t-min_t)
    min_prob = get_cfg("message_schedule", "trigger_prob_min", 0)
    max_prob = get_cfg("message_schedule", "trigger_prob_max", 1)
    prob = min_prob + ratio*(max_prob-min_prob)
    print(f"key = {key}, last_t = {last_t}, current_t = {t}, elapse = {t-last_t}, min_t = {min_t}, max_t = {max_t}, prob = {prob}")
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
    global SCHED_T
    gid = mes.sender.group_id
    sched_key = get_schedule_key(mes)
    
    wait_batch = get_cfg("message_schedule", "wait_batch_sec", 30)
    wait_ated  = get_cfg("message_schedule", "wait_ated_sec", wait_batch)
    wait = wait_batch
    trigger = False
    if (not trigger):
        if (mes.is_to_me):
            trigger = True
            wait = wait_ated
            print("Trigger by ated")
    if (not trigger):
        trigger = trigger_by_kwd(mes)
        if (trigger):
            wait = wait_ated
            print("Trigger by keyword")
    if (not trigger):
        trigger = trigger_by_time(mes)
        if (trigger):
            wait = wait_batch
            print("Trigger by time")
    if (not trigger):
        print("No reply", gid)
        return
    

    OWN_SCHED_T = time.time() + wait
    print("Trigger", gid, f"in {OWN_SCHED_T-time.time():.1f} seconds")
    SCHED_T[sched_key] = OWN_SCHED_T
    time.sleep(max(OWN_SCHED_T-time.time(), 0.1))
    gsess = GroupSess.open(gid)
    with gsess.LOCK:
        if (SCHED_T[sched_key] == OWN_SCHED_T):
            try:
                gsess.response(mes)
            except Exception:
                pass
        

@on_message
@threading_run
@on_exception_send_sync
@command("#CBClear", kw_options={"-n"}, bool_options={"-a", "-o"})
def cb_clear(mes: YBaseMessage, *args, **kwargs):
    

    mes_buffer = []
    def trim_by_num(gid, msgs, n):
        nonlocal mes_buffer
        le0 = len(msgs)
        msgs = trim_msg_length(msgs, num=n)
        le1 = len(msgs)
        if (le0!=le1):
            mes_buffer.append(f"{gid}消息长度{le0}->{le1}")
        return msgs
    def trim_assistant(gid, msgs):
        le0 = len(msgs)
        remain = []
        for i in msgs:
            if (isinstance(i, MessageUser)):
                remain.append(i)
        msgs = remain
        le1 = len(msgs)
        if (le0!=le1):
            mes_buffer.append(f"{gid}消息长度{le0}->{le1}")
        return msgs
    if (mes.sender.is_su):
        gids = set(args)   
        if (kwargs.get("-o", False)):
            gids.update(GroupSess._opened.keys())
        for gid in gids:
            gsess = GroupSess.open(gid)
            with gsess.LOCK:
                print("n=", kwargs.get("-n", 999))
                gsess.msgs = trim_by_num(gid, gsess.msgs, n=int(kwargs.get("-n", 999)))
                if (kwargs.get("-a", False)):
                    gsess.msgs = trim_assistant(gid, gsess.msgs)
                gsess.save_to_db()
    if (mes_buffer):
        to_send = "\n".join(mes_buffer)
        if (len(to_send) > 256):
            to_send = to_send[:252] + "..."
        mes.sync_send(to_send)

@on_message
@threading_run
def cb_on_every_message(mes: YBaseMessage):
    try:
        if (not mes.rich):
            return
        gid = mes.sender.group_id

        gsess = GroupSess.open(gid)
        with gsess.LOCK:
            gsess.trim_length_auto()
            gsess.add_user_ymes(mes)
        wait_and_reply(mes)
    except Exception as e0:
        traceback.print_exc()