import json
import time
import uuid
from pathlib import Path

import requests


class WorkflowAdapter:
    """把 workflow_profile.json 的语义角色映射到具体节点参数。"""

    def __init__(self, profile_path: str, comfy_url: str = "http://127.0.0.1:8188"):
        self.comfy_url = comfy_url.rstrip("/")
        self.profile = json.loads(
            Path(profile_path).read_text(encoding="utf-8-sig")
        )
        self.workflow_path = Path(profile_path).with_name(
            self.profile["workflow_file"]
        )
        self.workflow = json.loads(
            self.workflow_path.read_text(encoding="utf-8-sig")
        )
        self.roles = self.profile["roles"]
        self.run_id = uuid.uuid4().hex[:8]

    def set(self, role: str, value):
        if role not in self.roles:
            raise KeyError(
                f"profile 里没有角色 {role!r}。"
                f"当前可用：{sorted(self.roles)}"
            )
        spec = self.roles[role]
        node_id = spec["node"]
        param = spec["param"]
        if node_id not in self.workflow:
            raise KeyError(f"工作流里没有节点 {node_id}（角色 {role}）")
        self.workflow[node_id]["inputs"][param] = value

    def set_many(self, **kwargs):
        for role, value in kwargs.items():
            self.set(role, value)

    def _unique_prefix(self) -> str:
        return f"h3_{self.run_id}"

    def submit(self) -> str:
        self.set("filename_prefix", self._unique_prefix())
        resp = requests.post(
            f"{self.comfy_url}/prompt",
            json={"prompt": self.workflow},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["prompt_id"]

    def wait(self, prompt_id: str, timeout_seconds: int = 1800, interval: int = 3) -> dict:
        start = time.time()
        while time.time() - start < timeout_seconds:
            resp = requests.get(
                f"{self.comfy_url}/history/{prompt_id}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if prompt_id in data:
                return data[prompt_id]
            time.sleep(interval)
        raise TimeoutError(
            f"等待 {timeout_seconds} 秒仍未完成，prompt_id={prompt_id}"
        )

    def find_output(self, wait_seconds: int = 10) -> Path:
        """在 output_dir 下按本次 run 的 prefix 找文件。"""
        output_dir = Path(self.profile["output_dir"])
        prefix = self._unique_prefix()

        start = time.time()
        while time.time() - start < wait_seconds:
            matches = sorted(output_dir.rglob(f"{prefix}*"))
            if matches:
                return matches[-1]
            time.sleep(1)

        raise FileNotFoundError(
            f"在 {output_dir} 下没找到 {prefix}* 的文件。"
            "请确认 profile 里的 output_dir 指向 ComfyUI 的 output 目录。"
        )

    def run_once(self, wait_seconds: int = 1800) -> Path:
        prompt_id = self.submit()
        print(f"[submit] prompt_id = {prompt_id}")
        self.wait(prompt_id, timeout_seconds=wait_seconds)
        path = self.find_output()
        print(f"[done] {path}")
        return path