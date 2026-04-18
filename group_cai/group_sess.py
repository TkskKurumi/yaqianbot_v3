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
from openai import NOT_GIVEN
from openai.types.chat import ChatCompletion
import json, re
import traceback, tqdm
import ast, time
from os import path
from .system_prompt import SYS_PROMPT
from threading import RLock
import sqlite3
from .database.db import read_cursor, write_cursor
from yaqianbot.utils.debug_obj_schema import obj_schema_str
from .external_tools.tool_call import add_all_tool
from yaqianbot.globals.g_util import debug_ret
from .image_search_db import index as image_search_index
from typing import Tuple
from openai import BadRequestError

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
GLOBAL_LOCK = RLock()
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
        date=datetime.now().strftime("%Y-%m-%d %A %H-%M-%S"),
        content=content,
        optional=optional_info
    )


ds_client = OpenAI(api_key=get_cfg("deepseek_chat", "api_key", ""), base_url=get_cfg("deepseek_chat", "base_url", "https://api.deepseek.com"), timeout=600)
G_LOCK_N = 16
# G_LOCKS = [RLock() for i in range(G_LOCK_N)]
LOCK_POOL = defaultdict(lambda:RLock())
LCK = RLock()

SYSTEM_MES = [{"role": "system", "content": SYS_PROMPT}]

def tool_ret2deepseek(obj):
    if (isinstance(obj, str)):
        return obj
    if (isinstance(obj, dict)):
        # TODO: implement more auto convert like image
        return json.dumps(obj, ensure_ascii=False)
    return obj

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

def static_route(provider, model, **kwargs):
    try:
        if (not get_cfg("debug", "static_route", False)):
            return
        if (provider is None):
            return
        if (model is None):
            return
        with GLOBAL_LOCK:
            pth = g_paths.get_file_path("debug", "route.json")
            if (path.exists(pth)):
                with open(pth, "r", encoding="utf-8") as f:
                    j = json.load(f)    
            else:
                j = {}
            model_name = f"{provider}/{model}"
            j_model = j.get(model_name, {})
            for k, v in kwargs.items():
                if (isinstance(v, (int, float))):
                    j_k = j_model.get(k, {})
                    if (not isinstance(j_k, dict)):
                        j_k = {}
                    j_k["cnt"] = j_k.get("cnt", 0) + 1
                    j_k["sum"] = j_k.get("sum", 0) + v
                    j_k["avg"] = j_k["sum"]/j_k["cnt"]
                    j_model[k] = j_k
                else:
                    j_model[k] = v
            j[model_name] = j_model

            for k in kwargs:
                models = []
                for m in j:
                    if (k in j[m] and "avg" in j[m][k]):
                        models.append((j[m][k]["avg"], j[m][k]["cnt"], m))
                print(k, sorted(models, reverse=True))


            with open(pth, "w", encoding="utf-8") as f:
                json.dump(j, f)
    except Exception:
        traceback.print_exc()
