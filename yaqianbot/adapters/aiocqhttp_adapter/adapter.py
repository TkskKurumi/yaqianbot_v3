import traceback
from ..base_adapter import BaseAdapter
from .message import CQMessage
from ...utils.debug_obj_schema import obj_schema_str
from aiocqhttp import Event, CQHttp
from functools import partial
from ...receiver.on_message import on_message_fn_aio
from ...globals.g_util import debug_if_cfg

async def message_receiver(cqbot: CQHttp, event: Event):
    try:
        debug_if_cfg(("debug", "cq_on_event"), obj_schema_str(event))
        await on_message_fn_aio(CQMessage.from_cq(cqbot, event))
        
    except Exception as e:
        traceback.print_exc()
class AIOCQHTTPAdapter(BaseAdapter):
    def __init__(self, cfg):
        self.port = cfg["port"]
        self.host = cfg["host"]
        cqbot = CQHttp()
        self.cqbot = cqbot
        self.cqbot.on_message(partial(message_receiver, self.cqbot))
    def get_async_start_stop(self):
        return (self.cqbot.run_task(host=self.host, port=self.port), None)

    def get_sync_start_stop(self):
        return None
