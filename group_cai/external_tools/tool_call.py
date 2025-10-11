from yaqianbot.adapters.base_adapter.message import BaseMessage
from typing import Dict, List
from .volce import img_caption as volce_img_caption
from ..message.mseg_img import MSEGImage

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


def add_get_img_desc(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(image_id: str, query_prompt: str):
        if (image_id not in MSEGImage._opened):
            return {"status": "fail", "message": "Image not found by id %s"%image_id}
        img = MSEGImage._opened[image_id]
        img = img.get_pil()
        desc = volce_img_caption(img, prompt=query_prompt)
        return {"status": "ok", "desc": desc, "image_id": image_id}
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
    for i in [add_get_img_desc]:
        i(mes, tool_ls, tool_map)
    