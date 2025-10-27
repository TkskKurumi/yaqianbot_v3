from threading import Lock
from annoy import AnnoyIndex
from typing import Tuple, List
import heapq
from threading import RLock
NTREES = 10
SEARCH_K = 50
class AnnoyBlock:
    def __init__(self, vecs, idx_offset, method):
        vec0 = next(iter(vecs))
        ndims = len(vec0)
        self.ann = AnnoyIndex(ndims, method)
        for idx, v in enumerate(vecs):
            try:
                self.ann.add_item(idx, v)
            except TypeError as e:
                print("ERROR adding vec", idx, v)
                raise e

        self.ann.build(NTREES)
        self.vecs = vecs
        self.idx_offset = idx_offset
    @property
    def size(self):
        return len(self.vecs)
    @property
    def idx_tail(self):
        return self.idx_offset + len(self.vecs)-1
    def get_nns_by_vector(self, vec, n):
        if (not n):
            return []
        items, dists = self.ann.get_nns_by_vector(vec, n, include_distances=True, search_k=SEARCH_K)
        ret = [(dist, items[idx]+self.idx_offset) for idx, dist in enumerate(dists)]
        if (not ret):
            print("get n:", n)
            print("self size", self.size)
            print("self vecs", self.vecs[:10])
            print("vec size", vec.shape)
            print("self vec size", self.vecs[0].shape)

        assert ret, "returnning empty"

        return ret
    def get_item_vector(self, idx):
        if (idx<self.idx_offset or self.idx_tail<idx):
            raise IndexError(idx)
        return self.ann.get_item_vector(idx-self.idx_offset)
class DynAnnoy:
    def __init__(self, vecs=None, met="angular"):
        self._lock = RLock()
        self.met = met
        self._build(vecs)
    def _build(self, vecs):
        self._blocks: List[AnnoyBlock] = []
        if (vecs is None):
            return
        if (len(vecs) == 0):
            return

        block_vecs = []
        n = len(vecs)
        bit = 1
        while(bit<=n):
            if (n&bit):
                blk = vecs[n-bit:n]
                n -= bit
                block_vecs.append(blk)
            bit = bit<<1
        block_vecs = block_vecs[::-1]
        offset = 0
        for blk in block_vecs:
            newblock = AnnoyBlock(blk, offset, self.met)
            self._blocks.append(newblock)
            offset = self._blocks[-1].idx_tail+1
        
    def push_back(self, vec):
        with self._lock:
            return self._push_back(vec)
    def _push_back(self, vec):
        if (not self._blocks):
            offset = 0
        else:
            offset = self._blocks[-1].idx_tail + 1
        newblock = AnnoyBlock([vec], offset, self.met)
        self._blocks.append(newblock)
        self._merge_tail_blocks()
        return self._get_size()-1
    def _merge_tail_blocks(self):
        while (len(self._blocks) >= 2):
            block0, block1 = self._blocks[-1], self._blocks[-2]
            if (block0.size != block1.size):
                break
            self._blocks.pop()
            self._blocks.pop()

            vecs = block1.vecs + block0.vecs
            
            if (self._blocks):
                offset = self._blocks[-1].idx_tail + 1
            else:
                offset = 0
            newblock = AnnoyBlock(vecs, offset, self.met)
            self._blocks.append(newblock)
    def _get_size(self):
        if (not self._blocks):
            return 0
        else:
            return self._blocks[-1].idx_tail+1
    def _get_nns_by_vector(self, vec, n):
        n = min(self._get_size(), n)
        if (n == 0) :
            return []

        pq = []
        for i in self._blocks:
            m = min(n, i.size)
            items = i.get_nns_by_vector(vec, m)[::-1]
            if (items):
                pq.append((items[-1], items))
        heapq.heapify(pq)
        # print(pq)
        ret = []
        while (len(ret) < n and pq):
            top = heapq.heappop(pq)
            item, remain = top
            ret.append(item)
            remain.pop()
            if (remain):
                heapq.heappush(pq, (remain[-1], remain))
        assert ret
        return ret
    def get_nns_by_vector(self, vec, n):
        with self._lock:
            return self._get_nns_by_vector(vec, n)

    def _get_item_vector(self, idx):
        for i in self._blocks:
            if (i.idx_offset <= idx and idx <= i.idx_tail):
                return i.get_item_vector(idx)
        raise IndexError(idx)

    def get_item_vector(self, idx):
        with self._lock:
            return self._get_item_vector(idx)
    @property
    def size(self):
        with self._lock:
            return self._get_size()
        
    
if (__name__=="__main__"):
    import numpy as np
    vecs = np.random.normal(size=(50, 10))
    ann = DynAnnoy(vecs)
    # vec0 = np.random.normal(size=(10, ))
    vec0 = vecs[0]
    print(vec0)
    print(ann.get_nns_by_vector(vec0, 1))
    print(ann.get_nns_by_vector(vec0, 50))
    # print(ann._blocks[0].get_nns_by_vector(vec0, 10))
    # print(ann._blocks[0].get_nns_by_vector(vec0, 1))