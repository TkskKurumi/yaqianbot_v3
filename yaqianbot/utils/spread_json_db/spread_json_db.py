import json
from os import path
from threading import RLock
import os
import glob
from typing import Dict
def _ensure_dir(pth):
    os.makedirs(path.dirname(pth), exist_ok=True)



class Spreaded:
    def __init__(self, pth):
        self._loaded = False
        self._data = None
        self.pth = pth
    def _load(self):
        if (self._loaded):
            return self._data
        elif (path.exists(self.pth)):
            with open(self.pth, "r") as f:
                data = json.load(f)
            self._data = data
            self._loaded = True
            return self._data
        else:
            self._data = {}
            self._loaded = True
            return self._data
    def _save(self):
        if (not self._loaded):
            return
        try:
            _ensure_dir(self.pth)
        except Exception as e:
            print("pth = ", self.pth)
            raise e
        with open(self.pth, "w") as f:
            json.dump(self._data, f)
    def __getitem__(self, key):
        self._load()
        return self._data[key]
    def __setitem__(self, key, value):
        self._load()
        self._data[key] = value
        self._save()
    def pop(self, key, value):
        self._load()
        ret = self._data.pop(key, value)
        self._save()
        return ret
    def __contains__(self, key):
        return key in self._load()
        
class SpreadJson:
    _cls_lck = RLock()
    _opened = {}
    @classmethod
    def open(cls, dir, split_method=lambda x: str(x[0])):
        if (dir in cls._opened):
            return cls._opened[dir]
        ret = cls(dir, split_method=split_method)
        cls._opened[dir] = ret
        return ret
    def __init__(self, dir, split_method=lambda x: str(x)[0]):
        self.dir = dir
        self.lck = RLock()
        self.split_method = split_method
        self.spreads: Dict[str, Spreaded] = {}
    def _get_skey_pth(self, key):
        skey = self.split_method(key)
        pth = path.join(self.dir, skey+".json")
        return key, skey, pth
    def _get_spread(self, key):
        key, skey, pth = self._get_skey_pth(key)
        if (skey in self.spreads):
            return self.spreads[skey]
        self.spreads[skey] = Spreaded(pth)
        return self.spreads[skey]
    def __iter__(self):
        with self.lck:
            vis = set()
            for skey in self.spreads:
                vis.add(skey)
                for k in self.spreads[skey]._load():
                    yield k
            for pth in glob.glob(path.join(self.dir, "*.json")):
                skey = path.splitext(path.basename(pth))[0]
                if (skey in vis):
                    continue
                self.spreads[skey] = Spreaded(pth)
                for k in self.spreads[skey]._load():
                    yield k
    def items(self):
        with self.lck:
            for k in self:
                yield (k, self[k])
    def __getitem__(self, key):
        with self.lck:
            spr = self._get_spread(key)
            return spr[key]
    def __setitem__(self, key, value):
        with self.lck:
            spr = self._get_spread(key)
            spr[key] = value
    def __contains__(self, key):
        with self.lck:
            spr = self._get_spread(key)
            return key in spr
    def get(self, key, dft):
        with self.lck:
            spr = self._get_spread(key)
            if (key in spr):
                return spr[key]
            return dft
    
    def pop(self, key, dft):
        with self.lck:
            spr = self._get_spread(key)
            return spr.pop(key, dft)
if (__name__=="__main__"):
    import time
    tmp = SpreadJson("./tmp")
    if ("foo" in tmp):
        print("foo", tmp["foo"])
    tmp["foo"] = "tm=%s"%time.time()
    tmp["abc"] = "abc=%s"%time.time()
    for i, j in tmp.items():
        print("item:", i, j)
    tmp.pop("abc", "meow")
    print("poped")
    for i, j in tmp.items():
        print("item:", i, j)
    