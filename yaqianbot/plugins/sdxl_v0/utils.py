from io import BytesIO
import requests, random
from typing import List, Dict
from PIL import Image
import numpy as np
import os
from math import sqrt
def noise_as_image(noise: np.ndarray):
    noise = (noise-noise.min())/(noise.max()-noise.min())*255
    return Image.fromarray(noise.astype(np.uint8))
def upload_image_get_id(host, im, lossless=False):
    if (("A" in im.mode) or (im.mode=="P") or lossless):
        fmt = "PNG"
        fmt_kwa = {}
        fn = "data.png"
    else:
        fmt = "JPEG"
        fmt_kwa = {"quality": 98}
        fn = "data.png"
    bio = BytesIO()
    im.save(bio, format=fmt, **fmt_kwa)
    bio.seek(0)
    files = {"data": (fn, bio)}
    r = requests.post(f"{host}/upload_image", files=files)
    if (r.status_code==201):
        return r.json()["image_id"]
    else:
        r.raise_for_status()
def pop_none(d):
    for k, v in list(d.items()):
        if (v is None):
            d.pop(k)
    return d
def bytes_as_image(bytes):
    bio = BytesIO()
    bio.write(bytes)
    bio.seek(0)
    im = Image.open(bio)
    return im
def save_image(img, pth):
    os.makedirs(os.path.dirname(pth), exist_ok=True)
    img.save(pth)
    print(pth)

def l2norm(pts, keepdims=False):
    return np.sqrt(np.square(pts).sum(axis=-1, keepdims=keepdims))
def kmeans(points, k, dist_m="euler"):
    # pt_ls = list(points)
    # pts = random.sample(pt_ls, 2)
    # pts = np.ar
    pts = np.array(points[:k])
    last_cluster = None
    for i in range(1000):
        cluster_idx = [list() for i in range(k)]
        cluster_sum = [0 for i in range(k)]
        for idx, p in enumerate(points):
            if (dist_m == "euler"):
                dist = pts-p
                dist = np.sqrt(np.square(dist).sum(axis=-1))
            else:
                dist = (pts*p).sum(axis=-1)
                dist = dist/l2norm(pts)/l2norm(p)
                dist = 1-dist
            best = np.argmin(dist)
            cluster_idx[best].append(idx)
            cluster_sum[best] = cluster_sum[best] + p
        for idx in range(k):
            if (not cluster_idx[idx]):
                pts[idx] = 0
            else:
                pts[idx] = cluster_sum[idx] / len(cluster_idx[idx])
        if (cluster_idx==last_cluster):
            break
        else:
            last_cluster = cluster_idx
    return pts

def img2colors(img: Image.Image, n: int, mode="RGB"):
    m = round(max(sqrt(n*n*0.5), sqrt(n*2)))
    img = img.resize((m, m), Image.Resampling.LANCZOS).convert(mode)
    arr = np.asarray(img).astype(np.float32)
    colors = arr.reshape((-1, arr.shape[-1]))
    return kmeans(colors, n)


