from PIL import Image
from io import BytesIO
from abc import ABC, abstractmethod
from ...globals.g_cfg import get as get_cfg
import requests, json, base64
from math import sqrt
from openai import OpenAI
import random
from typing import Tuple
def normalize_resolution(w, h, area, mo) -> Tuple[int, int]:
    ratio = sqrt(area/w/h)
    return (round(w*ratio/mo)*mo, round(h*ratio/mo)*mo)

class ImageGeneration(ABC):
    @abstractmethod
    def generate(self) -> Image.Image:
        pass
class ImageGenerationSDCPP(ImageGeneration):
    def __init__(self, base_url, prompt, negative_prompt, width, height, area, patchsize, guidance, seed):
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.width, self.height = normalize_resolution(width, height, area, patchsize)
        self.guidance = guidance
        self.seed = seed
        self.client = OpenAI(api_key="hello", base_url=base_url)
        
    def generate(self):
        pro = self.prompt
        extra_params = {
            "negative_prompt": self.negative_prompt,
            "seed": self.seed
        }
        prompt = pro + "<sd_cpp_extra_args>" + json.dumps(extra_params) + "</sd_cpp_extra_args>"
        resp = self.client.images.generate(prompt=prompt, response_format="b64_json", size=f"{self.width}x{self.height}")
        resp_b64 = resp.data[0].b64_json
        
        resp_bytes = base64.b64decode(resp_b64)
        bio = BytesIO(resp_bytes)
        bio.seek(0)
        im = Image.open(bio)
        
        return im
def create(prompt, negative_prompt, width, height):
    host_type = get_cfg("zimage", "host_type", "sd.cpp")
    if (host_type == "sd.cpp"):
        task = ImageGenerationSDCPP(
            get_cfg("zimage", "host", "http://localhost:8100"),
            prompt,
            negative_prompt,
            width,
            height,
            get_cfg("zimage", "area", 1024*1024),
            64,
            3.5 if negative_prompt else 1,
            random.randrange(1, 1<<10)
        )
        image = task.generate()
        return image
    else:
        raise Exception("Unknown host_type "+host_type)