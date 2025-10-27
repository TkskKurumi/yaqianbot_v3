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
last_t = time.time()
@on_message
@threading_run
def on_every_message(mes: YBaseMessage):
    try:
        global last_t
        if (not mes.rich):
            return
        # if (not mes.is_group):
        #     return
        gid = mes.sender.group_id
        uid = mes.sender.uid

        ok = True
        if (uid in ["402254524", "2235969249"]):
            ok = True
        if (not ok):
            return
        
        gsess = GroupSess.open(gid)
        with gsess.LOCK:
            gsess.trim_length()
            gsess.add_user_ymes(mes)
            

            ok = False
            if (mes.is_to_me):
                ok = True
            if (not ok):
                tm = time.time()-last_t
                tm_mn, tm_mx = get_cfg("reply_min_secs", 30), get_cfg("reply_max_secs", 300)
                tm_01 = (tm - tm_mn) / (tm_mx-tm_mn)
                tm_01 = max(min(tm_01, 1), 0)
                p_mn, p_mx = get_cfg("reply_min_prob", 0.1), get_cfg("reply_max_prob", 1)
                prob = p_mn + tm_01*(p_mx-p_mn)
                rnd = random.random()
                print("DEBUG: prob %.1f <=> %.1f rand"%(prob, rnd))
                if (rnd < prob):
                    ok = True
            if (not ok):
                p = get_cfg("reply_keyword_prob", 0.7)
                kwds = get_cfg("reply_keyword", [])

                if (isinstance(kwds, list)):
                    for k in kwds:
                        if (k in mes.text_for_command):
                            if (random.random()<p):
                                ok = True
            

            if (ok):
                print("ready to response")
                last_t = time.time()
                try:
                    gsess.response(mes)
                except Exception as e1:
                    traceback.print_exc()
    except Exception as e0:
        traceback.print_exc()