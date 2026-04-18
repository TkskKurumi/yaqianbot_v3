from yaqianbot.adapters.base_adapter.message import BaseMessage
from typing import Dict, List
from .volce import img_caption as volce_img_caption
from ..message.mseg_img import MSEGImage, LiteralPILProvider
from ..image_search_db import index as image_search_index
from .bocha.bocha_search import add_bocha
import json, random
from yaqianbot.globals.g_cfg import get as get_cfg
from .builder import *
from .zimage.zimage import add_zimage
from .image_edit.image_edit import add_image_edit

def add_search_image(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(desc_detail, desc_medium, desc_rough):
        if (True):
            excludes = get_cfg("exclude_image_search", [])
            imgs = image_search_index.find_images_by_descs(desc_detail, desc_medium, desc_rough, *excludes, k=3)
            def fkey(i):
                m = i.get("match_desc", {})
                return m.get(desc_detail, 0) + m.get(desc_medium, 0)*0.1 + m.get(desc_rough, 0)*0.01
            imgs_filtered = []
            for i in imgs:
                ok = True
                for j in excludes:
                    if (i["match_desc"][j] > 0.9):
                        ok = False
                if (ok):
                    imgs_filtered.append(i)
            imgs = imgs_filtered
            imgs.sort(key=fkey, reverse=True)
            imgs = imgs[:3]
            for i in imgs:
                i["desc"] = image_search_index.volce_goc_img_desc(i["image_id"])
            return json.dumps(imgs, ensure_ascii=False)


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
def add_get_img_qa(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(image_id: str, query_prompt: str):
        if (image_id not in MSEGImage._opened):
            return json.dumps({"status": "fail", "message": "Image not found by id %s"%image_id}, ensure_ascii=False)
        img = MSEGImage._opened[image_id]
        img = img.get_pil()
        desc = volce_img_caption(img, prompt_ex=query_prompt)
        return json.dumps({"status": "ok", "desc": desc, "image_id": image_id}, ensure_ascii=False)
    desc = "调用外部工具，通过多模态AI分析图片内容。接受自然语言输入想要查询的内容。"
    func = build_function(
        name="get_img_qa",
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
    tool_map["get_img_qa"] = f
def add_get_user_avatar(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(userid: str):
        avt = mes.get_user_avatar(userid)
        m = MSEGImage(base_img=LiteralPILProvider(avt))
        m.save_data_to_db()
        ret = {
            "userid": userid,
            "avatar": m.to_deepseek()
        }
        return json.dumps(ret, ensure_ascii=False)

    desc = "获取用户的头像信息，参数为userid。"
    func = build_function(
        name="get_user_avatar",
        desc=desc,
        required=["userid"],
        params=build_params(
            userid=build_param(
                typ="string",
                desc="用户的账号ID。"
            )
        )
    )

    tool_ls.append(func)
    tool_map["get_user_avatar"] = f

def add_fair_dice(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(dice_num: int, dice_range: int):
        if (dice_num > 100):
            raise ValueError("number of dice should be smaller than 100")
        if (dice_range > 1000):
            raise ValueError("range of dice should be smaller than 1000")
        nums = []
        for i in range(dice_num):
            nums.append(random.randint(1, dice_range))
        mes.sync_send(f"投掷了{dice_num}个 1~{dice_range} 骰子: {nums}，总和{sum(nums)}（🎲）")
        return {"nums": nums, "sum": sum(nums)}
    desc = "排除大语言模型偏置，“公平”地生成随机数"
    func = build_function(
        name="fair_dice",
        desc=desc,
        required=["dice_num", "dice_range"],
        params=build_params(
            dice_num=build_param(
                typ="integer",
                desc="骰子次数",
                minimum=1,
                maximum=100
            ),
            dice_range=build_param(
                typ="integer",
                desc="骰子数值上界"
            )
        )
    )
    tool_ls.append(func)
    tool_map["fair_dice"] = f
        

def add_all_tool(mes: BaseMessage, tool_ls: List = None, tool_map: Dict = None):
    if (tool_ls is None):
        tool_ls = []
    if (tool_map is None):
        tool_map = {}
    for i in [add_get_img_qa, add_search_image, add_bocha, add_get_user_avatar, add_zimage, add_image_edit, add_fair_dice]:
        i(mes, tool_ls, tool_map)
    return tool_ls, tool_map