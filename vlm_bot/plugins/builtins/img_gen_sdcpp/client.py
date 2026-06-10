"""SDCPP Image Generation Client.

封装 /sdcpp/v1/img_gen API（submit task + poll 模式）。
"""

import base64
import time
from io import BytesIO
from typing import List, Optional
import requests
from PIL import Image


# ──────────────────────────────────────────────
# 全局默认值
# ──────────────────────────────────────────────

DEFAULT_HOST = "http://192.168.31.117:1235"
DEFAULT_TARGET_AREA = 512 * 1024


def _normalize_resolution(width: int, height: int, target_area: int) -> tuple:
    """根据宽高比和目标像素面积，计算归一化的分辨率。"""
    ratio = width / height
    h = int((target_area / ratio) ** 0.5)
    w = int(h * ratio)
    # 对齐到 8 的倍数（SD 常见要求）
    w = (w // 8) * 8
    h = (h // 8) * 8
    return w, h


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典。"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class SDCPPImageGenClient:
    """SDCPP /sdcpp/v1/img_gen API 客户端。

    Parameters
    ----------
    prompt : str
        图像生成的文本提示词。
    negative_prompt : str
        负面提示词。
    width, height : float
        目标宽高比（会被 normalize_resolution 归一化）。
    seed : int
        随机种子。
    host : str
        SDCPP 服务器地址。
    target_area : int
        目标像素面积。
    payload_override : dict | None
        可选的 payload 覆盖/合并。
    """

    def __init__(
        self,
        prompt: str,
        negative_prompt: str,
        width: float,
        height: float,
        seed: int = 42,
        host: str = DEFAULT_HOST,
        target_area: int = DEFAULT_TARGET_AREA,
        payload_override: Optional[dict] = None,
    ):
        self._host = host
        self._target_area = target_area
        self._payload_override = payload_override
        self._prompt = prompt
        self._negative_prompt = negative_prompt
        self._width = width
        self._height = height
        self._seed = seed
        self._job_id: Optional[str] = None
        self._poll_url: Optional[str] = None
        self._result_images: Optional[List[Image.Image]] = None
        self._status: Optional[str] = None

        self._create_task()

    def _create_task(self):
        """提交图像生成任务。"""
        # 获取服务器默认参数
        cap = requests.get(self._host + "/sdcpp/v1/capabilities").json()
        defaults = cap["defaults"]

        # 计算分辨率
        w, h = _normalize_resolution(int(self._width), int(self._height), self._target_area)

        payload = _deep_merge(
            defaults,
            {
                "prompt": self._prompt,
                "negative_prompt": self._negative_prompt,
                "width": w,
                "height": h,
                "seed": self._seed,
            },
        )

        if self._payload_override:
            payload = _deep_merge(payload, self._payload_override)

        r = requests.post(self._host + "/sdcpp/v1/img_gen", json=payload)
        r.raise_for_status()
        body = r.json()
        self._job_id = body["id"]
        self._poll_url = self._host + body["poll_url"]

    def poll_status(self) -> str:
        """单次查询任务状态。

        Returns
        -------
        status : "completed" | "failed" | "queued" | "generating"
        """
        r = requests.get(self._poll_url)
        r.raise_for_status()
        body = r.json()
        self._status = body["status"]

        if self._status == "completed":
            self._result_images = []
            for img_info in body["result"]["images"]:
                img_b64 = img_info["b64_json"]
                img_bytes = base64.b64decode(img_b64)
                bio = BytesIO(img_bytes)
                bio.seek(0)
                self._result_images.append(Image.open(bio))

        return self._status

    def wait_completed(self, interval: float = 2.0) -> str:
        """阻塞式轮询直到任务完成或失败。

        Parameters
        ----------
        interval : float
            轮询间隔（秒）。

        Returns
        -------
        status : "completed" | "failed"
        """
        while True:
            status = self.poll_status()
            if status in ("completed", "failed"):
                return status
            if status not in ("queued", "generating"):
                raise ValueError(f"Unknown job status: {status}")
            time.sleep(interval)

    def get_result(self, wait: bool = True) -> List[Image.Image]:
        """返回生成的 PIL Image 列表。

        Parameters
        ----------
        wait : bool
            是否等待完成。
        """
        if wait:
            if self.wait_completed() == "failed":
                raise Exception("Image generation failed")
        if self._result_images is None:
            raise RuntimeError("No result available — call wait_completed() or poll_status() first")
        return self._result_images
