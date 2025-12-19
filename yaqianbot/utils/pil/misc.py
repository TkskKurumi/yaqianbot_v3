from PIL import Image
import numpy as np
import random
# paste upper with mask = upper, result is not desired when 'upper has pixel which alpha in (0, 255) and color not equal lower color'
# lets say, lower is (0, 0, 0, 0)
# upper is (255, 255, 255, 128)
# color becomes (128, 128, 128, 128) instead of (255, 255, 255, 128)
# thus we need alpha_composite to replace paste

def paste(lower, upper, lefttop):
    upper1 = Image.new("RGBA", lower.size, (0, 0, 0, 0))
    upper1.paste(upper, box=lefttop)
    return Image.alpha_composite(lower, upper1)



def image_randnoise(pil: Image.Image, strength=0.5):
    if (True):
        if pil.mode in ["P", "RGBA", "LA"]:
            pil = pil.convert("RGBA")
        else:
            pil = pil.convert("RGB")
        
        arr = np.asarray(pil)
        meow = [0b1, 0b11, 0b111, 0b1111, 0b11111, 0b111111]
        meow = meow[min(int(strength*len(meow)), len(meow)-1)]
        arr = np.bitwise_xor(arr, meow)
        ret = Image.fromarray(arr)
        return ret
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
    im = Image.open(r"E:\Pics\tmp.gif")
    image_randnoise(im).show()