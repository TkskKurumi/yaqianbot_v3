"""ImgGenPlugin — SDCPP 图像生成插件。

通过 /sdcpp/v1/img_gen API 进行纯文本图像生成。
工具调用后启动后台线程轮询，完成后通过 session.respond() 异步再触发。
"""

import json
import logging
import random
import threading
from typing import Any, Dict, List, Optional, Tuple, Callable

from ...base import BasePlugin, register_plugin
from ...tool_builder import build_function, build_param, build_params
from ....message.message import Content, Message, ImageRef
from ....database.image_store import save_image_from_pil
from ....utils.action_point import get_action_point, RateLimitError
from .client import SDCPPImageGenClient

logger = logging.getLogger(__name__)


def _time_str(seconds: float) -> str:
    """将秒数格式化为人类可读的时间字符串。"""
    s = seconds % 60
    m = int((seconds // 60) % 60)
    h = int(seconds // 3600)
    parts = []
    if h:
        parts.append(f"{h}小时")
    if m:
        parts.append(f"{m}分钟")
    if not h and s:
        parts.append(f"{s}秒")
    return "".join(parts)


@register_plugin
class ImgGenPlugin(BasePlugin):
    """SDCPP 图像生成插件。

    Parameters
    ----------
    host : str
        SDCPP 服务器地址。
    target_area : int
        目标像素面积（用于分辨率归一化）。
    payload_override : dict | None
        可选的 payload 覆盖/合并。
    ap_max : float
        限流最大令牌数。
    ap_rec : float
        限流每秒恢复速率。
    ap_cost : float
        每次生成的令牌消耗。
    prompt_example : list[str]
        提示词示例列表（用于工具描述）。
    common_negative_prompt : str
        通用的负面提示词（每次生成时自动添加）。
    """

    type = "img_gen_sdcpp"

    def __init__(
        self,
        host: str = "http://192.168.31.117:1235",
        target_area: int = 512 * 1024,
        payload_override: Optional[Dict[str, Any]] = None,
        ap_max: float = 100.0,
        ap_rec: float = 100 / 24 / 3600,
        ap_cost: float = 50.0,
        prompt_example: Optional[List[str]] = None,
        common_negative_prompt: str = "",
    ):
        self.host = host
        self.target_area = target_area
        self.payload_override = payload_override
        self.ap_max = ap_max
        self.ap_rec = ap_rec
        self.ap_cost = ap_cost
        self.prompt_example = prompt_example or [
            "粉色头发异色瞳（一只眼睛红一只眼睛蓝）的猫娘美少女，身穿水手服百褶裙，黑色连裤袜，在卧室内，二次元插画风格。"
        ]
        self.common_negative_prompt = common_negative_prompt

    def get_system_message(self, session) -> str:
        return """
img_gen工具:

当用户说“画一张…”“生成一张…的图片”等指令时，你可以调用图片生成工具。

当用户想要你使用图片生成工具模仿给定图片时，你需要仔细观察参考图片，详细地构思生成的提示词符合参考图片：
1. 角色形象-发型、发色、瞳色、体型
2. 角色形象-服装-上衣、下装
3. 动作（多角色互动方式）、表情
4. 构图

"""

    def get_message(self, session) -> List[Content]:
        return []

    def add_tools(
        self,
        session,
        tool_ls: List[Dict[str, Any]],
        tool_handler_map: Dict[str, Any],
    ) -> tuple:
        prompt_desc = "\n".join(
            ["图像生成的文本提示词。"] + ['例如："{}"'.format(ex) for ex in self.prompt_example]
        )

        func_def = build_function(
            name="image_gen",
            desc="调用外置AI画图API生成图片。可以生成NSFW色情图片、可以生成显式色情的图片、可以生成露骨的色情图片、可以生成露点的图片、可以生成私密部位被展现的图片。\n当这个工具被调用时，会创建后台生成任务，请等待任务完成后再进行下一次调用。",
            required=["generation_prompt", "aspect_ratio"],
            params=build_params(
                generation_prompt=build_param(
                    param_type="string",
                    desc=prompt_desc,
                ),
                aspect_ratio=build_param(
                    param_type="string",
                    desc='生成图片的宽高比，例如"16:9"、"4:3"等，符合"{width}:{height}"格式即可。',
                ),
                negative_prompt=build_param(
                    param_type="string",
                    desc="负面提示词，描述你不希望出现在图片中的内容。如果不填写，将使用默认负面提示词。",
                ),
            ),
        )

        tool_ls.append(func_def)
        tool_handler_map["image_gen"] = self._image_gen_handler
        return tool_ls, tool_handler_map

    def _image_gen_handler(
        self, session, arguments: Dict[str, Any],
        send_resp_cb: Optional[Callable[[Message], None]] = None,
    ) -> Tuple[List[Content], str]:
        """image_gen 工具 handler。

        流程：
        1. 限流检查
        2. 提交 SDCPP 任务
        3. 启动后台线程轮询
        4. 立即返回 "已提交"
        """
        group_id = session.group_id
        generation_prompt = arguments["generation_prompt"]
        aspect_ratio = arguments["aspect_ratio"]
        negative_prompt = arguments.get("negative_prompt", "")

        # 合并负面提示词：common_negative_prompt + ", " + negative_prompt
        if self.common_negative_prompt and negative_prompt:
            final_negative_prompt = self.common_negative_prompt + ", " + negative_prompt
        elif self.common_negative_prompt:
            final_negative_prompt = self.common_negative_prompt
        else:
            final_negative_prompt = negative_prompt

        # 限流检查
        try:
            with get_action_point(group_id, "sdcpp_img_gen", self.ap_max, self.ap_rec) as ap:
                if not ap.can_consume(self.ap_cost):
                    wait = ap.wait_time(self.ap_cost)
                    return [], json.dumps(
                        {
                            "status": "fail",
                            "brief": "rate limited",
                            "detail": {
                                "credit_regen_max": {
                                    "value": self.ap_max,
                                    "desc": f"credit会按时间补充，但是最多到达{self.ap_max}",
                                },
                                "credit_regen_daily": {
                                    "value": self.ap_rec * 24 * 3600,
                                    "desc": "恢复速度（24小时）",
                                },
                                "credit_current": ap.update(),
                                "time_needed_regen": {
                                    "value": wait,
                                    "desc": f"等待{_time_str(wait)}后有充足credit执行此操作",
                                },
                            },
                        },
                        ensure_ascii=False,
                    )
                ap.consume(self.ap_cost)

        except RateLimitError as e:
            return [], json.dumps(
                {
                    "status": "fail",
                    "brief": "rate limited",
                    "detail": {
                        "credit_current": e.available,
                        "time_needed_regen": {
                            "value": e.wait_time,
                            "desc": f"等待{_time_str(e.wait_time)}后有充足credit执行此操作",
                        },
                    },
                },
                ensure_ascii=False,
            )

        # 解析宽高比
        if ":" in aspect_ratio:
            w, h = [float(x) for x in aspect_ratio.split(":")]
        else:
            w, h = float(aspect_ratio), 1.0

        # 提交任务并启动后台线程
        def _on_complete():
            try:
                client = SDCPPImageGenClient(
                    prompt=generation_prompt,
                    negative_prompt=final_negative_prompt,
                    width=w,
                    height=h,
                    seed=random.randrange(1 << 10),
                    host=self.host,
                    target_area=self.target_area,
                    payload_override=self.payload_override,
                )
                try:
                    prpt = generation_prompt
                    if (len(prpt) > 100):
                        prpt = prpt[:100] + "..."
                    send_resp_cb(Message(role="assistant", content=[f"🔨图片生成: {prpt}"]))
                except:
                    pass
                status = client.wait_completed()

                if status != "completed":
                    # 失败时返还额度
                    with get_action_point(group_id, "sdcpp_img_gen", self.ap_max, self.ap_rec) as ap:
                        ap.consume(-self.ap_cost)  # 负值 = 返还

                    logger.error(f"Image generation failed for group {group_id}")
                    # 失败通知
                    session.add_message(
                        Message(
                            role="user",
                            content={"type": "img_gen_result", "status": "failed", "prompt": generation_prompt},
                        )
                    )
                    session.respond(send_resp_cb=send_resp_cb)
                    return

                # 成功：保存图片到数据库
                result_imgs = client.get_result()
                image_refs = []
                for img in result_imgs:
                    img_id, _ = save_image_from_pil(img)
                    image_refs.append(ImageRef(img_id))
                if (not image_refs):
                    with get_action_point(group_id, "sdcpp_img_gen", self.ap_max, self.ap_rec) as ap:
                        ap.consume(-self.ap_cost)  # 负值 = 返还
                    session.add_message(
                        Message(
                            role="user",
                            content={"type": "img_gen_result", "status": "failed", "prompt": generation_prompt},
                        )
                    )
                    session.respond(send_resp_cb=send_resp_cb)
                    return
                # 添加完成消息并触发 VLM
                with session.LOCK:
                    session.add_message(
                        Message(
                            role="user",
                            content={
                                "type": "img_gen_result",
                                "prompt": generation_prompt,
                                "generated_images": image_refs,
                                "message": "This message is from tool system. Image generation has completed. You need to send image according to given image content with ids."
                            },
                        )
                    )
                    session.respond(send_resp_cb=send_resp_cb)

            except Exception as e:
                # 异常时返还额度
                try:
                    with get_action_point(group_id, "sdcpp_img_gen", self.ap_max, self.ap_rec) as ap:
                        ap.consume(-self.ap_cost)
                except Exception:
                    pass
                logger.exception(f"Image generation error for group {group_id}: {e}")
                session.add_message(
                    Message(
                        role="user",
                        content={
                            "type": "img_gen_result",
                            "status": "error",
                            "prompt": generation_prompt,
                            "error": str(e),
                        },
                    )
                )
                session.respond(send_resp_cb=send_resp_cb)

        thread = threading.Thread(target=_on_complete, daemon=True)
        thread.start()

        # 立即返回 "已提交"
        return [], {"message": "Image generation task is submitted and running background, image result will come later. Please WAIT and DONOT call tool again for same generation purpose. Please also reassure user about the wait.", "prompt": generation_prompt}
