from yaqianbot.adapters.base_adapter.message import BaseMessage
from PIL import Image
from typing import List, Dict
import requests
from io import BytesIO
from yaqianbot.globals.g_cfg import get as get_cfg
import json, traceback
from ...message.mseg_img import LiteralPILProvider, MSEGImage
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


def add_bocha(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    key = get_cfg("bocha", "api_key", None)
    if (key is None):
        return
    def f(query: str):
        # if (mes):
        #     mes.sync_send(["正在搜索: "+query])
        endpoint = get_cfg("bocha", "base_url", "https://api.bochaai.com/v1") + "/web-search"
        data = json.dumps({
            "query": query,
            "summary": True,
            "count": 15
        })
        headers = {
            'Authorization': 'Bearer '+key,
            'Content-Type': 'application/json'
        }
        resp = requests.request("POST", endpoint, headers=headers, data=data)
        j = resp.json()
        ret = {}
        if (j.get("code", -404) != 200):
            ret["status"] = "fail"
            ret["code"] = j.get("code", -404)
            return json.dumps(ret, ensure_ascii=False)
        ret["web_pages"] = []
        allowed_fields = ["siteName", "url", "snippet", 'summary']
        for p in j.get("data", {}).get("webPages", {}).get("value", []):
            filtered = {k: v for k, v in p.items() if k in allowed_fields}
            ret["web_pages"].append(filtered)
        
        ret["web_images"] = []
        for i in j.get("data", {}).get("images", {}).get("value", []):
            url = i["contentUrl"]
            try:
                if (url.startswith("//")):
                    url = "https:"+url
                r = requests.get(url)
                bio = BytesIO()
                bio.write(r.content)
                bio.seek(0)
                pil = Image.open(bio)
                m = MSEGImage(base_img=LiteralPILProvider(pil))
                m.save_data_to_db()
                ret["web_images"].append(m.to_deepseek())
            except Exception as e:
                traceback.print_exc()
                print(e)
        
        ret["status"] = "ok"


        return json.dumps(ret, ensure_ascii=False)
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