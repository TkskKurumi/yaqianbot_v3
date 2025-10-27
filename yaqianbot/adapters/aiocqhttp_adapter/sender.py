from ..base_adapter import BaseSender
from ...globals import g_requests_cache
from ...globals import g_cfg

from aiocqhttp import CQHttp
class CQSender(BaseSender):
    @classmethod
    def from_onebot(cls, onebot, event):
        uid = str(event["user_id"])
        if (event["message_type"] == "group"):
            gid = event["group_id"]
        else:
            gid = f"private-{uid}"
        if (event["sender"].get("card", "")):
            uname = event["sender"]["card"]
        else:
            uname = event["sender"]["nickname"]
        return cls(onebot, event, uid, gid, uname)
    def __init__(self, onebot, event, uid, group_id, username):
        self.onebot = onebot
        self.event = event
        self.uid = uid
        self.group_id = group_id
        self.username = username
    def get_avatar(self):
        url = r"http://q.qlogo.cn/headimg_dl?dst_uin=%s&spec=640&img_type=jpg"%(self.uid)
        return g_requests_cache.get_image(url)
    def get_group_avatar(self):
        url = r"http://p.qlogo.cn/gh/%s/%s/0"%(self.group_id, self.group_id)
        return g_requests_cache.get_image(url)
    @property
    def gender_str(self):
        return self.event.get("sender", {}).get("gender", "unknown")
    @property
    def group_privilege(self):
        if (self.group_id == "private"):
            return "private_chat"
        ob: CQHttp = self.onebot

        kwargs = {}
        def f(**kwa):
            kwargs.update(kwa)
        f(group_id=self.group_id, user_id=self.uid)
        if ("self_id" in self.event):
            f(self_id=self.event["self_id"])
        info = ob.sync.get_group_member_info(**kwargs)
        return info.get("role", "unknown")