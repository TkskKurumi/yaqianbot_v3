import shlex

def parse(args, kw_options=None, list_options=None, bool_options=None):
    if (isinstance(args, str)):
        args = shlex.split(args)
    if (kw_options is None):
        kw_options = set()
    if (list_options is None):
        list_options = set()
        kw_options.update(list_options)
    if (bool_options is None):
        bool_options = set()
        kw_options.update(bool_options)
    
    pargs = []
    kwargs = dict()
    kw = None
    for i in args:
        if(i.startswith("-") and (i in kw_options)):
            if(i in bool_options):
                kwargs[i]=True
            else:
                kw = i
        else:
            if(kw is not None):
                
                if(kw in list_options):
                    kwargs[kw] = kwargs.get(kw, [])
                    kwargs[kw].append(i)
                else:
                    kwargs[kw] = i
                    kw = None
            else:
                pargs.append(i)
    
    return pargs, kwargs
if (__name__=="__main__"):
    print(parse("fuck -n 10 -w 100"))
    print(parse("fuck -n 10 \n -w 100 \"\n\""))