def _trim_length(msgs, num=None, ratio=None):
    if (ratio is not None):
        num = int(len(msgs)*ratio)
    elif (num is None):
        num = int(len(msgs)*0.5)
    start = max(len(msgs)-num, 0)
    
    while (start<len(msgs)):
        if (isinstance(msgs[start], MessageUser)):
            break
        start += 1
    return msgs[start:]
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
        # self.LOCK = G_LOCKS[hash(gid)%G_LOCK_N]
        self.LOCK = LOCK_POOL[hash(gid)%get_cfg("group_lock_num", 32)]
        self.msgs = msgs
        self.group_id = gid
    
    def add_user_ymes(self, ymes: YBaseMessage):
        with self.LOCK:
            mes = ymes2mes(ymes)
            try:
                to_db = mes.to_db()
            except Exception:
                traceback.print_exc()
                print("mes invalid", self.group_id)
                return
            self.msgs.append(mes)
            try:
                self.save_to_db()
            except Exception as e:
                traceback.print_exc()
                print("group mes invalid", self.group_id)
                raise e
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
    


    def trim_length(self, num=None, ratio=None):
        with self.LOCK:
            self.msgs = _trim_length(self.msgs, num=num, ratio=ratio)
            self.save_to_db()

    def trim_length_auto(self):
        with self.LOCK:
            mx = get_cfg("mes_cnt_max", 384)
            mn = get_cfg("mes_cnt_pref", 128)
            if (len(self.msgs) > mx):
    
                self.msgs = _trim_length(self.msgs, num=mn)
                self.save_to_db()


    def response(self, mes: YBaseMessage):
        with self.LOCK:
            msgs = list(self.msgs)

            function_ls = []
            function_map = {}
            add_all_tool(mes, function_ls, function_map)
            print("available tools: ", function_map.keys())
            retry_tool = 3

            route_provider = None
            route_model = None

            top_p = get_cfg("deepseek_chat", "top_p_initial", 0.5)
            temperature = get_cfg("deepseek_chat", "temperature_initial", 1)
            @debug_ret(("debug", "deepseek_create_resp"), print_exc=True)
            def create_resp():
                nonlocal msgs, retry_tool, route_provider, route_model, top_p, temperature
                if (get_cfg("debug", "show_to_deepseek_progress", False)):
                    it = tqdm.tqdm(msgs, desc=f"processing msg history of {self.group_id}")
                else:
                    it = msgs
                to_deepseek = SYSTEM_MES + [i.to_deepseek() for i in it]
                if (get_cfg("debug", "dump_ds_msg", False)):
                    dump_mes = to_deepseek
                    outfile = g_paths.get_file_path("debug", "to_deepseek", f"{mes.sender.group_id}.json")
                    with open(outfile, "w", encoding="utf-8") as f:
                        json.dump(dump_mes, f, ensure_ascii=False)
                    print("debug to deepseek json", outfile)
                try:
                    if (retry_tool>=0 and function_ls):
                        tool_choice="auto"
                    else:
                        tool_choice="none"
                    kwa = get_cfg("deepseek_chat", "extra_kwargs", {})
                    if (kwa is None):
                        kwa = {}
                    max_completion_tokens = get_cfg("deepseek_chat", "max_completion_tokens", 2048)
                    tokens_limit = get_cfg("mes_tokens_max", None)
                    tokens_cut = get_cfg("mes_tokens_cut", None)
                    resp: ChatCompletion = ds_client.chat.completions.create(
                        messages=to_deepseek,
                        model=get_cfg("deepseek_chat", "model", "deepseek-chat"),
                        stream=False,
                        tool_choice=tool_choice,
                        tools=function_ls,
                        max_completion_tokens=max_completion_tokens,
                        top_p=top_p,
                        temperature=temperature,
                        **kwa
                    )
                    resp_msg = resp.choices[0]
                    tokens_used = resp.usage.total_tokens
                    tokens_cmpl = resp.usage.completion_tokens
                    tokens_prpt = resp.usage.total_tokens - resp.usage.completion_tokens
                    if (resp_msg.finish_reason == "length" and resp.usage.completion_tokens<max_completion_tokens):
                        raise Exception(f"Completion with {tokens_cmpl} hit model capacity {tokens_used} with prompted {tokens_prpt}")
                    
                    route_provider = getattr(resp, "provider", None)
                    route_model = getattr(resp, "model", None)

                    print(f"Response for {self.group_id} created\n"
                          f"- Tokens Total/Completion: {tokens_used}/{tokens_cmpl}\n"
                          f"- Reply Rounds           : {sum(isinstance(i, MessageAssistant) for i in msgs)}\n"
                          f"- Stop Reason            : {resp_msg.finish_reason}\n"
                          f"- Provider / Model       : {route_provider} / {route_model}\n"
                          f"- KWA:                   : {kwa}"
                          )
                    # print(f"Response for {self.group_id} created with {tokens_used}/{tokens_cmpl} tokens for reason '{resp_msg.finish_reason}', provider/model: {route_provider}/{route_model}, extra_kwa: {kwa}")
                    reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
                    print(f"Reasoning {reasoning} Content {resp.choices[0].message.content}")
                    if (not resp_msg.message.content and not getattr(resp_msg.message, "tool_calls", [])):
                        raise Exception(f"Response is empty, maybe thinking hits max cmpl tokens")
                    
                    if (tokens_limit is not None):
                        if (tokens_used > tokens_limit):
                            if (tokens_cut is None):
                                ratio = 0.33
                            else:
                                ratio = tokens_cut/tokens_used
                            len0 = len(msgs)
                            msgs = _trim_length(msgs, ratio=ratio)
                            print("trimmed message %d -> %d"%(len0, len(msgs)))
                except Exception as e:
                    print("failing", repr(e))
                    err_mes = try_find_error_message(SYSTEM_MES+msgs, traceback.format_exc())
                    if (err_mes):
                        print("Error message", err_mes, err_mes.to_deepseek())
                        print("Error message", err_mes, err_mes.to_db())
                    ratio = None
                    # pttn = r"maximum context length is (\d+) tokens. However, you requested (\d+) tokens"
                    # if (ratio is None and re.findall(pttn, repr(e))):
                    #     lim, req = [int(i) for i in next(iter(re.findall(pttn, repr(e))))]
                    #     lim = min(lim, get_cfg("mes_tokens_cut", lim))
                    #     ratio = int(lim)/int(req)
                    # pttn = r"request \((\d+) tokens.*xceeds the available context size \((\d+) tokens"
                    # if (ratio is None and re.findall(pttn, repr(e))):
                    #     req, lim = next(iter(re.findall(pttn, repr(e))))
                    #     ratio = int(lim)/int(req)
                    # if (ratio is None and ("the request exceeds the available context size" in repr(e))):
                    #     ratio = 0.5
                    # pttn = r"Completion with (\d+) hit model capacity (\d+) with prompted (\d+)"
                    # if (ratio is None and re.findall(pttn, repr(e))):
                    #     cmpl, capa, prpt = [int(i) for i in next(iter(re.findall(pttn, repr(e))))]
                    #     ratio = 1-cmpl/prpt # make space for 1x cmpl

                    ctx_lim, ctx_req = None, None
                    pttn = r"request \((\d+) tokens\) exceeds the available context size \((\d+) tokens\)"
                    for req, lim in re.findall(pttn, repr(e)):
                        ctx_lim = int(lim)
                        ctx_req = int(req)
                    pttn = r"Completion with (\d+) hit model capacity (\d+) with prompted (\d+)"
                    for cmpl, capa, prmp in re.findall(pttn, repr(e)):
                        ctx_lim = int(capa)
                        ctx_req = ctx_lim + int(cmpl) # assuming another 1x cmpl to complete


                    if (ctx_lim and ctx_req):
                        if (get_cfg("mes_tokens_cut", None) is not None):
                            # if confirmed ctx is too long, requirement is exceeding limit
                            # donot cut just around the limit, cut lower than limit, leave space for incoming future message to reuse prefix cache a bit
                            ctx_lim = min(ctx_lim, get_cfg("mes_tokens_cut", None))
                        ratio = ctx_lim/ctx_req
                        print(f"ctx-lim = {ctx_lim}, ctx-required = {ctx_req}")
                    # if (ratio is not None):
                    #     if (tokens_limit and tokens_cut):   
                    #         ratio = min(tokens_cut/tokens_limit, ratio)

                    if (ratio is not None):
                        
                        ratio = max(0, min(ratio, 0.8))
                        orig_msgs = msgs
                        msgs = _trim_length(msgs, ratio=ratio)
                        if (not msgs):
                            msgs = orig_msgs
                        else:
                            try:
                                print("retrying with limit msg length")
                                ret = create_resp()
                            except Exception as e1:
                                traceback.print_exc()
                                ret = None
                            if (ret is not None):
                                print("succuess with cut context")
                                return ret

                    raise e
                return resp, resp.choices[0].message
            resp, resp_msg = create_resp()
            retry = 5
            tool_visited = set()
            
            while (True):
                convert_contents = ""
                tool_resps = []

                if (resp_msg.content):
                    ok, err_msg, contents = handle_deekseek_result(mes, resp_msg, resp_msg.content)
                    if (ok):
                        # static_route(route_provider, route_model, success_cnt=1)
                        convert_contents = contents

                    else:
                        print(f"==== FAIL ==== retry-remain: {retry}, err_msg: {err_msg}, group_id: {self.group_id}, provider/model: {route_provider}/{route_model}")
                        print("<=== contents ====")
                        static_route(route_provider, route_model, success_cnt=0)
                        static_route(route_provider, route_model, fail_content=openai_obj_2_dict(resp))
                        print(resp_msg.content)
                        print("==== contents ===>")
                        retry -= 1
                        
                        top_p       = top_p       * get_cfg("deepseek_chat", "top_p_retry_scale"       , 0.5)
                        temperature = temperature * get_cfg("deepseek_chat", "templerature_retry_scale", 0.5)
                        if (retry>=0):
                            resp, resp_msg = create_resp()
                            continue
                        else:
                            raise Exception(err_msg)
                if (getattr(resp_msg, "tool_calls", [])):
                    tool_calls = resp_msg.tool_calls
                    for call in tool_calls:
                        fname = call.function.name
                        if (isinstance(call.function.arguments, str)):
                            call.function.arguments = json.dumps(json.loads(call.function.arguments), ensure_ascii=False)
                        elif (isinstance(call.function.arguments, dict)):
                            call.function.arguments = json.dumps(call.function.arguments, ensure_ascii=False)
                    if (get_cfg("debug", "dump_tool_call")):
                        try:
                            pth = g_paths.get_file_path("debug", "to_deepseek", f"{mes.sender.group_id}.tool.json")
                            with open(pth, "w", encoding="utf-8") as f:
                                json.dump(openai_obj_2_dict(resp_msg), f, ensure_ascii=False)
                            print("debug tool call", pth)
                        except Exception as e:
                            pass
                    for call in tool_calls:
                        fname = call.function.name
                        call.function.arguments = json.dumps(json.loads(call.function.arguments), ensure_ascii=False)

                        fargs = json.loads(call.function.arguments)
                        
                        visted_key = (fname, call.function.arguments)
                        visited = visted_key in tool_visited
                        tool_visited.add(visted_key)
                        if (retry_tool <= 0):
                            fret = json.dumps({"status": "forbidden", "reason": "tool call retry count exceed"})
                        elif (visited and not get_cfg("tool_call", "allow_identical_retry", False)):
                            fret = json.dumps({"status": "forbidden", "reason": "duplicated tool call"})
                        else:
                            try:
                                fret = function_map[fname](**fargs)
                                fret = tool_ret2deepseek(fret)

                            except Exception as e:
                                traceback.print_exc()
                                fret = json.dumps({"status": "fail", "reason": "tool call internal error "+repr(e)})
                        # msgs.append(MessageTool(openai_obj_2_dict(resp_msg)))
                        tool_resps.append(MessageTool({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": fname, 
                            "content": fret
                        }))
                    retry_tool -= 1
                msgs.append(MessageAssistant(convert_contents, openai_obj_2_dict(getattr(resp_msg, "tool_calls", None))))
                if (tool_resps):
                    msgs.extend(tool_resps)
                else:
                    break
                resp, resp_msg = create_resp()
            self.msgs = msgs
            self.save_to_db()

