from PIL import Image
import numpy as np
import random, math
from PIL import ImageFilter
from math import sqrt
from .hytk import hytk_rgb
# paste upper with mask = upper, result is not desired when 'upper has pixel which alpha in (0, 255) and color not equal lower color'
# lets say, lower is (0, 0, 0, 0)
# upper is (255, 255, 255, 128)
# color becomes (128, 128, 128, 128) instead of (255, 255, 255, 128)
# thus we need alpha_composite to replace paste

def paste(lower, upper, lefttop):
    upper1 = Image.new("RGBA", lower.size, (0, 0, 0, 0))
    upper1.paste(upper, box=lefttop)
    return Image.alpha_composite(lower, upper1)

def image_pal_dot(pil: Image.Image, pal):
    pal = np.array(pal)
    orig = np.asarray(pil).astype(np.float16)
    residual = orig.copy()
    ret = np.zeros_like(orig)
    h, w, ch = orig.shape
    queue = [(y, x) for x in range(w) for y in range(h)]
    neib_dyx = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    vis = set()
    for yx in queue:
        y, x = yx
        vis.add(yx)
        query = residual[y, x]
        distances = np.linalg.norm(pal - query, axis=1)  # shape = (n, )
        min_idx = np.argmin(distances)
        got = pal[min_idx]
        got_residual = residual[y, x] - got
        ret[y, x] = got
        
        neib_yx = []
        for dy, dx in neib_dyx:
            y1, x1 = y+dy, x+dx
            if (y1<0 or x1<0 or h<=y1 or w<=x1):
                continue
            if ((y1, x1) in vis):
                continue
            neib_yx.append((y1, x1))
        if (neib_yx):
            for y1, x1 in neib_yx:
                residual[y1, x1] += got_residual/len(neib_yx)
    im = Image.fromarray(ret.astype(np.uint8))
    return im


def image_randnoise(pil: Image.Image, strength=0.5, mode=0):
    if (mode==0):
        if pil.mode in ["P", "RGBA", "LA"]:
            pil = pil.convert("RGBA")
        else:
            pil = pil.convert("RGB")
        
        arr = np.asarray(pil)
        meow = [0b1, 0b11, 0b111, 0b1111, 0b11111, 0b111111, 0b1111111, 0b1111111, 0b11111111]
        meow = meow[min(int(strength*len(meow)), len(meow)-1)]
        arr = np.bitwise_xor(arr, meow)
        ret = Image.fromarray(arr)
        return ret
    elif (mode==1):
        meow = [0, 127, 255]
        if pil.mode in ["P", "RGBA", "LA"]:
            pil = pil.convert("RGBA")
            cols = [(r, g, b, a) for r in meow for g in meow for b in meow for a in meow]
            ch = 4
            gugugaga = 4**4
        else:
            pil = pil.convert("RGB")
            cols = [(r, g, b) for r in meow for g in meow for b in meow]
            ch = 3
            gugugaga = 4**3
        for i in range(round((1-strength)*gugugaga)):
            cols.append([random.randrange(255) for j in range(ch)])
        print(len(cols))
        return image_pal_dot(pil, cols)
    elif (mode==2):
        if pil.mode in ["P", "RGBA", "LA"]:
            pil = pil.convert("RGBA")
        else:
            pil = pil.convert("RGB")
        w, h = pil.size
        #reduce_fns = [lambda x, y: x, lambda x, y:y, lambda x,y:x+y, lambda x, y:x-y, lambda x,y:np.sqrt(x*x+y*y)]
        reduce_fns = [
            lambda x, y: np.sqrt(np.square(x)+ np.square(y)),
            lambda x, y: np.sqrt(np.square(x)+ np.square(y-h)),
            lambda x, y: np.sqrt(np.square(x-w) + np.square(y)),
            lambda x, y: np.sqrt(np.square(x-w) + np.square(y-h)),
        ]
        def process_one_channel(arr, phase_shift, strength=255):
            h, w = arr.shape
            ret = arr.copy().astype(np.float32)
            tot_scale = sqrt(w*w+h*h)
            # indices[y, x, :] = (y, x)
            indices = np.indices((h, w))
            indices = indices.transpose(1, 2, 0)
            LVL_N = 8
            strength_lvls = [1 for lvl in range(LVL_N)]
            l2norm = sqrt(sum(i*i for i in strength_lvls))
            strength_lvls = [i / l2norm * strength for i in strength_lvls]
            for lvl, strength_lvl in enumerate(strength_lvls):
                freq_2pi = (1<<lvl)*2*math.pi
                for reduce_fn in reduce_fns:
                    reduced = reduce_fn(indices[:,:,0], indices[:,:,1])
                    noise   = np.sin((reduced/tot_scale+phase_shift)*freq_2pi)*strength_lvl
                    ret = ret + noise
                    print(noise.max(), noise.min())
            return ret
        arr = np.asarray(pil)
        ret = []
        h, w, ch = arr.shape
        for i in range(ch):
            if (i<3):
                p0 = process_one_channel(arr[:,:,i], i/3, 90*strength)
                p1 = process_one_channel(arr[:,:,i], 0, 90*strength)
                ret.append((p0 + p1)/2)
            else:
                ret.append(arr[:,:,i])
        ret = np.stack(ret, axis=-1)
        ret = np.clip(ret, a_min=0, a_max=255).astype(np.uint8)
        return Image.fromarray(ret)
    elif (mode==3):
        rgb_pil = pil.convert("RGB")
        w, h = rgb_pil.size
        r = sqrt(w*w+h*h)
        rgb_pil_blur = rgb_pil.filter(ImageFilter.GaussianBlur(r/3*strength+1))
        rgb0 = np.asarray(rgb_pil)/255
        rgb1 = np.asarray(rgb_pil_blur)/255
        rgba = hytk_rgb(rgb0, rgb1, strength)
        rgba = np.clip(rgba, a_min=0, a_max=255)
        return Image.fromarray((rgba*255).astype(np.uint8))
                    


    else:
        if (pil.mode=="P" or "A" in pil.mode):
            pil = pil.convert("RGBA")
        else:
            pil = pil.convert("RGB")
        arr = np.asarray(pil)
        shape = arr.shape
        arr = arr.flatten()
        n = arr.shape[0]
        for i in range(100):
            j = random.randrange(n)
            if (arr[j]>128):
                arr[j] = 0
            else:
                arr[j] = 255
        arr = arr.reshape(shape)
        return Image.fromarray(arr.astype(np.uint8))

if (__name__=="__main__"):
    import time
    im = Image.open(r"C:\Users\TkskKurumi\startup\test_zi\prompt=5=0df5-turbo=True.png")
    t = time.time()
    image_randnoise(im, strength=0.5).show()
    print(time.time()-t)
    t = time.time()
    image_randnoise(im, strength=0.5, mode=2).show()
    print(time.time()-t)