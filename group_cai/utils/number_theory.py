import random
import math
from collections import defaultdict

def miller_rabin(n, k=None):
    """
    Miller-Rabin素性检测
    参数:
        n: 要检测的数
        k: 测试次数，默认为None时会根据n的大小自动选择
    返回:
        bool: 如果n很可能是素数返回True，否则返回False
    """
    if n < 2:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0:
        return False
    
    # 自动选择测试次数
    if k is None:
        if n < 1373653:
            k = 4
        elif n < 25326001:
            k = 5
        elif n < 118670087467:
            k = 12
        else:
            k = 20
    
    # 将n-1写成d*2^s的形式
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    
    def witness(a):
        """见证函数"""
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            return True
        
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                return True
        return False
    
    # 进行k次测试
    for _ in range(k):
        a = random.randint(2, n - 2)
        if not witness(a):
            return False
    
    return True

def pollard_rho(n):
    if n % 2 == 0:
        return 2
    if miller_rabin(n):
        return n

    # 设置最大尝试次数
    for _ in range(10):
        # 随机选择常数 c 和初始值 x
        c = random.randint(1, n-1)
        x = random.randint(2, n-2)
        y = x
        d = 1

        while d == 1:
            x = (x*x + c) % n
            y = (y*y + c) % n
            y = (y*y + c) % n
            d = math.gcd(abs(x-y), n)
            if d == n:
                break  # 退出内层循环，重新选择 c 和 x

        if 1 < d < n:
            return d

    # 如果多次尝试都失败，返回 n，但这种情况应该很少
    return n

def factorize(n):
    if n < 2:
        return {}
    factors = defaultdict(int)
    stack = [n]

    while stack:
        x = stack.pop()
        if miller_rabin(x):
            factors[x] += 1
        else:
            d = pollard_rho(x)
            while d == x:  # 如果分解失败，d 等于 x，则我们尝试用不同的随机种子再次分解
                d = pollard_rho(x)
            stack.append(d)
            stack.append(x // d)

    return dict(factors)

if (__name__=="__main__"):
    print(factorize(2*2*3*5*17*10007))
    print(factorize(123456789123))
    print(factorize(114514))