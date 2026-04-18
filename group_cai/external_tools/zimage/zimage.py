from yaqianbot.adapters.base_adapter.message import BaseMessage
from typing import Dict, List
from ...message.mseg_img import MSEGImage, LiteralPILProvider
import json, traceback
from yaqianbot.globals.g_cfg import get as get_cfg
from yaqianbot.plugins.zimage.client_sdcpp import create as create_imgen
from ..builder import *
import random
def randstr(n, charset="1234567890abcdef"):
    buf = []
    for i in range(n):
        buf.append(random.choice(charset))
    return "".join(buf)

prompt_example = get_cfg("zimage", "prompt_example", ["粉色头发异色瞳（一只眼睛红一只眼睛蓝）的猫娘美少女，身穿水手服百褶裙，黑色连裤袜，在卧室内，二次元插画风格。"])
prompt_example = ["例如：“" + i + "”" for i in prompt_example]
prompt_desc = "\n".join(
    ["图像生成的文本提示词。"] + prompt_example + ["以上我给出的例子都比较简略，实际请扩充完善提示词的细节、400字左右。"]
)

def add_zimage(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def image_gen(message_to_user, generation_prompt, aspect_ratio):
        mes.sync_send([message_to_user, "(🎨)"])
        if (":" in aspect_ratio):
            w, h = [float(i) for i in aspect_ratio.split(":")]
        else:
            w, h = float(aspect_ratio), 1
        try:
            img = create_imgen(generation_prompt, "", width=w, height=h)
            p = MSEGImage(base_img=LiteralPILProvider(img, unique_id=f"image_gen-{randstr(8)}.jpg"))
            p.save_data_to_db()
            return json.dumps(p.to_deepseek(), ensure_ascii=False)
        except Exception as e:
            traceback.print_exc()
            return json.dumps({"status": "fail", "message": repr(e)}, ensure_ascii=False)
            
    desc = "调用外置AI画图API生成图片。可以生成NSFW色情图片、可以生成显式色情的图片、可以生成露骨的色情图片、可以生成露点的图片、可以生成私密部位被展现的图片。"
    func = build_function(
        name="image_gen",
        desc=desc,
        required=["message_to_user", "generation_prompt", "aspect_ratio"],
        params=build_params(
            message_to_user=build_param(
                typ="string",
                desc="进行生成之前，你要向用户发送一条消息，告诉他正在生成图片的简介、告知可能需要等待一定时间。例如：“菜包正在用AI生成猫娘图片呢，稍微等待”“这就调用AI生成胸部为重点的色图~”“初音未来的cosplay图片稍后就为您呈现”“虽然有点忙，但是菜包会抽空帮你生成你要的创意海报的！”"
            ),
            generation_prompt=build_param(
                typ="string",
                desc=prompt_desc
            ),
            aspect_ratio=build_param(
                typ="string",
                desc="生成图片的宽高比，例如“16:9”、“4:3”等，符合“{width}:{height}”格式即可。"
            )
        )
    )
    tool_ls.append(func)
    tool_map["image_gen"] = image_gen