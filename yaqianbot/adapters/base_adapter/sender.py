# from ..base_adapter.message import BaseImage
from abc import ABC, abstractmethod
from ...globals import g_cfg
from .mseg import BaseImage
from typing import Any, Dict
class BaseSender(ABC):
    _recent_images: Dict[Any, BaseImage ] = {}
    def __init__(self, uid, group_id, username):
        self.uid = uid
        self.group_id = group_id
        self.username = username
    @abstractmethod
    def get_avatar(self):
        pass
    @abstractmethod
    def get_group_avatar(self):
        pass
    def set_recent_image(self, image):
        self._recent_images[self.uid] = image
    def get_recent_image(self):
        return self._recent_images[self.uid]
    @property
    def is_su(self):
        return str(self.uid) in g_cfg.CFG.get("superusers", {})
    @property
    def gender_str(self):
        return "UNKNOWN"
    @property
    @abstractmethod
    def group_privilege(self):
        pass