from typing import Any, Dict, List
from collections import defaultdict
from queue import Queue
INF = float("inf")

# from https://oi-wiki.org/graph/graph-matching/bigraph-weight-match/
# cannot understand at all, just translate to python
class KuhnMunkres:
    def __init__(self):
        self.w = defaultdict(lambda:defaultdict(lambda:0))
    def add_edge(self, le, ri, w):
        self.w[le][ri] = w
        assert w>=0
    def solve_match(self):
        le_keys = set()
        ri_keys = set()
        for le in self.w.keys():
            le_keys.add(le)
            for ri in self.w[le].keys():
                ri_keys.add(ri)
        le_keys = list(le_keys)
        ri_keys = list(ri_keys)

        le2idx = {i:idx for idx, i in enumerate(le_keys)}
        ri2idx = {i:idx for idx, i in enumerate(ri_keys)}

        n = max(len(le_keys), len(ri_keys))
        w_map = defaultdict(lambda:defaultdict(lambda:0))
        lx = []
        for ldx, le in enumerate(le_keys):
            mx = 0
            for ri, w in self.w[le].items():
                rdx = ri2idx[ri]
                w_map[ldx][rdx] = w
                mx = max(mx, w)
            lx.append(mx)
        ly = [0 for i in range(n)]
        # virtual left items
        while (len(lx)<n):
            lx.append(0)


        ri_slack = None
        le_vis = None
        ri_vis = None
        def init():
            nonlocal ri_slack, le_vis, ri_vis, n
            ri_slack = [INF for i in range(n)]
            le_vis = [False for i in range(n)]
            ri_vis = [False for i in range(n)]

        pth = [0 for i in range(n)]
        le_match = [-1 for i in range(n)]
        ri_match = [-1 for i in range(n)]
        q = Queue()
        def check(ri, q):
            ri_vis[ri] = True
            if (ri_match[ri] != -1):
                q.put(ri_match[ri])
                le_vis[ri_match[ri]] = True

                return False
            while (ri != -1):
                # print("check pth", ri)
                le = pth[ri]
                ri_match[ri] = le
                ri, le_match[le] = le_match[le], ri
            return True

        def bfs(i):
            nonlocal q, ri_slack, le_vis, ri_vis
            # print("bfs start slack", ri_slack)
            # print("bfs start vle", le_vis)
            # print("bfs start vri", ri_vis)
            q = Queue()
            q.put(i)
            le_vis[i] = True
            while (1):
                # print("bfs while 1")
                while (not q.empty()):
                    le = q.get()
                    # print("bfs", le)
                    for ri in range(n):
                        if (not ri_vis[ri]):
                            delta = lx[le] + ly[ri] - w_map[le][ri]
                            if (ri_slack[ri] >= delta):
                                pth[ri] = le
                                if (delta):
                                    ri_slack[ri] = delta
                                else:
                                    if (check(ri, q)):
                                        return
                a = INF
                for ri in range(n):
                    if (not ri_vis[ri]):
                        a = min(a, ri_slack[ri])
                # print(a)
                for j in range(n):
                    if (le_vis[j]):
                        lx[j] -= a
                    if (ri_vis[j]):
                        ly[j] += a
                    else:
                        ri_slack[j] -= a
                for ri in range(n):
                    
                    if ((not ri_vis[ri]) and (ri_slack[ri]==0)):
                        chk = check(ri, q)
                        if (chk):
                            return
                    else:
                        # print(f"ri_vis[{ri}]={ri_vis[ri]}, ri_slack={ri_slack[ri]}")
                        pass
        
        for le in range(n):
            init()
            bfs(le)
        ret = []
        for le, le_key in enumerate(le_keys):
            ri = le_match[le]
            if (ri!=-1 and ri<len(ri_keys)):
                ri_key = ri_keys[ri]
                ret.append((le_key, ri_key, w_map[le][ri]))
        return (ret)

if (__name__=="__main__"):
    solver = KuhnMunkres()
    solver.add_edge("foo", "bar", 3)
    solver.add_edge("foo", "dar", 2)
    # print(solver.solve_match())
            
        

                     