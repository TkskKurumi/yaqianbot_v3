from yaqianbot.adapters.base_adapter.message import BaseMessage
from typing import Dict, List
from .volce import img_caption as volce_img_caption
from ..message.mseg_img import MSEGImage
from ..image_search_db import index as image_search_index
from .bocha.bocha_search import add_bocha
import json
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

    

def add_search_image(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(desc_detail, desc_medium, desc_rough):
        ret = {}
        found_any = False
        for level, desc in [("detail", desc_detail), ("medium", desc_medium), ("rough", desc_rough)]:
            found = image_search_index.find_image_by_desc(desc)
            if (found):
                found_any = True
                ret[f"found_{level}"] = {
                    "image_id": found,
                    "desc": image_search_index.volce_goc_img_desc(found)
                }
                break
        ret["status"] = "ok" if found_any else "fail"
        return json.dumps(ret, ensure_ascii=False)
    desc = "从图库中，根据自然语言检索图片。接受三个等级的输入。返回image_id和其描述。"
    func = build_function(
        name="search_image",
        desc=desc,
        required=["desc_detail", "desc_medium", "desc_rough"],
        params=build_params(
            desc_detail=build_param(
                typ="string",
                desc="详细的搜索要求，例如“粉色头发的猫娘微笑表情包”、“蓝发JK角色的二次元插画”"
            ),
            desc_medium=build_param(
                typ="string",
                desc="中等的搜索要求，例如“猫娘微笑表情包”，“蓝发角色的二次元插画”"
            ),
            desc_rough=build_param(
                typ="string",
                desc="粗略的搜索要求，例如“表情包”，“二次元插画”"
            )
        )
    )
    tool_ls.append(func)
    tool_map["search_image"] = f
def add_get_img_desc(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(image_id: str, query_prompt: str):
        if (image_id not in MSEGImage._opened):
            return json.dumps({"status": "fail", "message": "Image not found by id %s"%image_id}, ensure_ascii=False)
        img = MSEGImage._opened[image_id]
        img = img.get_pil()
        desc = volce_img_caption(img, prompt_ex=query_prompt)
        return json.dumps({"status": "ok", "desc": desc, "image_id": image_id}, ensure_ascii=False)
    desc = "调用外部工具，通过多模态AI分析图片内容。接受自然语言输入想要查询的内容。"
    func = build_function(
        name="get_img_desc",
        desc=desc,
        required=["image_id", "query_prompt"],
        params=build_params(
            image_id=build_param(
                typ="string",
                desc="聊天记录中出行图片的image_id。"
            ),
            query_prompt=build_param(
                typ="string",
                desc="需要查询的信息，接受自然语言输入。例如“图片里的角色是谁？”、“图片属于哪种风格”、“图中的人物在什么地方”等"
            )
        )
    )
    tool_ls.append(func)
    tool_map["get_img_desc"] = f



def add_all_tool(mes: BaseMessage, tool_ls:List, tool_map:Dict):
    for i in [add_get_img_desc, add_search_image, add_bocha]:
        i(mes, tool_ls, tool_map)
    