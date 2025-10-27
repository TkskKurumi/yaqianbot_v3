from ..adapters.base_adapter.message import BaseMessage
from ..utils.debug_obj_schema import obj_schema_str
from ..utils import argparse
from functools import wraps
import re, inspect
import asyncio
import traceback
from ..globals.g_threading import sync_to_aio
from ..globals.g_util import debug_if_cfg
ALL_RECEIVERS = {}

async def on_message_fn_aio(mes: BaseMessage):
    global ALL_RECEIVERS
    debug_if_cfg(("debug", "message_repr"), "".join(i.repr_text for i in mes.rich))
    tasks = []
    for name, fn in ALL_RECEIVERS.items():
        if (inspect.iscoroutinefunction(fn)):
            tasks.append(fn(mes))
        else:
            tasks.append(sync_to_aio(fn, mes))
    await asyncio.gather(*tasks)
        

def on_message(fn):
    global ALL_RECEIVERS
    print("register", fn)
    name = fn.__name__
    ALL_RECEIVERS[name] = fn
    return fn

def on_exception_send_sync(fn):
    @wraps(fn)
    def inner(mes):
        try:
            fn(mes)
        except Exception as e:
            traceback.print_exc()
            mes.sync_send("出现了谜之错误%s"%e)
    return inner

def on_tome(fn):
    @wraps(fn)
    def inner(mes: BaseMessage):
        print("on_tome", mes)
        if (mes.is_to_me):
            return fn(mes)
        else:
            print("DEBUG: not to me", mes.is_to_me)
    return inner

def is_su(fn):
    @wraps(fn)
    def inner(mes: BaseMessage):
        if (mes.is_su):
            return fn(mes)
        else:
            print("DEBUG: not to me", mes.is_to_me)
    return inner

def command(startswith, kw_options=None, list_options=None, bool_options=None):
    def wrapper(fn):
        @wraps(fn)
        def inner(mes: BaseMessage):
            t = mes.text_for_command.strip(" \n")
            matched = re.match(startswith, t)
            if (matched):
                prefix = matched.group()
                remain = t[len(prefix):]
                args, kwargs = argparse.parse(remain, kw_options, list_options, bool_options)
                result = fn(mes, *args, **kwargs)
                return result
            else:
                pass
            return None
        return inner
    return wrapper

