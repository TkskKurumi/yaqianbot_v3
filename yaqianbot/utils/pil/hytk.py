import numpy as np
from PIL import Image

# [0, 1] bound
def hytk_1ch(arr_dark, arr_light, bound):
    # A    : x * alpha             = arr_dark * bound
    # B    : x * alpha + (1-alpha) = arr_light * (1-bound) + bound
    # A-B  : alpha-1 = arr_dark * bound - arr_light * (1-bound) - bound
    # C    : alpha   = arr_dark * bound - arr_light * (1-bound) - bound + 1
    # C->A : x = arr_dark * bound / alpha
    alpha = arr_dark * bound - arr_light * (1-bound) - bound + 1
    
    x = arr_dark * bound / alpha
    x[alpha==0] = arr_dark[alpha==0]
    return x, alpha
def dot(x, y):
    return np.sum(x*y)
def solve_pxy(p: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """
    返回标量 a, b 最小化 ||a*x + b*y - p||
    
    参数:
        p, x, y: 向量 (ndarray)
        
    返回:
        (a, b): 最优系数
    """
    # 计算所有必要的内积
    S_xx = np.dot(x, x)
    S_xy = np.dot(x, y)
    S_yy = np.dot(y, y)
    S_xp = np.dot(x, p)
    S_yp = np.dot(y, p)
        
    # 检查矩阵是否可逆
    det = S_xx * S_yy - S_xy * S_xy
    
    # 处理退化情况
    if np.abs(det) < 1e-12:  # 接近奇异
        # 检查是否两个向量都为零
        if S_xx < 1e-12 and S_yy < 1e-12:
            return 0.0, 0.0
        
        # 如果 x 是零向量，只在 y 上投影
        if S_xx < 1e-12:
            b = S_yp / S_yy if S_yy > 1e-12 else 0.0
            return 0.0, b
        
        # 如果 y 是零向量，只在 x 上投影
        if S_yy < 1e-12:
            a = S_xp / S_xx if S_xx > 1e-12 else 0.0
            return a, 0.0
        
        # 向量共线的情况 - 有无穷多解，返回一个特解
        # 令 b = 0，在 x 上投影
        a = S_xp / S_xx
        return a, 0.0
    
    # 一般情况：解线性方程组
    # 使用显式公式或线性求解器
    # 这里使用显式公式
    a = (S_yy * S_xp - S_xy * S_yp) / det
    b = (S_xx * S_yp - S_xy * S_xp) / det
    
    return float(a), float(b)


def solve_c_by_alpha(alpha, c0, c1):
    # alpha = c0 * cm0 + c1*cm1
    cm0, cm1 = solve_pxy(alpha, c0, 1-c1)
    if (cm0 == 0):
        c = c1
    else:
        c = c0*cm0/alpha
        c[alpha==0] = c[alpha==0]
    return c, c0*cm0+(1-c1)*cm1, cm0, cm1

def hytk_1ch_max(c0, c1, bound):
    # A    : x * alpha             = arr_dark * bound
    # B    : x * alpha + (1-alpha) = arr_light * (1-bound) + bound
    # A-B  : alpha-1 = arr_dark * bound - arr_light * (1-bound) - bound
    # C    : alpha   = arr_dark * bound - arr_light * (1-bound) - bound + 1
    # C->A : x = arr_dark * bound / alpha
    alpha = c0+1-c1
    alpha = np.minimum(alpha, 1)
    c, cm0, cm1 = solve_c_by_alpha(alpha, c0, c1)
    x = arr_dark * bound / alpha
    x[alpha==0] = arr_dark[alpha==0]
    return x, alpha

def hytk_rgb(rgb_dark: np.ndarray, rgb_light, bound):
    r0, g0, b0 = rgb_dark.transpose((2, 0, 1))
    r1, g1, b1 = rgb_light.transpose((2, 0, 1))
    r, ar = hytk_1ch(r0, r1, bound)
    g, ag = hytk_1ch(g0, g1, bound)
    b, ab = hytk_1ch(b0, b1, bound)
    a = (ar+ag+ab)/3
    a[a==0] = 1
    
    
    # r0/r1/r: 红色里图/表图/输出
    # rmap0/rmap1: 里图变暗程度(1最亮最好看)，表图变亮程度(1最暗最好看)
    # alpha: alpha输出
    # A: r * alpha           = r0 * rmap0
    # B: r * alpha + 1-alpha = 1 - (1-r1)*rmap1
    # 联立rgb三个通道，应该是有约束的优化问题。
    # A-B+1: alpha = r0*rmap0 -r1*rmap1+rmap1 = r0*rmap0 + (1-r1)*rmap1
    #        alpha = g0*gmap0 + (1-g0)*gmap1
    # 1-B = 1-r1*rmap1-1+rmap1 = (1-r1)*rmap1
    def calc_score(rmap0, rmap1, gmap0, bmap0):

        def cosine_dist(a, b):
            a_norm = np.sqrt(np.sum(np.square(a)))
            b_norm = np.sqrt(np.sum(np.square(b)))
            dot = (a*b).sum()
            cosine = dot/(a_norm+1e-8)/(b_norm+1e-8)
            return (1-cosine)/2
        def pen_bound(a):
            a1 = np.clip(a, a_min=0, a_max=1)
            return a1, 

        alpha = r0*rmap0 + (1-r1)*rmap1
        r = r0*rmap0/alpha
        g = g0*gmap0/alpha
        b = b0*bmap0/alpha
        r[alpha==0] = r0[alpha==0]
        g[alpha==0] = g0[alpha==0]
        b[alpha==0] = g0[alpha==0]

        score += rmap0*rmap0 + rmap1*rmap1 + gmap0*gmap0 + bmap0*bmap0
        
        gmap1 = (alpha-g0*gmap0)/(1-g0)
        gmap1: np.ndarray = np.nan_to_num(gmap1, nan=0, posinf=1, neginf=0)
        gmap1_scoring = np.clip(gmap1, a_min=0, a_max=1)
        score += gmap1_scoring.mean()*gmap1_scoring.mean()
        glit = g0*gmap0 + 1-alpha
        gpen = cosine_dist(glit, 1-g1)
        score -= gpen*gpen
        
        bmap1 = (alpha-b0*bmap0)/(1-b0)
        bmap1: np.ndarray = np.nan_to_num(bmap1, nan=0, posinf=1, neginf=0)
        bmap1_scoring = np.clip(bmap1, a_min=0, a_max=1)
        score += bmap1_scoring.mean()*bmap1_scoring.mean()
        blit = b0*bmap0 + 1-alpha
        bpen = cosine_dist(blit, 1-g1)
        score -= bpen*bpen

        return r, g, b, alpha, score
        # (1-g0)*gmap1 = alpha-g0*gmap0
        # cost = 
        

    # r * alpha             = r0 * rb0
    # -> alpha = r0 * rb0 / r
    # -> rb0 = r * alpha / r0
    # r*alpha = r0 * rb0
    
    # r * alpha + (1-alpha) = r1 * (1-rb1) + rb1
    # -> (r-1)*alpha =  r1 * (1-rb1) + rb1 - 1
    # -> alpha = (r1 * (1-rb1) + rb1 - 1) / (r-1) = (rb1-1)*(1-r1)/(r-1)

    # r * alpha + (1-alpha) = r1 * (1-rb1) + rb1
    # 1-rb1 = (1-r) * alpha / (1-r1)
    # alpha*(1-r) = (1-r1)*(1-rb1)

    
    # alpha =    r0  *    rb0  /    r
    #       = (1-r1) * (1-rb1) / (1-r)
    # r = r0 / alpha * rb0[0~1] 
    # r = 1 -  (1-r1) / alpha * (1-rb1)[0~1]
    # 1 = (1-r1)/alpha * (1-rb1) + r0/alpha*rb0
    # alpha = (1-r1) * A + r0*B
    #       = (1-g1) * C + g0*D
    #       = (1-b1) * D + g0*E
    
    if (True):
        r_min = np.maximum(0, 1 - (1-r1)/a)
        r_max = np.minimum(1, r0/a)
        r = (r_min+r_max)/2
        
        g_min = np.maximum(0, 1 - (1-g1)/a)
        g_max = np.minimum(1, g0/a)
        g = (g_min+g_max)/2

        b_min = np.maximum(0, 1 - (1-b1)/a)
        b_max = np.minimum(1, b0/a)
        b = (b_min+b_max)/2
        

    # dark_mapped  = x * alpha             = arr_dark  * bound_dark
    # light_mapped = x * alpha + (1-alpha) = arr_light * (1-bound_light) + bound_light


    return np.stack([r, g, b, a], axis=-1)



def hytk_rgb(rgb_dark: np.ndarray, rgb_light, bound):
    r0, g0, b0 = rgb_dark.transpose((2, 0, 1))
    r1, g1, b1 = rgb_light.transpose((2, 0, 1))
    r, ar = hytk_1ch(r0, r1, bound)
    g, ag = hytk_1ch(g0, g1, bound)
    b, ab = hytk_1ch(b0, b1, bound)
    a = (ar+ag+ab)/3
    a[a==0] = 1
    def dot(arr, brr):
        return np.sum(arr*brr)
    def l2norm(arr):
        return np.sqrt(np.sum(np.square(arr)))
    
    def sanfen(func, le, ri, iter_num=10):
        for i in range(iter_num):
            p0 = le+(ri-le)/3
            p1 = ri+(le-ri)/2
            score0 = func(p0)
            score1 = func(p1)
            if (score0>score1):
                le = p0
            else:
                ri = p1
        return (le+ri)/2


    def best_cmap(alpha, c0, c1):
        def cmap1_for_least_alpha_diff(cmap0):
            # alpha_r ~ alpha_c = c0*cmap0 + (1-c1)*cmap1
            # alpha_r - c0*cmap0 ~ (1-c1)*cmap1
            y = alpha - c0*cmap0
            x = (1-c1)
            if (l2norm(x)<1e-8):
                cmap1 = 0
                alpha_loss = l2norm(y)
                return cmap1, alpha_loss
            else:
                cmap1 = dot(y, x) / dot(x, x)
                alpha_loss = l2norm(y-cmap1*x)
                return cmap1, alpha_loss
        cmap0 = sanfen(lambda x:cmap1_for_least_alpha_diff(x)[-1], 0, 1)
        cmap1, loss = cmap1_for_least_alpha_diff(cmap0)
        # print(cmap0, cmap1, loss)
        return cmap0, cmap1, loss

    rmap0, rmap1, loss = best_cmap(a, r0, r1)
    gmap0, gmap1, loss = best_cmap(a, g0, g1)
    bmap0, bmap1, loss = best_cmap(a, b0, b1)
    print(rmap0, rmap1)
    print(gmap0, gmap1)
    print(bmap0, bmap1)
    r = np.clip(r0*rmap0/a, a_max=1, a_min=0)
    g = np.clip(g0*gmap0/a, a_max=1, a_min=0)
    b = np.clip(b0*bmap0/a, a_max=1, a_min=0)
    return np.stack([r, g, b, a], axis=-1)


        
def hytk_rgb_2(rgb_dark: np.ndarray, rgb_light, it=5):
    r0, g0, b0 = rgb_dark.transpose((2, 0, 1))
    r1, g1, b1 = rgb_light.transpose((2, 0, 1))
    def dot(arr, brr):
        return np.sum(arr*brr)
    def l2norm(arr):
        return np.sqrt(np.sum(np.square(arr)))
    def zero_to(arr, to):
        ret = arr.copy()
        ret[ret==0] = to
        return ret
    def mse(arr, brr):
        return np.mean(np.square(arr*brr))
    
    def sanfen_mini(func, le, ri, iter_num=it):
        for i in range(iter_num):
            p0 = le+(ri-le)/3
            p1 = ri+(le-ri)/3
            score0 = func(p0)
            score1 = func(p1)
            # print(msg, p0, score0, p1, score1)
            if (score0>score1):
                le = p0
            else:
                ri = p1
        # print("best = ", (le+ri)/2)
        return (le+ri)/2
    def scoring_func(rmap0, rmap1, gmap0, gmap1, bmap0, bmap1):
        alpha_r = r0*rmap0 + (1-r1)*rmap1
        alpha_g = g0*gmap0 + (1-g1)*gmap1
        alpha_b = b0*bmap0 + (1-b1)*bmap1
        r = r0*rmap0/zero_to(alpha_r, 1)
        g = g0*gmap0/zero_to(alpha_g, 1)
        b = b0*bmap0/zero_to(alpha_b, 1)
        a = (alpha_r+alpha_g+alpha_b)/3
        score = sum(i*i for i in [max(rmap0, rmap1), max(gmap0, gmap1), max(bmap0, bmap1)])
        # score = sum([rmap0, rmap1, gmap0, gmap1, bmap0, bmap1])
        # score -= mse(alpha_r, a)
        # score -= mse(alpha_g, a)
        # score -= mse(alpha_b, a)
        
        print(score, rmap0, rmap1, gmap0, gmap1, bmap0, bmap1)
        return score, rmap0, rmap1, gmap0, gmap1, bmap0, bmap1, r, g, b, a
    def best_bmap1(rmap0, rmap1, gmap0, gmap1, bmap0):
        __scoring_func = lambda bmap1: scoring_func(rmap0, rmap1, gmap0, gmap1, bmap0, bmap1)
        _scoring_func = lambda bmap1: -__scoring_func(bmap1)[0]
        bmap1 = sanfen_mini(_scoring_func, 0, 1, it)
        return __scoring_func(bmap1)
    def best_bmap0(rmap0, rmap1, gmap0, gmap1):
        __scoring_func = lambda bmap0: best_bmap1(rmap0, rmap1, gmap0, gmap1, bmap0)
        _scoring_func = lambda bmap0: -__scoring_func(bmap0)[0]
        bmap0 = sanfen_mini(_scoring_func, 0, 1, it)
        return __scoring_func(bmap0)
    def best_gmap1(rmap0, rmap1, gmap0):
        __scoring_func = lambda gmap1: best_bmap0(rmap0, rmap1, gmap0, gmap1)
        _scoring_func = lambda gmap1: -__scoring_func(gmap1)[0]
        gmap1 = sanfen_mini(_scoring_func, 0, 1, it)
        return __scoring_func(gmap1)
    def best_gmap0(rmap0, rmap1):
        __scoring_func = lambda gmap0: best_gmap1(rmap0, rmap1, gmap0)
        _scoring_func = lambda gmap0: -__scoring_func(gmap0)[0]
        gmap1 = sanfen_mini(_scoring_func, 0, 1, it)
        return __scoring_func(gmap1)
    def best_rmap1(rmap0):
        __scoring_func = lambda rmap1: best_gmap0(rmap0, rmap1)
        _scoring_func = lambda rmap1: -__scoring_func(rmap1)[0]
        rmap1 = sanfen_mini(_scoring_func, 0, 1, it)
        return __scoring_func(rmap1)
    def best_rmap0():
        __scoring_func = lambda rmap0: best_rmap1(rmap0)
        _scoring_func = lambda rmap0: -__scoring_func(rmap0)[0]
        rmap0 = sanfen_mini(_scoring_func, 0, 1, it)
        return __scoring_func(rmap0)
    return best_rmap0()

def hytk_rgb_3(rgb_dark: np.ndarray, rgb_light, bound, iter_num=5, dead=0.1):

    r0, g0, b0 = rgb_dark.transpose((2, 0, 1))
    r1, g1, b1 = rgb_light.transpose((2, 0, 1))
    m0, m1 = bound-dead/2, (1-bound)-dead/2
    ar = r0*m0+(1-r1)*m1
    ag = g0*m0+(1-g1)*m1
    ab = b0*m0+(1-b1)*m1
    a = (ar+ag+ab)/3
    a[a==0] = 1
    def dot(arr, brr):
        return np.sum(arr*brr)
    def l2norm(arr):
        return np.sqrt(np.sum(np.square(arr)))
    
    EPS = 0.05
    def sanfen(func, le, ri):
        nonlocal EPS
        while (le+EPS<ri):
            p0 = le+(ri-le)/3
            p1 = ri+(le-ri)/2
            score0 = func(p0)
            score1 = func(p1)
            if (score0>score1):
                le = p0
            else:
                ri = p1
        return (le+ri)/2


    def best_cmap(alpha, c0, c1):
        def cmap1_for_least_alpha_diff(cmap0):
            # alpha_r ~ alpha_c = c0*cmap0 + (1-c1)*cmap1
            # alpha_r - c0*cmap0 ~ (1-c1)*cmap1
            y = alpha - c0*cmap0
            x = (1-c1)
            if (l2norm(x)<1e-8):
                cmap1 = 0
                alpha_loss = l2norm(y)
                return cmap1, alpha_loss
            else:
                cmap1 = dot(y, x) / dot(x, x)
                alpha_loss = l2norm(y-cmap1*x)
                return cmap1, alpha_loss
        cmap0 = sanfen(lambda x:cmap1_for_least_alpha_diff(x)[-1], 0, 1)
        cmap1, loss = cmap1_for_least_alpha_diff(cmap0)
        # print(loss)
        return cmap0, cmap1, loss
    for i in range(iter_num):
    # for EPS in [0.2, 0.1, 0.05, 0.02, 0.01, 0.001, 0.0001]:
        rmap0, rmap1, lr = best_cmap(a, r0, r1)
        gmap0, gmap1, lg = best_cmap(a, g0, g1)
        bmap0, bmap1, lb = best_cmap(a, b0, b1)
        alpha_r = r0*rmap0 + (1-r1)*rmap1
        alpha_g = g0*gmap0 + (1-g1)*gmap1
        alpha_b = b0*bmap0 + (1-b1)*bmap1
        if (False):
            a = (alpha_r*lr+alpha_g*lg+alpha_b*lb)/(lr+lg+lb)
        else:
            a = (alpha_r+alpha_g+alpha_b)/3
        a[a==0] = 1
        print(EPS, lr+lg+lb, a.mean())
    return np.stack([r0*rmap0/a, g0*gmap0/a, g0*bmap0/a, a], axis=-1)
if (__name__=="__main__"):
  
    a = Image.open(r"E:\Pics\__nikaido_hiro_mahou_shoujo_no_majo_saiban_drawn_by_umemaro_siona0908__c95a4c5fcb0d7eda487629dce481bada.jpg").convert("RGB")
    # a = a.resize((8, 8))
    b = Image.open(r"E:\Pics\__sakuraba_ema_mahou_shoujo_no_majo_saiban_drawn_by_umemaro_siona0908__7b680dae72dd592d517b888078b2ea80.jpg").resize(a.size).convert("RGB")

    a_arr = np.asarray(a)/255
    b_arr = np.asarray(b)/255

    arr = hytk_rgb_3(a_arr, b_arr, 0.5, iter_num=10)
    arr = np.clip(arr, a_min=0, a_max=1)

    im = Image.fromarray((arr*255).astype(np.uint8), "RGBA")
    im.save("tmp1.png")
    im1 = im.convert("RGB").save("tmp2.png")