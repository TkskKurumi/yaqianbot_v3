
def hashi(x, length=60):
    ret = 0
    mask = (1<<length) - 1
    def add_data(x):
        nonlocal ret
        if (x<0):
            add_data(100)
            add_data(-x)
            return
        ret = (ret<<5) | x
        while (ret>>length):
            ret = (ret>>length) ^ (ret&mask)
        return ret
    if (isinstance(x, bool)):
        add_data(x)
    elif (isinstance(x, list)):
        add_data(1)
        for i in x:
            add_data(hashi(i))
    elif (isinstance(x, set)):
        add_data(2)
        for i in x:
            add_data(hashi(i))
    elif (isinstance(x, dict)):
        add_data(3)
        for k, v in x.items():
            add_data(hashi(k, length=length))
            add_data(hashi(v, length=length))
    elif (isinstance(x, int)):
        add_data(4)
        add_data(x)
    elif (isinstance(x, float)):
        add_data(5)
        for scale in [1e-8, 1e-4, 1, 1e4, 1e8]:
            add_data(int(x*scale))
    elif (isinstance(x, str)):
        add_data(6)
        for i in x:
            add_data(ord(i))
    else:
        raise TypeError(type(x))
    return ret
def hashs(x, length=15):
    return hex(hashi(x, length=length*4))[2:].zfill(length)
if (__name__=="__main__"):
    print(hashs("abc"))
    print(hashs(114514))
    print(hashs(114514.514))
    print(hashs({"ok": True, "fail": False}))
    print(hashs(-1))