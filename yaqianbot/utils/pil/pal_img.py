import numpy as np
from PIL import Image
import random
from tqdm import tqdm
def kmeans(points, k, max_it = 10, early_stop_acc=0.9):
    n, dim = points.shape
    centers = np.array([points[random.randrange(n)] for i in range(k)])
    close_idx = [i%k for i in range(n)]
    for i in range(max_it):
        if (False):
            print(centers)
        chg = 0
        clu_sum = [0 for i in range(k)]
        clu_num = [0 for i in range(k)]
        diff = points.reshape((n, 1, dim))-centers.reshape((1, k, dim))
        dist = np.sum(np.square(diff), axis=-1)
        close_idx1 = np.argmin(dist, axis=-1)
        for j in range(n):
            idx = close_idx1[j].item()
            if (idx != close_idx[j]):
                chg += 1
                close_idx[k] = idx
            close_idx[j] = idx
            clu_sum[idx] += points[j]
            clu_num[idx] += 1
        for j in range(k):
            if (clu_num[j]):
                centers[j] = clu_sum[j]/clu_num[j]
            else:
                centers[j] = points[random.randrange(n)]
        if (not chg):
            break
        else:
            acc = (n-chg)/n
            print("Acc %.1f%%"%((n-chg)/n*100))
            if (acc>early_stop_acc):
                break
    return centers, clu_num, close_idx
        
            


def img_pal(image: Image.Image, k=None, min_area=None):
    image_arr = np.asarray(image).astype(np.float32)
    h, w, ch = image_arr.shape
    area = h*w
    image_colors = image_arr.reshape((area, ch))
    if (min_area is not None):
        k = max(2, round(1/min_area/2))
        while (k>=2):
            centers, clu_num, close_idx = kmeans(image_colors, k)
            clu_min_area = min(clu_num)/area
            print(f"k={k}, clu_min_area={clu_min_area}")
            if (clu_min_area<min_area):
                if (k==2):
                    break
                else:
                    k = max(2, min(k-1, round(k*clu_min_area/min_area)))
            else:
                break
    elif (k is not None):
        centers, clu_num, close_idx = kmeans(image_colors, k)
    else:
        raise ValueError("Either k or min_area should be specified")

    img_col1 = np.array([centers[i] for i in close_idx])
    img_arr1 = img_col1.reshape((h, w, ch))
    img1 = Image.fromarray(img_arr1.astype(np.uint8))
    return centers, clu_num, close_idx, img1
if (__name__=="__main__"):
    img_pal(Image.open(r"E:\Pics\53eafb554033b9a863c61be268b5f42715168109.png"), k=8)[-1].show()
    # img_pal(Image.open(r"E:\Pics\53eafb554033b9a863c61be268b5f42715168109.png"), min_area=0.05)[-1].show()
