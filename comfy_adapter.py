import json
import time
import uuid
from pathlib import Path

import requests


class WorkflowAdapter:
    """把 workflow_profile.json 的语义角色映射到具体节点参数。"""

    def __init__(self, profile_path: str, comfy_url: str = ""):
        if not comfy_url:
            config_path = Path(__file__).with_name("config.json")
            try:
                data = json.loads(config_path.read_text(encoding="utf-8-sig"))
                comfy_url = data.get("comfyui_url", "http://127.0.0.1:8188")
            except Exception:
                comfy_url = "http://127.0.0.1:8188"
                
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

    def set_reference_images(self, image_names: list):
        """
        动态设置参考图。

        image_names: 文件名列表，对应 ComfyUI input 目录下的文件。
        会先清除工作流里已有的 ref_image_* 连接，再按顺序创建新的 LoadImage 节点并接入。
        """
        ref_node_id = None
        for nid, node in self.workflow.items():
            if node.get("class_type") == "MiniMaxH3ReferenceToVideo":
                ref_node_id = nid
                break

        if ref_node_id is None:
            raise KeyError("工作流中找不到 MiniMaxH3ReferenceToVideo 节点")

        inputs = self.workflow[ref_node_id].setdefault("inputs", {})

        # 清除旧的 ref_image_* 连接
        for key in list(inputs.keys()):
            if key.startswith("ref_images.ref_image_"):
                del inputs[key]

        # 为每个图片创建 LoadImage 节点并连接
        for i, image_name in enumerate(image_names):
            load_node_id = f"dyn_load_ref_{i}"
            self.workflow[load_node_id] = {
                "inputs": {"image": image_name},
                "class_type": "LoadImage",
                "_meta": {"title": f"动态参考图 {i}"},
            }
            inputs[f"ref_images.ref_image_{i}"] = [load_node_id, 0]

    def _unique_prefix(self) -> str:
        return f"h3_{self.run_id}"

    def submit(self) -> str:
        self.set("filename_prefix", self._unique_prefix())
        resp = requests.post(
            f"{self.comfy_url}/prompt",
            json={"prompt": self.workflow},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["prompt_id"]

    def wait(self, prompt_id: str, timeout_seconds: int = 3600, interval: int = 5) -> dict:
        """
        等待 ComfyUI 完成任务。

        - 单次 /history 请求失败不判定任务失败，继续轮询。
        - 超时后主动中断 ComfyUI 任务，避免"放弃等待但任务还在跑"占用显存。
        """
        start = time.time()
        last_error = None

        while time.time() - start < timeout_seconds:
            try:
                resp = requests.get(
                    f"{self.comfy_url}/history/{prompt_id}",
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                if prompt_id in data:
                    return data[prompt_id]
                last_error = None
            except requests.exceptions.RequestException as exc:
                last_error = exc
                print(f"  [warn] /history 请求失败，继续等待：{type(exc).__name__}")
            time.sleep(interval)

        # 超时了，主动中断 ComfyUI 的任务，避免它继续占用显存
        print(f"  [timeout] 主动中断 ComfyUI 任务 {prompt_id}")
        try:
            requests.post(
                f"{self.comfy_url}/interrupt",
                timeout=10,
            )
        except Exception as exc:
            print(f"  [warn] /interrupt 失败：{type(exc).__name__}")
        try:
            requests.post(
                f"{self.comfy_url}/queue",
                json={"delete": [prompt_id]},
                timeout=10,
            )
        except Exception as exc:
            print(f"  [warn] /queue 删除失败：{type(exc).__name__}")

        raise TimeoutError(
            f"等待 {timeout_seconds} 秒仍未完成，prompt_id={prompt_id}（已请求中断）"
            + (f"，最后一次错误：{last_error}" if last_error else "")
        )

    def find_output(self, wait_seconds: int = 60) -> Path:
        """
        在 output_dir 下按本次 run 的 prefix 找最终视频文件。

        VHS_VideoCombine 会先落 preview .png，再异步用 ffmpeg 编码 .mp4，
        因此不能见到任何文件就返回，必须等到 mp4 出现。

        优先级：
            1. *-audio.mp4   （合并音频后的完整视频）
            2. *.mp4
            3. 其它          （超时兜底，通常是 .png 预览图）
        """
        output_dir = Path(self.profile["output_dir"])
        prefix = self._unique_prefix()

        start = time.time()
        last_seen = []

        while time.time() - start < wait_seconds:
            matches = sorted(output_dir.rglob(f"{prefix}*"))
            last_seen = matches

            audio_mp4 = [
                p for p in matches if p.name.endswith("-audio.mp4")
            ]
            if audio_mp4:
                return audio_mp4[0]

            mp4s = [
                p for p in matches if p.suffix.lower() == ".mp4"
            ]
            if mp4s:
                return mp4s[0]

            time.sleep(1)

        if last_seen:
            return last_seen[0]

        raise FileNotFoundError(
            f"在 {output_dir} 下没找到 {prefix}* 的文件。"
            "请确认 profile 里的 output_dir 指向 ComfyUI 的 output 目录。"
        )

    def run_once(self, wait_seconds: int = 3600) -> Path:
        prompt_id = self.submit()
        print(f"[submit] prompt_id = {prompt_id}")
        self.wait(prompt_id, timeout_seconds=wait_seconds)
        path = self.find_output()
        print(f"[done] {path}")
        return path