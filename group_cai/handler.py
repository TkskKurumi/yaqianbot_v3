from yaqianbot.receiver import on_message, command, on_exception_send_sync, on_tome
from yaqianbot.adapters.base_adapter.message import BaseMessage as YBaseMessage
from yaqianbot.adapters.base_adapter.mseg import MessageSegment as YMessageSegment
from yaqianbot.adapters.base_adapter.mseg import BaseImage as YBaseImage
from yaqianbot.adapters.base_adapter.mseg import BaseText as YBaseText
from yaqianbot.globals.g_cfg import get as get_cfg
from .group_sess import GroupSess
import random
import time
last_t = time.time()
@on_message
def on_every_message(mes: YBaseMessage):
    global last_t

    if (not mes.rich):
        return

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
        else:
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

        if (ok):
            last_t = time.time()
            gsess.response(mes)
