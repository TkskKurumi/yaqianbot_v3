from PIL import Image
from openai import OpenAI
from typing import Dict, Optional
from yaqianbot.globals.g_cfg import get as get_cfg
from ...database.image import (
    get_img_info_recur as db_get_img_info_recur,
    set_img_info_recur as db_set_img_info_recur
)
from ...utils import img2b64url
from openai import APIConnectionError

API_KEY = get_cfg("vl_model", "api_key", "")
BASE_URL = get_cfg("vl_model", "base_url", "http://192.168.31.175:12355/v1")
MODEL = get_cfg("vl_model", "model", "qwen/qwen3-vl-30b")