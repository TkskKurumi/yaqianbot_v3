from ..external_tools import volce_embd
from ..external_tools import volce_img_caption
from ..database.image import (
    get_img_data as db_get_img_data,
    get_img_info as db_get_img_info,
    update_img_info as db_update_img_info
)
from ..database import image as image_db
from typing import Optional, Dict
from PIL import Image
from io import BytesIO
import numpy as np
import base64, json
import random, traceback
from .ann import DynAnnoy
from ..utils import bytes2pil
from threading import RLock
from yaqianbot.globals.g_cfg import get as get_cfg
def embd2b64(embd: np.ndarray):
    bytes = embd.astype(np.float32).tobytes()
    return base64.b64encode(bytes).decode("ascii")
def b642embd(b64):
    bytes = base64.b64decode(b64)
    return np.frombuffer(bytes, np.float32)
def image_id2pil(image_id):
    data = db_get_img_data(image_id)
    if (data is None):
        raise Exception(f"Cannot load image by id {image_id}")
    return bytes2pil(data)
def volce_goc_img_desc(image_id):
    if (db_get_img_info(image_id, "desc", None) is not None):
        return db_get_img_info(image_id, "desc", None)
    desc = volce_img_caption(image_id2pil(image_id))
    db_update_img_info(image_id, {"desc": desc})
    return desc
def volce_get_img_embd(image_id: Optional[str]=None, image_pil: Optional[Image.Image]=None):
    if (image_id is not None):
        cached_embd = db_get_img_info(image_id, "embds", {})
        if (volce_embd.MODEL in cached_embd):
            return b642embd(cached_embd[volce_embd.MODEL])
    if (image_pil is not None):
        pil = image_pil
    else:
        data = db_get_img_data(image_id)
        if (data is None):
            raise Exception("Cannot load image with id %s"%image_id)
        bio = BytesIO()
        bio.write(data)
        bio.seek(0)
        pil = Image.open(bio)
    
    embd = volce_embd.get_embd(pil)
    if (image_id is not None):
        cached_embd = db_get_img_info(image_id, "embds", {})
        cached_embd[volce_embd.MODEL] = embd2b64(embd)
        db_update_img_info(image_id, {"embds": cached_embd})
    return embd
def volce_img_match_desc(image_id, *all_desc):
    cached_desc: Dict[str, float] = db_get_img_info(image_id, "volce_match_desc", {})
    query_desc = set(all_desc)-set(cached_desc.keys())

    if (not query_desc):
        return cached_desc
    PROMPT = "请你为图片打分，范围0~1，0表示完全不符合描述，1表示完全符合描述。返回的结果符合json格式、不需要任何额外输出、只包含json body、包含且只包含以下示例的keys、为它们填充实际的value："
    PROMPT = PROMPT + "{" + ", ".join(f'{json.dumps(i, ensure_ascii=False)}: float' for i in query_desc) + "}"
    print("PROMPT: ", PROMPT)
    ok = False
    fail_reason = ""
    for i in range(2):
        try:
            resp_content = volce_img_caption(image_id2pil(image_id), PROMPT)
            resp_dict = json.loads(resp_content)
        except json.decoder.JSONDecodeError:
            fail_reason = "volce returning syntax error "+resp_content
            continue
        ok = True
        if (not isinstance(resp_dict, dict)):
            ok = False
            fail_reason = "volce returning object type not dict: %s"%resp_dict
            continue
        for k in query_desc:
            if (k not in resp_dict):
                fail_reason = "required field not found %s in %serror"%(k, resp_dict)
                ok = False
                break
        for k, v in resp_dict.items():
            if (not isinstance(v, (int, float))):
                fail_reason = "returning rating not number %s"%v
                ok = False
                break
            if (v<0 or 1<v):
                fail_reason = "returning rating overflow %s"%v
                ok = False
                break
        if (ok):
            break
    if (ok):
        cached_desc.update(resp_dict)
        db_update_img_info(image_id, {"volce_match_desc": cached_desc})
        return cached_desc
    else:
        raise Exception(fail_reason)



def cosine_sim(a, b):
    ret = np.dot(a, b)/np.linalg.norm(a)/np.linalg.norm(b)
    return (ret+1)/2 # [-1, 1] -> [0, 1]
DIST_EPS = 1e-3
class ImageIndex:
    def __init__(self):
        self.lck = RLock()
        self.image_id2idx = {}
        self.ann = DynAnnoy()
        self.pils = []
        self.image_ids = []
    @property
    def n(self):
        return len(self.pils)
    def add_image(self, image_id: str, image_pil: Image.Image):
        with self.lck:
            vec = volce_get_img_embd(image_id, image_pil)
            nns = self.ann.get_nns_by_vector(vec, 1)
            if (nns and nns[0][0] < DIST_EPS):
                self.image_id2idx[image_id] = nns[0][-1]
            else:
                self.image_ids.append(image_id)
                self.pils.append(image_pil)
                idx = self.ann.push_back(vec)
                self.image_id2idx[image_id] = idx
                return idx
    def find_nns_by_embd(self, embd, k=1):
        with self.lck:
            ret0 = self.ann.get_nns_by_vector(embd, k)
            ret1 = []
            for angular_dist, idx in ret0:
                hit_embd = self.ann.get_item_vector(idx)
                ret1.append((cosine_sim(embd, hit_embd), idx))
            return ret1
    def find_by_desc(self, desc, k=5, min_cosine=0.6, min_verify=0.9):
        with self.lck:
            embd_desc = volce_embd.get_embd(desc)
            nns = self.find_nns_by_embd(embd_desc, k=k)
            ret = []
            for cosine_sim, idx in nns:
                if (cosine_sim > min_cosine):
                    try:
                        desc_dict = volce_img_match_desc(self.image_ids[idx], desc)
                        if (desc_dict[desc] > min_verify):
                            ret.append(self.image_ids[idx])
                    except Exception:
                        traceback.print_exc()
                        continue
            if (ret):
                return random.choice(ret)
            return None

INDEX = ImageIndex()
def add_image(image_id):
    image_pil = image_id2pil(image_id)
    INDEX.add_image(image_id, image_pil)
def find_image_by_desc(*descs):
    min_num = get_cfg("image_index_min_num", 128)
    if (INDEX.n < min_num):
        for i in range(min_num - INDEX.n):
            try:
                image_id = image_db.rand_img()
                add_image(image_id)
            except Exception:
                pass
    if (not INDEX.n):
        return
    for desc in descs:
        found = INDEX.find_by_desc(desc, k=10)
        if (found):
            return found
