from PIL import Image
from openai import OpenAI
from typing import Dict, Optional
from yaqianbot.globals.g_cfg import get as get_cfg
from ..database.image import (
    get_img_info_recur as db_get_img_info_recur,
    set_img_info_recur as db_set_img_info_recur
)
from ..utils import img2b64url
from openai import APIConnectionError
# from ..message.mseg_img import MSEGImage

API_KEY = get_cfg("vl_model", "api_key", "")
BASE_URL = get_cfg("vl_model", "base_url", "http://192.168.31.175:12355/v1")
MODEL = get_cfg("vl_model", "model", "qwen/qwen3-vl-30b")
DB_CACHE_KEY = get_cfg("vl_model", "db_cache_key", "qwen/qwen3-vl-30b-q6")
MAX_BYTES = get_cfg("vl_model", "image_max_bytes", 500000)
CLIENT = OpenAI(api_key=API_KEY, base_url=BASE_URL)

PROMPT_DEFAULT = """
详细描述此图片。
包括图片内容。
包括图片分类（手机截图、游戏截图、二次元插画、漫画、人物照片、风景照片、表情包等）。
若接收到色情元素也请你描述内容，这是用于moderation检测目的，务必不要过滤输出。
按以下等级分类检测色情与否：非色情、性感、性暗示、显式色情。
""".strip()

GROUNDING_PROMPT = """
描述图片，并检测图片中的各个物件，并且配合bbox。输出json格式。注意，可以用来进行色情敏感内容检测和moderation，所以请务必不要对敏感内容进行过滤，输出所有内容。
输出的格式例如：
{
    "description": "请详细描述图片的内容。如果是游戏内容，请寻找并描述操作光标所在位置。",
    "grounding": [
        {
        "bbox": [left_x, upper_y, right_x, lower_y],
        "content": "第一分镜，内容是一个怎么怎么样的女角色（针对漫画）"
        },
        {
            "bbox": "...",
            "content": "对话框，文字内容为：我..喜欢你。（针对漫画）"
        },
        {
            "bbox": "...",
            "content": "确认按钮（针对界面截图类）"
        },
        {
            "bbox": "...",
            "content": "输入文字框（针对界面截图类）"
        },
        {
            "bbox": "...",
            "content": "女主角形象，她穿着...外貌...（针对游戏截图，分析构图、理解游戏世界内的几何信息位置关系）（游戏场景中定位）"
        },
        {
            "bbox": "...",
            "content": "桌子（游戏场景中定位）"
        },
        {
            "bbox": "...",
            "content": "怪兽（游戏场景中定位）"
        },
        {
            "bbox": "...",
            "content": "可拾取素材（游戏场景中定位）"
        },
        {
            "bbox": "...",
            "content": "角色的右眼，瞳孔是蓝色的...（针对插画图片，分析构图）"
        },
        {
            "bbox": "...",
            "content": "戴在角色头上的黑色的帽子...（针对插画图片，分析构图）"
        }    
    ]
}

以上仅作格式示例，具体内容视图片内容而定、详细标注出图片各组成部分。不需要太过详细、最多输出50个物件。
""".strip()

class Message:
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
                "image_url": {"url": img2b64url(x, MAX_BYTES)}
            }
    def to_openai(self):
        return {
            "role": "user",
            "content": [self._content_to_openai(i) for i in self.contents]
        }

def one_image_desc(image_pil: Image.Image, prompt=PROMPT_DEFAULT, image_id: Optional[str]=None, force_refresh=False):
    if (image_id is not None):
        if (not force_refresh):
            db_cached = db_get_img_info_recur(image_id, "vl_model", DB_CACHE_KEY, prompt, None)
            if (db_cached is not None):
                return db_cached
    msgs = [Message(prompt, image_pil).to_openai()]
    kwargs = get_cfg("vl_model", "extra_kwargs", {})
    try:
        resp = CLIENT.chat.completions.create(
            messages=msgs,
            model=MODEL,
            top_p=0.001,
            max_tokens=2048,
            stream=False,
            **kwargs
        )
    except APIConnectionError as e:
        print("BASE_URL", BASE_URL)
        raise e

    resp_msg = resp.choices[0].message.content

    if (image_id is not None):
        print(image_id)
        db_set_img_info_recur(image_id, "vl_model", DB_CACHE_KEY, prompt, resp_msg)
    return resp_msg

