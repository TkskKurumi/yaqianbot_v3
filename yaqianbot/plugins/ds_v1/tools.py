from ...adapters.base_adapter.message import BaseMessage
from typing import List, Dict, Union, Set, Any
from datetime import datetime
from ..sdxl_v0.plg_sdxl import for_deepseek as sdxl_deepseek
from ...globals.g_cfg import get as get_cfg
import json
import requests
def build_param(typ, desc):
    return {"type": typ, "description": desc}
def build_params(**kwargs):
    return kwargs
def build_function(name, desc, required, params):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required
            }
        }
    }

def add_username(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f():
        return mes.sender.username
    func = build_function(
        name="get_username",
        desc="获取用户名",
        required=[],
        params={}
    )
    tool_ls.append(func)
    tool_map["get_username"] = f
def add_datetime(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f():
        now = datetime.now().strftime("%Y年%m月%d日%H时%M分")
        return now
    func = build_function(
        name="get_datetime",
        desc="获取当前日期（年月日时分）",
        required=[],
        params={}
    )
    tool_ls.append(func)
    tool_map["get_datetime"] = f
def add_sdxl(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(prompt: str):
        return sdxl_deepseek(mes, prompt)
    func = build_function(
        name="txt2img",
        desc="调用文生图AI生成图片发送给用户，接受图片描述为输入，返回结果成功或失败",
        required=["prompt"],
        params=build_params(
            prompt=build_param(
                typ="string",
                desc="文生图的文字描述输入。适应danbooru风格的英文标签描述而非长句的自然语言，例如粉发水手服猫娘躺在床上看书“pink hair, serafuku, cat ears, on bed, reading, holding book”"
            )
        )
    )
    tool_ls.append(func)
    tool_map["txt2img"] = f
def add_bocha(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    key = get_cfg("bocha", "api_key", None)
    if (key is None):
        return
    def f(query: str):
        mes.sync_send(["正在搜索: "+query])
        endpoint = get_cfg("bocha", "base_url", "https://api.bochaai.com/v1") + "/web-search"
        data = json.dumps({
            "query": query,
            "summary": True,
            "count": 50
        })
        headers = {
            'Authorization': 'Bearer '+key,
            'Content-Type': 'application/json'
        }
        resp = requests.request("POST", endpoint, headers=headers, data=data)
        j = resp.json()
        if (j.get("code", -404) != 200):
            return "搜索失败：code %s"%j.get("code", -404)
        pages = j.get("data", {}).get("webPages", {}).get("value", [])
        if (not pages):
            return "搜索失败: 结果为空"
        resp_simple = []
        allowed_fields = ["siteName", "url", "snippet", 'summary']
        for p in pages:
            filtered = {k: v for k, v in p.items() if k in allowed_fields}
            resp_simple.append(filtered)
        return json.dumps(resp_simple)
    func = build_function(
        name="web_search",
        desc="联网搜索",
        required=["query"],
        params=build_params(
            query=build_param(
                typ="string",
                desc="联网搜索关键词"
            )
        )
    )
    tool_ls.append(func)
    tool_map["web_search"] = f
    


def add_all_tools(mes: BaseMessage, tool_ls, tool_map):
    for f in [add_bocha,
              add_datetime,
              add_sdxl,
              add_username]:
        f(mes, tool_ls, tool_map)
    