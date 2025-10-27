from .g_cfg import get as get_cfg
from functools import wraps, partial
import traceback
def debug_if_cfg(cfg_path, *args, **kwargs):
    if (get_cfg(*cfg_path, False)):
        print(*args, **kwargs)
    else:
        print(cfg_path, get_cfg(*cfg_path, False))

def debug_ret(cfg_path, print_exc=False):
    dbg = partial(debug_if_cfg, cfg_path)
    def deco(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            
            argstr = ", ".join(repr(i) for i in args)
            kwagstr = ", ".join("%s=%s"%(k, repr(v)) for k, v in kwargs)
            dbg(f"{fn.__name__}({argstr}, {kwagstr})")
            try:
                ret = fn(*args, **kwargs)
                dbg(f"{fn.__name__}({argstr}, {kwagstr}) = {ret}")
                return ret
            except Exception as e:
                dbg(f"{fn.__name__}({argstr}, {kwagstr}) exc", repr(e))
                if (print_exc):
                    dbg(traceback.format_exc())
                raise e
        return inner
    return deco

