"""
阶段 1：FastAPI 薄包装。

只暴露只读状态 + comfyui 配置读写，不接生成、不接写工具。
复用 app.py 里的私有扫描函数，避免重复实现。
阶段 2 会把 _read_episode_id / _scan_segments / _read_marks / _segment_status
抽到独立模块，消除 `import app` 时构建 Gradio UI 的副作用。
"""

import copy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import app as app_module


fastapi_app = FastAPI(title="Reelwright API", version="0.1.0")

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _collect_episode_status() -> dict:
    """与 app.inspect_episode 的返回结构保持一致。"""
    episode = app_module._read_episode_id()
    segments = app_module._scan_segments()
    marks = app_module._read_marks()
    liked_keys = set(marks.get("liked", []))

    out = []
    for seg in segments:
        status = app_module._segment_status(seg["id"], liked_keys)
        out.append({
            "id": seg["id"],
            "duration": seg["duration"],
            "views": seg["views"],
            "narrative_goal": seg["narrative_goal"],
            **status,
        })

    return {
        "episode": episode,
        "segment_count": len(segments),
        "segments": out,
    }


def _redact_config(config: dict) -> dict:
    """返回给前端前抹掉 api_key，避免泄露。"""
    safe = copy.deepcopy(config)
    providers = safe.get("providers")
    if isinstance(providers, dict):
        for name, data in providers.items():
            if isinstance(data, dict):
                data["api_key"] = "***" if data.get("api_key") else ""
    return safe


@fastapi_app.get("/api/health")
def health():
    return {"ok": True, "service": "reelwright-api"}


@fastapi_app.get("/api/status")
def get_status():
    return _collect_episode_status()


@fastapi_app.get("/api/config")
def get_config():
    return _redact_config(app_module._read_config())


class ConfigUpdate(BaseModel):
    comfyui_path: str | None = None
    comfyui_url: str | None = None


@fastapi_app.post("/api/config")
def update_config(update: ConfigUpdate):
    """只允许改 comfyui_* 两个字段，不接收整份配置，避免把脱敏值写回去。"""
    config = app_module._read_config()

    if update.comfyui_path is not None:
        config["comfyui_path"] = update.comfyui_path.strip()

    if update.comfyui_url is not None:
        url = update.comfyui_url.strip()
        if url and not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "error": "comfyui_url 必须以 http:// 或 https:// 开头"}
        config["comfyui_url"] = url or "http://127.0.0.1:8188"

    app_module._write_config(config)

    return {
        "ok": True,
        "comfyui_path": config.get("comfyui_path", ""),
        "comfyui_url": config.get("comfyui_url", ""),
    }