import threading
import yaml
import sys
import asyncio
import importlib
from .adapters.base_adapter import BaseAdapter
from .utils.debug_obj_schema import obj_schema_str
from .globals import g_cfg
import os

def _process_cfg_value(v):
    if (isinstance(v, str)):
        for i in range(10):
            chg = False
            for env_k, env_v in os.environ.items():
                findstr = "${%s}"%env_k
                if (findstr in v):
                    print(findstr, "->", env_v)
                    v = v.replace(findstr, env_v)
                    chg = True
            if (not chg):
                break
        return v
    elif (isinstance(v, dict)):
        return _process_cfg_dict(v)
    elif (isinstance(v, list)):
        return [_process_cfg_value(i) for i in v]
    else:
        return v

def _process_cfg_dict(obj):
    return {k: _process_cfg_value(v) for k, v in obj.items()}


def process_cfg(cfg):

    cfg = _process_cfg_dict(cfg)

    su = cfg.get("superusers", {})
    su = set(str(i) for i in su)
    cfg["superusers"] = su
    
    return cfg
def run():  
    cfg = sys.argv[-1]
    print(cfg)
    with open(cfg, "r", encoding="utf-8") as f:
        cfg_str = f.read()
    cfg = yaml.safe_load(cfg_str)
    cfg = process_cfg(cfg)
    g_cfg.CFG = cfg
    print(obj_schema_str(cfg))

    adapters = []
    end_fn_async = []
    start_fn_async = []
    start_fn_threading = []
    end_fn_threading = []

    for plg in cfg["plugins"]:
        if (isinstance(plg, str)):
            plg_module = importlib.import_module(plg)
        else:
            raise TypeError("config plugin type error %s"%type(plg))

    cfg_adapters = cfg.get("adapters", [])
    if (not cfg_adapters):
        print("No adapters")
        return

    for adapter_cfg in cfg_adapters:
        adapter_module = importlib.import_module(adapter_cfg["adapter"])
        # print("adapter_module", adapter_module)
        adapter_cls = adapter_module.Adapter
        adapter: BaseAdapter = adapter_cls(adapter_cfg["config"])
        aio_start_end = adapter.get_async_start_stop()
        if (aio_start_end is not None):
            s, e = aio_start_end
            start_fn_async.append(s)
            if (e is not None):
                end_fn_async.append(e)
        else:
            s, e = adapter.get_sync_start_stop()
            start_fn_threading.append(s)
            if (e is not None):
                end_fn_threading.append(e)
    


    start_fn_tasks = [threading.Thread(target=i) for i in start_fn_threading]
    for t in start_fn_tasks:
        t.start()
    
    async def run_aio():
        print("Running in loop", asyncio.get_event_loop())
        a_tasks = [asyncio.create_task(i) for i in start_fn_async]
        for i in a_tasks:
            await i
    
    asyncio.run(run_aio())
    # asyncio.run(s)
    
    end_fn_tasks = [threading.Thread(i) for i in end_fn_threading]
    for t in start_fn_tasks:
        t.join()
    for t in end_fn_tasks:
        t.join()
run()