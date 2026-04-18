from yaqianbot.adapters.base_adapter.message import BaseMessage
from PIL import Image
from yaqianbot.plugins.zimage.client_sdcpp_edit import create as create_image_edit
from typing import List
from ...message.mseg_img import MSEGImage, LiteralPILProvider
from openai import OpenAI
import random
from typing import Dict, Optional
from yaqianbot.globals.g_cfg import get as get_cfg
from ..builder import *
from ...database.image import (
    get_img_info_recur as db_get_img_info_recur,
    set_img_info_recur as db_set_img_info_recur
)
from ...utils import img2b64url, img2openai, b64url2img
from openai import APIConnectionError
from ...utils.action_point import get_user_section as ap_get_user_section

# API_KEY = get_cfg("image_edit", "api_key", "")
# BASE_URL = get_cfg("image_edit", "base_url", "https://openrouter.ai/api/v1")
# MODEL = get_cfg("image_edit", "model", "google/gemini-3-pro-preview")
# EXTRA_BODY=get_cfg("image_edit", "extra_body", {"modalities": ["image", "text"]})
# CLIENT = OpenAI(api_key=API_KEY, base_url=BASE_URL)

AP_MAX = get_cfg("zimage", "edit", "ap_max", 100)
AP_REC = get_cfg("zimage", "edit", "ap_rec", 100/24/3600)
AP_COST = get_cfg("zimage", "edit", "ap_cost", 100/2)

def time_str(seconds):
    s = seconds%60
    m = int((seconds//60)%60)
    h = int(seconds//3600)
    ret = []
    if (h):
        ret.append(f"{h}小时")
    if (m):
        ret.append(f"{m}分钟")
    if (not h and s):
        ret.append(f"{s}秒")
    return "".join(ret)


prompt_example = get_cfg("zimage", "edit", "prompt_example", ["把这张照片转换为二次元风格。"])
prompt_example = ["例如：“" + i + "”" for i in prompt_example]
prompt_desc = "\n".join(
    ["图像编辑的文本提示词。"] + prompt_example + ["以上我给出的例子都比较简略，实际请扩充完善提示词的细节。"]
)

FUNC_SCHEMA = build_function(
    name="image_edit",
    desc="调用外部工具，进行基于AI的图像编辑。接收一个prompt和多个参考图片。",
    required=["message_to_user", "prompt", "ref_img_ids"],
    params=build_params(
        message_to_user=build_param(
            typ="string",
            desc="进行图像编辑调用前，先给用户发送一条消息告知。例如“菜包马上帮您编辑图像，请稍等哟”、“菜包这就调用图像编辑AI，帮你给角色戴上帽子，马上就好！”、“接下来菜包会用AI工具帮你实现创意的，不过要花点时间哟~”"
        ),
        prompt=build_param(
            typ="string",
            desc=prompt_desc
        ),
        ref_img_ids=build_param(
            typ="array",
            desc="图像编辑的基础图片或参考图片，一个或者多个",
            minItems=1,
            maxItems=10,
            items={"type": "string"}
        )
    )
)
class Content2OpenAI:
    def __init__(self, *contents):
        self.contents = contents
    def _content_to_openai(self, x):
        if (isinstance(x, str)):
            return {
                "type": "text",
                "text": x
            }
        elif (isinstance(x, Image.Image)):
            return {
                "type": "image_url",
                "image_url": {"url": img2b64url(x, 500000)}
            }
    def to_openai(self):
        return {
            "role": "user",
            "content": [self._content_to_openai(i) for i in self.contents]
        }
# def openai_image_edit(prompt, images: List[Image.Image]):
    # messages = [Content2OpenAI(prompt, *images).to_openai()]
    # resp = CLIENT.chat.completions.create(
    #     messages=messages,
    #     model=MODEL,
    #     extra_body=EXTRA_BODY
    # )
    # resp_msg = resp.choices[0].message
    
    # ret_imgs = []
    # if getattr(resp_msg, "images", None):
    #     for img in resp_msg.images:
    #         image_url = img['image_url']['url']  # Base64 data URL
    #         img = b64url2img(image_url)
    #         ret_imgs.append(img)
    # return resp, resp_msg, ret_imgs
    
def randstr(n, charset="1234567890abcdef"):
    buf = []
    for i in range(n):
        buf.append(random.choice(charset))
    return "".join(buf)
def add_image_edit(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def f(message_to_user, prompt, ref_img_ids: List[str]):
        img_pils = []
        for img_id in ref_img_ids:
            img_seg = MSEGImage.from_db({"image_id": img_id})
            try:
                pil = img_seg.get_pil()
                if (pil is None):
                    return {"status": "fail", "message": "无法打开图片%s，可能是id传入有误"%(img_id,)}    
                img_pils.append(pil)
            except Exception as e:
                return {"status": "fail", "message": "无法打开图片%s: %s"%(img_id, repr(e))}
        mes.sync_send([message_to_user, "(🎨✏️)"])
        with ap_get_user_section(mes.sender.uid, "image_edit", AP_MAX, AP_REC) as section:
            section.ap_max = AP_MAX
            section.ap_rec = AP_REC
            section.write_db()
            regen_time = section.check_recovery_time(AP_COST)
            if (regen_time):
                return {"status": "fail", "brief": "rate limtied", "detail": {
                    "credit_regen_max": {"value": AP_MAX, "desc": f"credit会按时间补充，但是最多到达{AP_MAX}"},
                    "credit_regen_daily": {"value": AP_REC*24*3600, "desc": "恢复速度（24小时）"},
                    "credit_current": section.update(),
                    "time_needed_regen": {"value": regen_time, "desc": f"等待{time_str(regen_time)}后有充足credit执行此操作"}
                }}
            section.consume(AP_COST, no_check=True)
            try:
                img_pil = create_image_edit(prompt, img_pils)
                i = MSEGImage(base_img=LiteralPILProvider(img_pil, unique_id=f"image_edit-{randstr(8)}.jpg"))
            except Exception as e:
                section.consume(-AP_COST, no_check=True)
                raise e
            return i.to_deepseek()
                
            # if (getattr(resp, "cost", None) is not None):
            #     cost_usd = resp.cost
            #     cost_cny = cost_usd*7.5
            # else:
            #     cost_usd = "UNKNOWN"
            #     cost_cny = "UNKNOWN"
            # print(getattr(resp_msg, "content", None))
            # print(getattr(resp_msg, "reasoning", None))
            # img_out_segs = [MSEGImage(base_img=LiteralPILProvider(i)) for i in img_out_pils]
            # return {
            #     "status": "ok",
            #     "images": [i.to_deepseek() for i in img_out_segs],
            #     "message": resp_msg.content,
            #     "cost_cny": {"value": cost_cny, "desc": "此次图片编辑API花费人民币。"},
            #     "cost_usd": {"value": cost_usd, "desc": "此次图片编辑API花费美元。"}
            # }
    tool_ls.append(FUNC_SCHEMA)
    tool_map["image_edit"] = f
