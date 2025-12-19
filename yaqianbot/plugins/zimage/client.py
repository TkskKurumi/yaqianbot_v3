import requests
from PIL import Image
from io import BytesIO
import time
import json

class Task:
    def __init__(self, prompt, width=None, height=None, aspect_ratio=None, host="http://localhost:8100"):
        self.prompt = prompt
        self.host = host
        self.width = width
        self.height = height
        self.aspect_ratio = aspect_ratio
        resp = requests.post(f'{host}/create', json=self.asdict())
        if (resp.status_code==201):
            self.task_id = resp.json()["task_id"]
        else:
            print(resp.json())
            resp.raise_for_status()
        


    def asdict(self):
        def pop_none(d):
            return {k: v for k, v in d.items() if v is not None}
        return pop_none({
            "prompt": self.prompt,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio
        })
    def get_status(self):
        resp = requests.get(f"{self.host}/status/{self.task_id}")
        if (resp.status_code == 404):
            return "fail", "not found"
        else:
            return resp.json()["status"], resp.json().get("error", None)
    def get_result_block(self):
        while (True):
            st, reason = self.get_status()
            if (st == "fail"):
                raise Exception(reason)
            elif (st == "done"):
                break
            else:
                print(st, reason)
                time.sleep(1)
    def get_bytes(self):
        resp = requests.get(f"{self.host}/image/{self.task_id}")
        if (resp.status_code==200):
            return True, resp.content
        else:
            return False, resp.json()
    def get_pil(self):
        ok, bytes = self.get_bytes()
        if (not ok):
            raise Exception("Generate fail")
        bio = BytesIO()
        bio.write(bytes)
        bio.seek(0)
        return Image.open(bio)
    def save_image(self, pth=None):
        
        success, data = self.get_bytes()
        if (success):
            if (pth is None):
                pth = f"./{self.task_id}.jpg"
            with open(pth, "wb") as f:
                f.write(data)
            return True, pth
        else:
            if (pth is None):
                pth = f"./s{self.task_id}.json"
            with open(pth, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return False, pth
if __name__ == "__main__":
    task = Task("两个人正在性爱，女方的一条腿被抬起、架在男方的手臂上，男方从侧面将阴茎插入阴道。男方的脸在画面外不可见。", 1024, 1024)
    task.get_result_block()
    success, pth = task.save_image()
    print(pth)