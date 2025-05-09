from requests_cache import SQLiteCache, CachedSession
from . import g_paths
import os
from PIL import Image
from io import BytesIO
from os import path
from datetime import timedelta
SESS = None
def _goc_sess():
    global SESS
    if (SESS is None):
        pth = g_paths.get_file_path("common_requests_cache.sqlite")
        sql = SQLiteCache(pth)
        SESS = CachedSession(backend=sql, expire_after=timedelta(days=30))
    return SESS

def get_image(url):
    sess = _goc_sess()
    r = sess.get(url)
    bio = BytesIO()
    bio.write(r.content)
    bio.seek(0)
    img = Image.open(bio)
    return img
    