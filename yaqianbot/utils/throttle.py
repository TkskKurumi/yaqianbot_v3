from collections import deque
from threading import RLock
import time
from contextlib import contextmanager
class Throttle:
    def __init__(self, period, num):
        self.lck = RLock()
        self.q = deque()
        self.period = period
        self.num = num
    @contextmanager
    def throttled(self):
        self.wait()
        self.add()
        try:
            yield
        except Exception:
            pass
    def wait(self):
        with self.lck:
            while (len(self.q) >= self.num):
                t = self.q[0]
                wait = t+self.period-time.time()
                if (wait>0):
                    print("Throttled")
                    time.sleep(wait)
                if (self.q[0] + self.period < time.time()):
                    self.q.popleft()
    def add(self):
        with self.lck:
            self.q.append(time.time())
if (__name__=="__main__"):
    t = Throttle(period=1, num=5)
    for i in range(100):
        t.wait()
        t.add()
        print(time.time())
    
    