from .client_sdcpp import normalize_resolution, ImageGeneration
from openai import OpenAI
import json, base64, random
import numpy as np
from PIL import Image
from io import BytesIO
from ...globals.g_cfg import get as get_cfg
from typing import List
from math import sqrt
class ImageEdit(ImageGeneration):
    pass

def img2bytes(img: Image.Image, max_bytes=float("inf")):
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
class ImageEditSDCPP(ImageEdit):
    def __init__(self, base_url, prompt, images: List[Image.Image], area, patchsize, seed):
        self.prompt = prompt
        self.seed = seed
        self.client = OpenAI(api_key="hello", base_url=base_url)
        self.images = images
        self.area = area
        self.patchsize = patchsize
    def get_image_input(self):
        im0 = next(iter(self.images))
        w, h = im0.size
        w, h = normalize_resolution(w, h, self.area, self.patchsize)
        ar1 = w/h
        def res(i: Image.Image):
            ar0 = i.width/i.height
            if (max(ar0/ar1, ar1/ar0) > 1.1):
                i = i.convert("RGB")
                col = [int(j) for j in np.asarray(i).astype(np.uint8).mean(axis=0).mean(axis=0)]
                print(col)
                im1 = Image.new("RGB", (w, h), tuple(col))
                if (ar0 > ar1): # too wide
                    im0 = i.resize((w, round(w/ar0)))
                else:
                    im0 = i.resize((round(h*ar0), h))
                left, top = (w-im0.width)//2, (h-im0.height)//2
                im1.paste(im0, (left, top))
                return im1
            else:
                return i.resize((w, h))


        return (w, h, [img2bytes(res(i))[2] for i in self.images])
    def generate(self):
        pro = self.prompt
        extra_params = {
            "negative_prompt": "",
            "seed": self.seed
        }
        prompt = pro + "<sd_cpp_extra_args>" + json.dumps(extra_params) + "</sd_cpp_extra_args>"

        w, h, images = self.get_image_input()
        resp = self.client.images.edit(image=images, prompt=prompt, response_format="b64_json", size=f"{w}x{h}")
        resp_b64 = resp.data[0].b64_json
        
        resp_bytes = base64.b64decode(resp_b64)
        bio = BytesIO(resp_bytes)
        bio.seek(0)
        im = Image.open(bio)
        
        return im
    
def create(prompt, images):
    host_type = get_cfg("zimage", "edit", "host_type", "sd.cpp")
    if (host_type == "sd.cpp"):
        task = ImageEditSDCPP(
            base_url=get_cfg("zimage", "edit", "host", "http://localhost:8101"),
            prompt=prompt,
            images=images,
            area=get_cfg("zimage", "edit", "area", 512*1024),
            patchsize=get_cfg("zimage", "edit", "patchsize", 32),
            seed=random.randrange(1<<10)
        )
        image = task.generate()
        return image
    else:
        raise Exception("Unknown host_type "+host_type)