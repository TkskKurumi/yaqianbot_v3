from .volce import volce_ark
import numpy as np
from PIL import Image
from yaqianbot.globals.g_cfg import get as get_cfg
from typing import Optional
from .volce import img2b64url
MODEL = "doubao-embedding-vision-250615"
def img2vec(img: Image.Image):
    b64 = img2b64url(img)
    resp = volce_ark.multimodal_embeddings.create(
        model=MODEL,
        encoding_format="float",
        input=[
            {
                "type": "image_url",
                "image_url": b64
             }
        ]
    )
    print(resp)

def get_embd(*args):
    input = []
    for i in args:
        if (isinstance(i, str)):
            input.append({
                "type": "text","text": i
            })
        elif (isinstance(i, Image.Image)):
            input.append({
                "type": "image_url",
                "image_url": {"url": img2b64url(i)}
            })
   
    resp = volce_ark.multimodal_embeddings.create(
        input=input,
        encoding_format="float",
        model=MODEL,
    )
    # print(resp)
    ret = resp.data.embedding
    return np.asarray(ret).astype(np.float32)