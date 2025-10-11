from yaqianbot.receiver import on_message, command, on_exception_send_sync, on_tome
from yaqianbot.adapters.base_adapter.message import BaseMessage as YBaseMessage
from yaqianbot.adapters.base_adapter.mseg import MessageSegment as YMessageSegment
from yaqianbot.adapters.base_adapter.mseg import BaseImage as YBaseImage
from yaqianbot.adapters.base_adapter.mseg import BaseText as YBaseText
from yaqianbot.globals.g_cfg import get as get_cfg
from .message.mseg_img import MSEGImage
from .message.mseg_txt import MSEGText
from .message.mseg_any import MSEGRecvAny
from .message.base_mes import MessageUser, Message, MessageTool, MessageAssistant
from .message.base_mes import mes_from_db
from .message.base_message_segment import MessageSegment
from .message.base_message_segment import from_db as mseg_from_db
from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict
from openai import OpenAI
import json
from .system_prompt import SYS_PROMPT
from threading import RLock
import sqlite3
from .database.db import read_cursor, write_cursor
from yaqianbot.utils.debug_obj_schema import obj_schema_str
from .external_tools.tool_call import add_all_tool


def _init_table(cursor: sqlite3.Cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_session(
            group_id TEXT,
            messages BLOB,
            PRIMARY KEY (group_id)
        )
    """)
def _db_get_messages(group_id, cursor: sqlite3.Cursor):
    cursor.execute("SELECT messages from group_session WHERE group_id = ?", (group_id, ))
    result = cursor.fetchone()
    if (result is None):
        return []
    else:
        blb = result[0]
        msgs = json.loads(blb.decode("utf-8"))
        return [mes_from_db(i) for i in msgs]


def ymes2mes(ymes: YBaseMessage):
    ycontent: List[YMessageSegment] = ymes.rich
    content = []
    for mseg in ycontent:
        if (isinstance(mseg, YBaseImage)):
            content.append(MSEGImage(base_img=mseg))
        elif (isinstance(mseg, YBaseText)):
            content.append(MSEGText(mseg.txt))
        else:
            content.append(MSEGRecvAny(mseg.repr_text))
    optional_info = {}
    optional_info["role"] = ymes.sender.group_privilege
    optional_info["gender"] = ymes.sender.gender_str
    return MessageUser(
        username=ymes.sender.username,
        userid=ymes.sender.uid,
        date=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
        content=content,
        optional=optional_info
    )


ds_client = OpenAI(api_key=get_cfg("deepseek_chat", "api_key", ""), base_url=get_cfg("deepseek_chat", "base_url", "https://api.deepseek.com"))
G_LOCK_N = 16
G_LOCKS = [RLock() for i in range(G_LOCK_N)]
LCK = RLock()

SYSTEM_MES = [{"role": "system", "content": SYS_PROMPT}]

def openai_obj_2_dict(obj):
    def _is_val_builtin(obj):
        if (isinstance(obj, str)):
            return True
        elif (isinstance(obj, int)):
            return True
        else:
            return False
    
    if (isinstance(obj, dict)):
        return {k: openai_obj_2_dict(v) for k, v in obj.items()}
    elif (isinstance(obj, list)):
        return [openai_obj_2_dict(i) for i in obj]
    elif (isinstance(obj, tuple)):
        return tuple(openai_obj_2_dict(i) for i in obj)
    elif (isinstance(obj, int) or isinstance(obj, str)):
        return obj
    elif (obj is None):
        return obj
    else:
        return openai_obj_2_dict(obj.__dict__)

class GroupSess:
    _opened = {}
    @classmethod
    def open(cls, group_id):
        with LCK:
            if (group_id in cls._opened):
                return cls._opened[group_id]
            with read_cursor() as cursor:
                _init_table(cursor)
                msgs = _db_get_messages(group_id, cursor)
            ret = cls(group_id, msgs)
            cls._opened[group_id] = ret
            return ret

    def __init__(self, gid, msgs: List[MessageSegment]):
        self.LOCK = G_LOCKS[hash(gid)%G_LOCK_N]
        self.msgs = msgs
        self.group_id = gid
    
    def add_user_ymes(self, ymes: YBaseMessage):
        with self.LOCK:
            mes = ymes2mes(ymes)
            self.msgs.append(mes)
            self.save_to_db()
    def save_to_db(self):
        with self.LOCK:
            with write_cursor() as cursor:
                _init_table(cursor)
                msgs = [i.to_db() for i in self.msgs]
                msg_json = json.dumps(msgs, ensure_ascii=False)
                msg_blob = msg_json.encode("utf-8")
                cursor.execute("""
                    INSERT OR REPLACE INTO group_session (group_id, messages) VALUES (?, ?)
                """, (self.group_id, msg_blob))
        
    def trim_length(self):
        with self.LOCK:
            mx = get_cfg("mes_cnt_max", 384)
            mn = get_cfg("mes_cnt_pref", 128)
            if (len(self.msgs) > mx):
                self.msgs = self.msgs[-mn:]
                rev = self.msgs[::-1]
                while (rev and not isinstance(rev[-1], MessageUser)):
                    rev.pop()
                self.msgs = rev[::-1]
                self.save_to_db()


    def response(self, mes: YBaseMessage):
        with self.LOCK:
            msgs = list(self.msgs)

            function_ls = []
            function_map = {}
            # TODO: add function calls
            add_all_tool(mes, function_ls, function_map)
            def create_resp():
                nonlocal msgs
                resp = ds_client.chat.completions.create(
                    messages=SYSTEM_MES+[i.to_deepseek() for i in msgs],
                    model=get_cfg("deepseek_chat", "model", "deepseek-chat"),
                    stream=False,
                    tool_choice="auto",
                    tools=function_ls
                )
                return resp, resp.choices[0].message
            resp, resp_msg = create_resp()
            retry = 5
            while (True):
                if (getattr(resp, "tool_calls", [])):
                    tool_calls = resp_msg.tool_calls
                    for call in tool_calls:
                        fname = call.function.name
                        fargs = json.loads(call.function.arguments)
                        fret  = function_map[fname](**fargs)
                        # keep it raw
                        msgs.append(MessageTool(openai_obj_2_dict(resp_msg)))
                        msgs.append(MessageTool({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": fname, 
                            "content": fret
                        }))
                    resp = ds_client.chat.completions.create(
                        messages=SYSTEM_MES+[i.to_deepseek() for i in msgs],
                        model=get_cfg("deepseek_chat", "model", "deepseek-chat"),
                        stream=False
                    )
                    resp_msg = resp.choices[0].message
                else:
                    try:
                        content_mseg, content_send = deepseek_resp_to_send(mes, resp_msg.content)
                        if (get_cfg("dry_run", False)):
                            print("=== DRY SEND ===", content_send)
                        else:
                            mes.sync_send(content_send)
                    except Exception as e:
                        if (retry>=0):
                            print("==== RETEY ===", retry, e)
                            retry -= 1
                            resp, resp_msg = create_resp()
                            continue
                        else:
                            print(obj_schema_str(mes))
                            raise e
                    msgs.append(MessageAssistant(content_mseg))
                    break
            self.msgs = msgs[1:]
            self.save_to_db()



def deepseek_resp_to_send(ymes: YBaseImage, resp_content: str):
    content_dict: List[Dict] = json.loads(resp_content)
    content_mseg: List[MessageSegment] = [mseg_from_db(i) for i in content_dict]
    for mseg in content_mseg:
        if (isinstance(mseg, MSEGImage) and mseg.get_pil() is None):
            print(mseg.image_id)
            raise ValueError("invalid send image %s"%(mseg.image_id))
    content_send: List[Any] = []
    for i in content_mseg:
        if (i.to_send() is None):
            raise ValueError("MSEG to_send error %s"%i)
        else:
            content_send.append(i.to_send())
    return content_mseg, content_send