from ..receiver import on_message, command
from ..adapters.base_adapter.message import BaseMessage
from PIL import Image
import numpy as np
from ..globals.g_threading import threading_run


@on_message
@command("/test")
def cmd_test(mes: BaseMessage, *args, **kwargs):
    print(mes, args, kwargs)
    arr = np.random.uniform(0, 255, (100, 100, 3)).astype(np.uint8)
    im = Image.fromarray(arr)
    mes.sync_send(["hello", im, str(mes.is_su)])