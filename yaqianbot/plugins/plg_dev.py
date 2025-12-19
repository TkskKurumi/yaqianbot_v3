from ..receiver import on_message, command, is_su, on_exception_send_sync
from ..adapters.base_adapter.message import BaseMessage
from PIL import Image
import numpy as np
import json
from ..globals.g_threading import threading_run
from ..utils.debug_obj_schema import obj_schema_str




@on_message
@is_su
@on_exception_send_sync
@command("#exec")
def cmd_exec(mes: BaseMessage, *args, **kwargs):
    contents = mes.text_for_command
    exec(contents)


        
    