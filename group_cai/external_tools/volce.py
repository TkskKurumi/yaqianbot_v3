import base64
from PIL import Image
from io import BytesIO
from math import sqrt
from yaqianbot.globals.g_cfg import get as get_cfg
from volcenginesdkarkruntime import Ark

_1M = 1<<20
_500K = 500<<10

def img2bytes(img: Image.Image, max_bytes=_500K):
    if (img.mode == "P"):
        img = img.convert("RGBA")
    if ("A" in img.mode):
        fmt = "PNG"
        kwa = {}
    else:
        fmt = "JPEG"
        kwa = {"quality": 90}
    w, h = img.size
    def to_bytes(ratio):
        w1, h1 = round(ratio*w), round(ratio*h)
        bio = BytesIO()
        img.resize((w1, h1), resample=Image.Resampling.LANCZOS).save(bio, format=fmt, **kwa)
        size = bio.tell()
        
        bio.seek(0)
        data = bio.read()

        bio.seek(0)
        
        return bio, data, size
    
    ratio = 1
    while (ratio*w>1 and ratio*h>1):
        bio, data, size = to_bytes(ratio)
        if (size<=max_bytes):
            return fmt, bio, data, size
        else:
            ratio = min(ratio*0.9, ratio*sqrt(max_bytes/size))
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

def img2b64url(img: Image.Image):
    fmt, bio, data, size = img2bytes(img, max_bytes=_500K)

    if (fmt == "PNG"):
        mime = "image/png"
    elif (fmt == "JPEG"):
        mime = "image/jpeg"
    else:
        raise ValueError("Format="+str(fmt))

    b64 = base64.b64encode(data).decode("ascii")

    url = f"data:{mime};base64,{b64}"
    return url

def img_caption(img: Image.Image, prompt=PROMPT_DEFAULT, prompt_ex=None):
    fmt, bio, data, size = img2bytes(img, max_bytes=_500K)

    if (fmt == "PNG"):
        mime = "image/png"
    elif (fmt == "JPEG"):
        mime = "image/jpeg"
    else:
        raise ValueError("Format="+str(fmt))

    b64 = base64.b64encode(data).decode("ascii")

    url = f"data:{mime};base64,{b64}"

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


