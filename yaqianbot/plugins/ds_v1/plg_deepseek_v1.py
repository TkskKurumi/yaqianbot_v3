from ...receiver import on_message, command, on_exception_send_sync, on_tome
from datetime import datetime
from ...adapters.base_adapter.message import BaseMessage
from ...globals.g_threading import threading_run
from collections import defaultdict
import sqlite3
from threading import RLock
from typing import List, Dict, Union, Any
import openai
import json
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from ...globals.g_cfg import get as get_cfg
from ...globals.g_paths import get_file_path
from contextlib import contextmanager
import os
from math import ceil
from .system_templates import TEMPLATES
from ..sdxl_v0.plg_sdxl import for_deepseek as sdxl_deepseek
from types import NoneType
from .tools import add_all_tools
def _rand_str(n_bytes=8):
    return os.urandom(n_bytes).hex()
class _DB:
    def __init__(self, db_pth):
        self.db_pth = db_pth
        self.lck = RLock()
    def _init_db(self, conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions(
                sess_id TEXT,
                content BLOB,
                PRIMARY KEY (sess_id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sess(
                user_id TEXT,
                sess_ls BLOB,
                PRIMARY KEY (user_id)
            );
        """)
    @contextmanager
    def _get_conn(self):
        with self.lck:
            conn = sqlite3.connect(self.db_pth, check_same_thread=False)
            self._init_db(conn)
            try:
                yield conn.cursor()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

def blob2dict(blb: bytes):
    return json.loads(blb.decode("ascii"))
def dict2blob(dic):
    return json.dumps(dic, ensure_ascii=True).encode("ascii")

DB = _DB(get_file_path("deepseek_v1", "mes_storage.sqlite3"))


client = OpenAI(api_key=get_cfg("deepseek_chat", "api_key", None), base_url=get_cfg("deepseek_chat", "endpoint", "https://api.deepseek.com"))
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
        

def kwa2dict(**kwa):
    return kwa


def remove_think(msg, start="<think>", end="</think>"):
    c = msg.content
    if (c.startswith(start) and (end in c)):
        c = c[c.find(end)+len(end):]
        msg.content = c
    return msg



class Session:
    _opened = {}
    contents: List[Union[Dict, ChatCompletionMessage]]
    summary_cache: Union[NoneType, Dict[str, str]]
    sess_id: str

    @classmethod
    def find_by_id(cls, sess_id, *args):
        if (sess_id in cls._opened):
            return cls._opened[sess_id]
        with DB._get_conn() as cur:
            cur = cur.execute("SELECT content from sessions WHERE sess_id=?", (sess_id, ))
            rows = cur.fetchone()
            if (rows):
                content = blob2dict(rows[0])
                ret = cls(**content)
                cls._opened[sess_id] = ret
                return ret
            elif (args):
                return next(iter(args))
            else:
                raise KeyError(sess_id)
    @classmethod
    def new_from_template(cls, template, new_id=None, **variables):
        if (new_id is None):
            new_id = _rand_str()
        if (template not in TEMPLATES):
            raise KeyError(template)
        t = TEMPLATES[template]
        tstring = t["TEMPLATE_STRING"]

        for vname, vinfo in t["VARIABLES"].items():
            if (vname not in variables):
                variables[vname] = vinfo["default"]
        for i in range(100):
            changed = False
            for k, v in variables.items():
                if ("$"+k in tstring):
                    changed = True
                tstring = tstring.replace("$"+k, v)
            if (not changed):
                break
        contents = [kwa2dict(role="system", content=tstring)]
        ret = cls(new_id, contents)
        cls._opened[ret.sess_id] = ret
        ret.save_db()
        return ret

    def __init__(self, sess_id, contents, summary_cache=None):
        self.sess_id = sess_id
        self.contents = contents
        self.summary_cache = summary_cache
    def as_dict(self):
        return {
            "sess_id": self.sess_id,
            "contents": openai_obj_2_dict(self.contents),
            "summary_cache": self.summary_cache
        }
    def save_db(self):
        with DB._get_conn() as cursor:
            d = self.as_dict()
            blob = json.dumps(d, ensure_ascii=True).encode("ascii")
            cursor.execute("INSERT OR REPLACE INTO sessions(sess_id, content) VALUES (?, ?)", (self.sess_id, blob))
    def derive(self, new_id=None):
        if (new_id is None):
            new_id = _rand_str()
        ret = type(self)(new_id, list(self.contents), self.summary_cache)
        type(ret)._opened[ret.sess_id] = ret
        return ret

    def cont_chat(self, mes: BaseMessage, content):
        uid = mes.sender.uid
        add_user_sess(uid, self.sess_id)
        function_ls = []
        function_map = {}
        add_all_tools(mes, function_ls, function_map)
        print(function_ls)
        print(function_map)
        
        dlgs = self.contents
        dlgs.append(kwa2dict(role="user", content=content))
        resp = client.chat.completions.create(model=get_cfg("deepseek_chat", "model", "deepseek-chat"), messages=dlgs, tool_choice="auto", tools=function_ls)

        resp_msg = remove_think(resp.choices[0].message)
        dlgs.append(resp_msg)

        while (getattr(resp_msg, "tool_calls", [])):
            tool_calls = resp_msg.tool_calls
            for call in tool_calls:
                fname = call.function.name
                fargs = json.loads(call.function.arguments)
                fret  = function_map[fname](**fargs)
                dlgs.append(kwa2dict(role="tool", tool_call_id=call.id, name=fname, content=fret))
            resp = client.chat.completions.create(model=get_cfg("deepseek_chat", "model", "deepseek-chat"), messages=dlgs, tool_choice="auto", tools=function_ls)
            resp_msg = remove_think(resp.choices[0].message)
            dlgs.append(resp_msg)
        self.contents = dlgs
        self.save_db()
        print(dlgs)
        return resp_msg.content
    @property
    def summary(self):
        return self.get_summary(raise_for_exception=False)
    def get_summary(self, raise_for_exception=False):
        try:
            content_str = []
            for i in self.contents:
                if (hasattr(i, "content")):
                    content_str.append(i.content)
                elif (isinstance(i, dict) and i.get("content", None)):
                    content_str.append(i["content"])
            content_str = "; ".join(content_str)
            if (self.summary_cache is None):
                self.summary_cache = dict()
            if (content_str in self.summary_cache):
                return self.summary_cache[content_str]
            
            dlgs = list(self.contents)
            dlgs.append(kwa2dict(role="user", content="请用最少的字数总结对话"))
            resp = client.chat.completions.create(model=get_cfg("deepseek_chat", "model", "deepseek-chat"), messages=dlgs)
            resp_msg = remove_think(resp.choices[0].message)
            self.summary_cache[content_str] = resp_msg.content
            self.save_db()
            return resp_msg.content
        except Exception as e:
            if (raise_for_exception):
                raise e
            else:
                return "总结内容时出错: %s"%e
USER_LS: Dict[str, List[str]] = defaultdict(list)
with DB._get_conn() as cur:
    rows = cur.execute("SELECT user_id, sess_ls FROM user_sess").fetchall()
    n = len(rows)
    print(rows)
    for uid, sess_ls_blb in rows:
        sess_ls = blob2dict(sess_ls_blb)
        USER_LS[uid] = sess_ls
        

def make_top(ls: List, elem):
    ls.sort(key=lambda x: x!=elem)
    return ls
def make_short_alias(ls):
    s = set(ls)
    le = 1
    while (True):
        short2long = {i[:le]: i for i in s}
        long2short = {i: i[:le] for i in s}
        if (len(short2long) == len(s)):
            return short2long, long2short
        le += 1
        if (le>100):
            assert False

def save_user_ls(uid, ls):
    USER_LS[uid] = ls
    with DB._get_conn() as cur:
        blb = dict2blob(ls)
        cur.execute("INSERT OR REPLACE INTO user_sess(user_id, sess_ls) VALUES (?, ?)", (uid, blb))
    return ls

def get_user_sess0(uid):
    ls = USER_LS[uid]
    if (ls):
        return Session.find_by_id(ls[0])
    new = Session.new_from_template(next(iter(TEMPLATES)))
    ls.append(new.sess_id)
    ls = make_top(ls, ls[-1])
    
    save_user_ls(uid, ls)
    return Session.find_by_id(ls[0])

def add_user_sess(uid, sess_id):
    ls = USER_LS[uid]
    if (sess_id not in ls):
        ls.append(sess_id)
    make_top(ls, sess_id)
    save_user_ls(uid, ls)


@on_message
@threading_run
@on_exception_send_sync
@command("#聊天new")
def cmd_chat_new(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    template_name = args[0]
    
    args1 = list(args[1:])
    var = {}
    
    for idx, i in enumerate(args1):
        if (idx%2):
            var[args1[idx-1]] = i
    
    mes.sync_send(["DEBUG: templ = %s, var = %s"%(template_name, var)])

    sess = Session.new_from_template(template_name, **var)
    print(sess.contents)
    add_user_sess(uid, sess.sess_id)

    mes.sync_send(["SESS_ID: %s"%sess.sess_id])

@on_message
@threading_run
@on_exception_send_sync
@command("#聊天副本")
def cmd_chat_dup(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    sess = get_user_sess0(uid)
    sess1 = sess.derive()
    sess1.save_db()
    ls = USER_LS[uid]
    ls.append(sess1.sess_id)
    make_top(ls, sess1.sess_id)
    make_top(ls, sess.sess_id)
    save_user_ls(uid, ls)
    
    mes.sync_send(["副本另存为: %s"%sess1.sess_id])


@on_message
@threading_run
@on_tome
@on_exception_send_sync
def chat_ds_v1(mes: BaseMessage):
    sess = get_user_sess0(mes.sender.uid)
    content = sess.cont_chat(mes, mes.text_for_command)
    mes.sync_send([content])



class PrintBuf:
    def __init__(self):
        self.buf = []
    def get(self):
        return "".join(self.buf)
    def __call__(self, *args, sep=" ", end="\n"):
        for idx, i in enumerate(args):
            if (idx):
                self.buf.append(sep)
            self.buf.append(str(i))
        self.buf.append(end)
@on_message
@threading_run
@on_exception_send_sync
@command("#聊天列表")
def cmd_chat_sess_ls(mes: BaseMessage):
    uid = mes.sender.uid
    if (not USER_LS[uid]):
        mes.sync_send(["没有聊天记录"])
        return
    ls = USER_LS[uid][:10]
    s, l = make_short_alias(ls)
    prt = PrintBuf()
    for long_id in ls:
        short_id = l[long_id]
        try:
            sess = Session.find_by_id(long_id)
        except KeyError:
            sess = Session.new_from_template(next(iter(TEMPLATES)), new_id=long_id)
            sess.save_db()
            mes.sync_send(["session_id %s 的session不存在，为了修复databse，新建了一个空的session"%long_id])
        prt(short_id, ":", sess.summary)

    mes.sync_send([prt.get()])

@on_message
@threading_run
@on_exception_send_sync
@command("#聊天切换")
def cmd_chat_sess_switch(mes: BaseMessage, *args, **kwargs):
    uid = mes.sender.uid
    sess_id = (" ".join(args)).strip()
    ls = USER_LS[uid][:10]
    s, l = make_short_alias(ls)

    found = None
    if (sess_id in s):
        found = s[sess_id]
    elif (sess_id in l):
        found = sess_id
    elif (Session.find_by_id(sess_id, None) is not None):
        found_sess = Session.find_by_id(sess_id).derive()
        found_sess.save_db()
        found = found_sess.sess_id
        mes.sync_send(["获取了其他用户的消息%s -> %s"%(sess_id, found)])
    else:
        mes.sync_send(["未知聊天记录", sess_id, str(ls)])
        return
    sess_id = found
    if (sess_id not in ls):
        ls.append(sess_id)
    make_top(ls, sess_id)
    save_user_ls(uid, ls)
    sess = Session.find_by_id(sess_id)
    mes.sync_send(["已切换至%s : %s"%(sess.sess_id, sess.summary)])

@on_message
@threading_run
@on_exception_send_sync
@command("#聊天修复")
def cmd_chat_sess_repair(mes: BaseMessage):
    uid = mes.sender.uid
    sess0 = get_user_sess0(uid)
    sess = sess0.derive()
    
    while (sess.contents):
        try:
            sess.summary_cache = None
            sum = sess.get_summary(raise_for_exception=True)
            sess.save_db()
            break
        except Exception as e:
            s1 = sess.derive()
            contents = list(s1.contents)
            while (True):
                contents.pop()
                if (not contents):
                    mes.sync_send(["修复失败"+str(e)])
                    return
                last = contents[-1]
                if (isinstance(last, dict)):
                    last_role = last.get("role", "")
                else:
                    last_role = getattr(last, "role", "")
                if (last_role in ["assistant", "system"]):
                    s1.contents = contents
                    sess = s1
                    break
    ls = USER_LS[uid]
    ls.append(sess.sess_id)
    make_top(ls, sess.sess_id)
    info = f"已删除部分末尾消息，长度{len(sess0.contents)} -> {len(sess.contents)}。新聊天{sess.sess_id}: {sess.summary}"
    mes.sync_send([info])
