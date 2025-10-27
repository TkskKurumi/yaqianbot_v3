import inspect
import time
from functools import wraps
from threading import RLock

_CNT = {}
_RT  = {}
_LOCK = RLock()
def add_runtime(name, start, end):
    with _LOCK:
        _CNT[name] = _CNT.get(name, 0) + 1
        _RT[name] = _RT.get(name, 0) + end-start
def report_profile(prt=print):
    with _LOCK:
        if (not _RT):
            return
        items = sorted(_RT.items(), key=lambda x:x[-1]/_CNT[x[0]], reverse=True)
        items = items[:10]
        maxlen = len(max(items, key=lambda x:len(x[0]))[0])
        for name, rt in items:
            if (not rt):
                continue
            cnt = _CNT[name]
            rt = _RT[name]
            if (cnt>rt):
                speed_str = "%.1f runs/second"%(cnt/rt)
            else:
                speed_str = "%.1f seconds/run"%(rt/cnt)
            prt(name.rjust(maxlen, " "), ":", "%d times in %.2f seconds, %s"%(_CNT[name], _RT[name], speed_str))
                  
class Profiler:
    def __init__(self, name=None):
        self.name0 = name
        if (name is None):
            stack = inspect.stack()
            frame = stack[1]
            self.name1 = "%s:%s"%(frame.filename, frame.lineno)
        else:
            self.name1 = "no need"

    @property
    def name(self):
        return self.name0 or self.name1
    def __enter__(self):
        self.start = time.time()
    def __exit__(self, *args):
        add_runtime(self.name, self.start, time.time())
    def __call__(self, fn):
        name = self.name0 or fn.__name__ or self.name1
        @wraps(fn)
        def inner(*args, **kwargs):
            start = time.time()
            try:
                ret = fn(*args, **kwargs)
                end   = time.time()
                add_runtime(name, start, end)
                return ret
            except Exception as e:
                end   = time.time()
                add_runtime(name, start, end)
                raise e
        return inner