def try_repair_json_str(content):
    repl = []
    trail_backslach = 0
    instr = False
    i = 0
    while (i<len(content)):
        ch = content[i]
        if (not instr):
            if (ch=='"'):
                instr = True
            repl.append(ch)
            i = i+1
        else:
            if (ch == "\\"):
                trail_backslach += 1
                repl.append(ch)
            else:
                if (ch == '"'):
                    if (trail_backslach%2 == 1):
                        repl.append(ch)
                    else:
                        j = i+1
                        find_delim = False
                        while (j<len(content)):
                            chj = content[j]
                            if (chj in [",", "]", "}", ":"]):
                                find_delim = True
                                break
                            elif (chj not in [" \n\r\t"]):
                                find_delim = False
                                break
                            j = j+1
                        if (j==len(content)):
                            find_delim = True
                        if (not find_delim):
                            repl.append('\\"')
                        else:
                            repl.append('"')
                            instr = False
                else:
                    repl.append(ch)
                    trail_backslach = 0
            i = i+1
    print("".join(repl))
    return ast.literal_eval("".join(repl))

def try_load_json(content):
    ok = False
    try:
        ret = json.loads(content)
        ok = True
    except json.JSONDecodeError:
        print("load json error", content)
        ok = False
    if (ok):
        return ret
    try:
        ret = try_repair_json_str(content)
        ok = True
    except SyntaxError as e:
        traceback.print_exc()
        raise e
    return ret



