from abc import ABC, abstractmethod

class PluginBase(ABC):
    def __init__(self, cfg):
        self.cfg = cfg
    @abstractmethod
    def register_receivers(self):
        pass
