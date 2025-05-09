from ..adapters.base_adapter.message import BaseMessage
from ..utils.debug_obj_schema import obj_schema_str
from ..utils import argparse
from functools import wraps
import re, inspect
import asyncio
from ..globals.g_threading import sync_to_aio
ALL_RECEIVERS = {}

async def on_message_fn_aio(mes: BaseMessage):
    global ALL_RECEIVERS
    print("DEBUG", obj_schema_str(mes))
    print("all receivers", ALL_RECEIVERS)
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

def command(startswith, kw_options=None, list_options=None, bool_options=None):
    def wrapper(fn):
        @wraps(fn)
        def inner(mes: BaseMessage):
            t = mes.text_for_command.strip(" \n")
            matched = re.match(startswith, t)
            if (matched):
                print("DEBUG: match cmd start", startswith, t)
                prefix = matched.group()
                remain = t[len(prefix):]
                args, kwargs = argparse.parse(remain, kw_options, list_options, bool_options)
                result = fn(mes, *args, **kwargs)
                return result
            else:
                print("DEBUG: match cmd fail ", startswith, t)
            return None
        return inner
    return wrapper

