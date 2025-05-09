from . import g_cfg
from os import path
import os
def get_rundir():
    ret = g_cfg.CFG.get("rundir", path.join(os.getcwd(), ".yaqianbot"))
    os.makedirs(ret, exist_ok=True)
    return ret

def get_dir(*args):
    ret = g_cfg.CFG.get("rundir", path.join(os.getcwd(), ".yaqianbot"))
    ret = path.join(ret, *args)
    os.makedirs(ret, exist_ok=True)
    return ret

def get_file_path(*args):
    ret = g_cfg.CFG.get("rundir", path.join(os.getcwd(), ".yaqianbot"))
    ret = path.join(ret, *args)
    os.makedirs(path.dirname(ret), exist_ok=True)
    return ret