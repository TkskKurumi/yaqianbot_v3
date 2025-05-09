from abc import ABC, abstractmethod
class BaseAdapter:
    @abstractmethod
    def __init__(self, config):
        pass
    
    @abstractmethod
    def get_async_start_stop(self):
        return None

    @abstractmethod
    def get_sync_start_stop(self):
        return None