def deepseek_resp_to_send(ymes: YBaseImage, resp_msg, resp_content: str):
    try:
        content_dict: List[Dict] = json.loads(resp_content)
        content_dict: List[Dict] = try_load_json(resp_content)
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

def try_send_mseg(ymes: YBaseMessage, mseg: List[MessageSegment]) -> Tuple[bool, str]:
    sent_any = False
    decompose = len(mseg) <= 3
    composed = []

    for idx, i in enumerate(mseg):
        if (idx):
            time.sleep(1)
        if (isinstance(i, MSEGImage)):
            if (i.get_pil() is None):
                return False, "image is not found %s"%(i.image_id)
        try:
            if (decompose):
                to_send = i.to_send()
            else:
                composed.append(i.to_send())
        except Exception as e:
            if (not sent_any):
                return False, "cannot prepare %s"%(i.to_db())
        if (decompose):
            try:
                ymes.sync_send([to_send])
            except Exception as e:
                if (not sent_any):
                    try:
                        to_db = i.to_db()
                    except:
                        to_db = repr(i)
                    return False, "cannot send content %s-%s"%(to_db, to_send)
    if (composed):
        try:
            ymes.sync_send(composed)
        except:
            return False, "cannot send %s"%(to_send)
    return True, ""


# returns Tuple[ok: bool, err_msg: str, msg: List[MessageSegment]
def handle_deekseek_result(ymes: YBaseMessage, resp_msg, resp_content: str) -> Tuple[bool, str, List[MessageSegment]]:
    deserialize_ok = False
    try:
        content_ls = try_load_json(resp_content)
        deserialize_ok = True
    except Exception as e:
        print(resp_content, "json decode error")
        deserialize_ok = False
        return False, "json decode error "+repr(e), None

    instantiate_ok = False
    try:
        content_mseg: List[MessageSegment] = [mseg_from_db(i) for i in content_ls]
        instantiate_ok = True
    except Exception as e:
        print(content_ls)
        instantiate_ok = False
        return False, "load mseg error "+repr(e), None
    
    send_ok, err_msg = try_send_mseg(ymes, content_mseg)
    if (not send_ok):
        return False, err_msg, None
    else:
        return True, "", content_mseg

