
class PrintBuf:
    def __init__(self):
        self.buf = []
    def get(self):
        return "".join(self.buf)
    def __call__(self, *args, sep=" ", end="\n"):
        for idx, i in enumerate(args):
            if (idx):
                self.buf.append(sep)
            self.buf.append(str(i))
        self.buf.append(end)
def list_schema_str(obj, indent=0, visited_id=None, max_len=3000):
    if (not obj):
        return "[]"
    if (visited_id is None):
        visited_id = {}
    prt = PrintBuf()
    prt("[ id=%X"%id(obj))
    visited_id[id(obj)] = obj
    ls_repr = []
    if (len(obj)):
        mx_elem = max(max_len//len(obj), 100)
    else:
        mx_elem = max_len
    for i in obj:
        ls_repr.append(obj_schema_str(i, indent+2, visited_id=visited_id, max_len=mx_elem))
    for i in ls_repr:
        if (len(i) > mx_elem):
            i = "..." + i[-mx_elem:]
        prt(" "*(indent+2), i, ",")
    prt(" "*indent+"]", end="")
    return prt.get()
def dict_schema_str(obj, indent=0, visited_id=None, max_len=3000):
    if (visited_id is None):
        visited_id = {}
    prt = PrintBuf()
    prt("{ id=%X"%(id(obj)))
    visited_id[id(obj)] = obj
    kv_repr = []
    if (len(obj)):
        mx_elem = max(max_len//len(obj), 100)
    else:
        mx_elem = max_len
    for k, v in obj.items():
        kv_repr.append((repr(k), obj_schema_str(v, indent+2, visited_id=visited_id, max_len=mx_elem)))
    kv_repr.sort(key=lambda x:len(x[0])+len(x[1]), reverse=True)
    for k_repr, v_repr in kv_repr:
        if (len(v_repr) > mx_elem):
            v_repr = "..." + v_repr[-mx_elem:]
        prt(" "*(indent+2)+k_repr, ':', v_repr)
    prt(" "*indent+"}", end="")
    return prt.get()

def obj_schema_str(obj, indent=0, visited_id=None, max_len=10000):
    if (visited_id is None):
        visited_id = {}
    if (isinstance(obj, dict)):
        return dict_schema_str(obj, indent, visited_id=visited_id, max_len=max_len)
    elif (isinstance(obj, str)):
        return repr(obj)
    elif (isinstance(obj, int)):
        return repr(obj)
    elif (isinstance(obj, list)):
        return list_schema_str(obj, indent, max_len=max_len, visited_id=visited_id)
    elif (isinstance(obj, tuple)):
        return repr(obj)
    elif (obj is None):
        return "None"
    elif (hasattr(obj, "__dict__")):
        if (id(obj) in visited_id):
            return "%s, id=%X, ...(canbe reference cycle)"%(repr(obj), id(obj))
        else:
            visited_id[id(obj)] = obj
            return "%s, id=%X, __dict__ = %s"%(repr(obj), id(obj), obj_schema_str(obj.__dict__, indent=indent, visited_id=visited_id, max_len=max_len))
    else:
        return repr(obj)
if (__name__=="__main__"):
    print(obj_schema_str({"foo": "bar", "alice": {"suki": "bob", "aaa": {"ccc": "ddd"}}}))
    class Foo:
        def __init__(self, data):
            self.data = data
    f1 = Foo("f1")
    f2 = Foo(f1)
    f3 = Foo(f2)
    
    print(obj_schema_str(f3))
    f1.data = f3
    print(obj_schema_str(f3))
