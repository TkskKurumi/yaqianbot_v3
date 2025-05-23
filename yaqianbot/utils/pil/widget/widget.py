from PIL import Image
from abc import ABC, abstractmethod
def retrieve_callable(obj, **kwargs):
    while (True):
        if (isinstance(obj, list)):
            return [retrieve_callable(i, **kwargs) for i in obj]
        elif (callable(obj)):
            obj = obj(**kwargs)
        else:
            return obj

class Argument:
    def __init__(self, name):
        self.name = name
    def __call__(self, **kwargs):
        return kwargs.get(self.name, None)

class Widget(ABC):
    @abstractmethod
    def __init__(self, *args, **kwargs):
        raise NotImplementedError()
    @abstractmethod
    def render(self, *args, **kwargs):
        raise NotImplementedError()
    def __call__(self, **kwargs) -> Image.Image:
        return self.render(**kwargs)
    def getdefault(self, attr, default, **kwargs):
        ret = self.get(attr, **kwargs)
        if (ret is None):
            return retrieve_callable(default, **kwargs)
        else:
            return ret
    def get(self, attr, **kwargs):
        if (getattr(self, attr, None) is not None):
            return retrieve_callable(getattr(self, attr), **kwargs)
        elif (kwargs.get(attr, None) is not None):
            return retrieve_callable(kwargs[attr], **kwargs)
        else:
            return None