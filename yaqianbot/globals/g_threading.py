from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from asyncio import events
import contextvars
import functools

pool = ThreadPoolExecutor(max_workers=128)

def threading_run(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        task = pool.submit(fn, *args, **kwargs)
        return task
    return inner


async def sync_to_aio(func, /, *args, **kwargs):
    loop = events.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    return await loop.run_in_executor(pool, func_call)