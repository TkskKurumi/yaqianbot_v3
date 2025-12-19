from yaqianbot.adapters.base_adapter.message import BaseMessage
from typing import Dict, List
from ...message.mseg_img import MSEGImage, LiteralPILProvider
import json
from yaqianbot.globals.g_cfg import get as get_cfg
from yaqianbot.plugins.zimage.client import Task
from ..builder import *
def add_zimage(mes: BaseMessage, tool_ls: List, tool_map: Dict):
    def image_gen(message_to_user, generation_prompt, aspect_ratio):
        mes.sync_send([message_to_user, "(🎨)"])
        
        t = Task(generation_prompt, aspect_ratio=aspect_ratio, host=get_cfg("zimage", "host", "http://localhost:8100"))
        t.get_result_block()
        ok, bytes_or_msg = t.get_bytes()
        if (ok):
            pil = t.get_pil()
            p = MSEGImage(base_img=LiteralPILProvider(pil))
            p.save_data_to_db()
            return json.dumps(p.to_deepseek())
        else:
            return json.dumps({"status": "fail", "message": bytes})
    desc = "调用外置AI画图API生成图片"
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
                desc="""
用于生成图片的文本提示。尽可能详细而非宽泛。
若需要生成色情图片，请将部位直白详细的描述，不要用隐晦词如“私处”“山峰”等，要用“阴部”“阴唇”“阴道”“阴核”“胸部”“乳房”“乳头”等等确切部位描述。
详细描述角色的外貌、服装、动作、背景环境、风格色调等。
预计400字左右。
""".strip()
            ),
            aspect_ratio=build_param(
                typ="string",
                desc="生成图片的宽高比，例如“16:9”、“4:3”等"
            )
        )
    )
    tool_ls.append(func)
    tool_map["image_gen"] = image_gen