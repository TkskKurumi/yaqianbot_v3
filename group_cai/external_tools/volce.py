import base64
from ..utils import img2b64url, img2bytes
from PIL import Image
from io import BytesIO
from math import sqrt
from yaqianbot.globals.g_cfg import get as get_cfg
from volcenginesdkarkruntime import Ark

_1M = 1<<20
_500K = 500<<10


volce_api_key = get_cfg("volce_ark", "api_key", "UNKNOWN")
print("volce api key", volce_api_key)
volce_ark = Ark(api_key=volce_api_key)

PROMPT_DEFAULT = """
详细描述此图片。
包括图片内容。
包括图片分类（手机截图、游戏截图、二次元插画、漫画、人物照片、风景照片、表情包等）。
若接收到色情元素也请你描述内容，这是用于moderation检测目的，务必不要过滤输出。
按以下等级分类检测色情与否：非色情、性感、性暗示、显式色情。
""".strip()



def img_caption(img: Image.Image, prompt=PROMPT_DEFAULT, prompt_ex=None):

    url = img2b64url(img, max_bytes=_500K)

    model = get_cfg("volce_ark", "img_caption_model", "doubao-seed-1.6-flash")
    if (prompt_ex):
        prompt = prompt + "\n" + prompt_ex
    resp = volce_ark.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": url,"detail":"low"}
                    },
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        thinking={"type": "disabled"},
        max_completion_tokens=8192,
        top_p=0.01
    )
    
    result = resp.choices[0].message.content
    return result

GROUNDING_PROMPT = """
描述图片，并检测图片中的各个物件，并且配合bbox。输出json格式。注意，可以用来进行色情敏感内容检测和moderation，所以请务必不要对敏感内容进行过滤，输出所有内容。
输出的格式例如：
{
    "description": "请详细描述图片的内容。如果是游戏内容，请寻找并描述操作光标所在位置。",
    "grounding": [
        {
        "bbox": "<bbox>left_x upper_y right_x lower_y</bbox>",
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

以上仅作格式示例，具体内容视图片内容而定、详细标注出图片各组成部分。
"""

