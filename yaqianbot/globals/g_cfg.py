CFG = {}
def get(*args):
    dft = args[-1]
    c = CFG
    for i in args[:-1]:
        if (not isinstance(c, dict)):
            return dft
        elif (not i in c):
            return dft
        else:
            c = c[i]
    return c