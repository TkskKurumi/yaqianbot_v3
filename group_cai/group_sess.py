from yaqianbot.receiver import on_message, command, on_exception_send_sync, on_tome
from yaqianbot.adapters.base_adapter.message import BaseMessage as YBaseMessage
from yaqianbot.adapters.base_adapter.mseg import MessageSegment as YMessageSegment
from yaqianbot.adapters.base_adapter.mseg import BaseImage as YBaseImage
from yaqianbot.adapters.base_adapter.mseg import BaseText as YBaseText
from yaqianbot.adapters.base_adapter.mseg import BaseVideo as YBaseVideo
from yaqianbot.globals.g_cfg import get as get_cfg
from yaqianbot.globals import g_paths
from .message.mseg_img import MSEGImage
from .message.mseg_vid import MSEGVideo
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
import json, re
import traceback
from .system_prompt import SYS_PROMPT
from threading import RLock
import sqlite3
from .database.db import read_cursor, write_cursor
from yaqianbot.utils.debug_obj_schema import obj_schema_str
from .external_tools.tool_call import add_all_tool
from yaqianbot.globals.g_util import debug_ret
from .image_search_db import index as image_search_index

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

@debug_ret(("debug", "ymes2mes"), print_exc=True)
def ymes2mes(ymes: YBaseMessage):
    ycontent: List[YMessageSegment] = ymes.rich
    content = []
    for mseg in ycontent:
        if (isinstance(mseg, YBaseImage)):
            mseg_im = MSEGImage(base_img=mseg)
            content.append(mseg_im)
            try:
                mseg_im.save_data_to_db()
                image_search_index.add_image(mseg_im.image_id)
            except Exception as e:
                traceback.print_exc()
        elif (isinstance(mseg, YBaseText)):
            content.append(MSEGText(mseg.txt))
        elif (isinstance(mseg, YBaseVideo)):
            try:
                v = mseg.get_saved_file()
                content.append(MSEGVideo(base_vid=mseg))
            except Exception as e:
                content.append(MSEGRecvAny(repr="[视频文件获取失败]"))
                print(e)
        else:
            content.append(MSEGRecvAny(mseg.repr_text))
    optional_info = {}
    try:
        optional_info["role"] = ymes.sender.group_privilege
    except Exception as e:
        optional_info["role"] = "UNKNOWN"
        traceback.print_exc()
        print(e)
    optional_info["gender"] = ymes.sender.gender_str
    optional_info["self_id"] = ymes.self_id
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

def try_find_error_message(msgs, fmt_exc):
    idxs = re.findall(r"messages\[(\d+)\]", fmt_exc)
    if (idxs):
        idx = int(idxs[0])
        return msgs[int(idx)]
    return None


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

    def __init__(self, gid, msgs: List[Message]):
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
                if (get_cfg("debug", "dump_ds_msg", False)):
                    dump_mes = SYSTEM_MES+[i.to_deepseek() for i in msgs]
                    outfile = g_paths.get_file_path("debug", "to_deepseek", f"{mes.sender.group_id}.json")
                    with open(outfile, "w", encoding="utf-8") as f:
                        json.dump(dump_mes, f, ensure_ascii=False)
                    print("debug to deepseek json", outfile)
                try:
                    resp = ds_client.chat.completions.create(
                        messages=SYSTEM_MES+[i.to_deepseek() for i in msgs],
                        model=get_cfg("deepseek_chat", "model", "deepseek-chat"),
                        stream=False,
                        tool_choice="auto",
                        tools=function_ls,
                        max_completion_tokens=8192
                    )
                except Exception as e:
                    err_mes = try_find_error_message(SYSTEM_MES+msgs, traceback.format_exc())
                    if (err_mes):
                        print("Error message", err_mes, err_mes.to_deepseek())
                    raise e
                return resp, resp.choices[0].message
            resp, resp_msg = create_resp()
            retry = 5
            retry_tool = 2
            while (True):
                if (getattr(resp_msg, "tool_calls", [])):
                    tool_calls = resp_msg.tool_calls
                    for call in tool_calls:
                        fname = call.function.name
                        fargs = json.loads(call.function.arguments)
                        if (retry_tool <= 0):
                            fret = json.dumps({"status": "fail", "reason": "tool call retry count exceed"})
                        else:
                            try:
                                fret = function_map[fname](**fargs)
                            except Exception as e:
                                fret = json.dumps({"status": "fail", "reason": "tool call internal error "+repr(e)})

                        msgs.append(MessageTool(openai_obj_2_dict(resp_msg)))
                        msgs.append(MessageTool({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": fname, 
                            "content": fret
                        }))
                    resp, resp_msg = create_resp()
                    retry_tool -= 1
                else:
                    try:
                        content_mseg, content_send = deepseek_resp_to_send(mes, resp_msg, resp_msg.content)
                        if (get_cfg("dry_run", False)):
                            print("=== DRY SEND ===", content_send)
                        else:
                            mes.sync_send(content_send)
                    except Exception as e:
                        if (retry>=0):
                            # try:
                            #     fmt_exc = traceback.format_exc()
                            #     if (re.findall(r"messages\[\d+\]", fmt_exc)):
                            #         idx = int(re.findall(r"messages\[(\d+)\]", fmt_exc)[0])
                            #         mes = msgs[idx]
                            #         print("bad message", mes)
                            # except Exception as e1:
                            #     print(repr(e1))

                            print("==== RETEY ===", retry, e)
                            retry -= 1
                            resp, resp_msg = create_resp()
                            continue
                        else:
                            print(obj_schema_str(mes))
                            raise e
                    msgs.append(MessageAssistant(content_mseg))
                    break
            self.msgs = msgs
            self.save_to_db()



def deepseek_resp_to_send(ymes: YBaseImage, resp_msg, resp_content: str):
    try:
        content_dict: List[Dict] = json.loads(resp_content)
    except Exception as e:
        traceback.print_exc()
        print(resp_content, resp_msg)
        raise e
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