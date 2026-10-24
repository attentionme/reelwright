"""
集状态扫描：从 app.py 抽出来的只读函数。

app.py（Gradio + Agent）和 api.py（FastAPI）共用这一份实现，
避免重复代码，也避免 api.py 为了拿扫描函数而 import app（会构建 Gradio UI）。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_episode_id() -> str:
    p = ROOT / "episode.txt"
    if p.exists():
        text = p.read_text(encoding="utf-8-sig").strip()
        if text:
            return text
    return "ep01"


def scan_segments() -> list:
    root = ROOT / "segments"
    if not root.exists():
        return []

    segs = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if not re.fullmatch(r"seg_\d+", d.name):
            continue

        meta = {}
        meta_path = d / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        segs.append({
            "id": d.name,
            "duration": meta.get("estimated_duration"),
            "views": meta.get("views"),
            "narrative_goal": meta.get("narrative_goal"),
        })

    segs.sort(key=lambda s: int(s["id"].split("_")[1]))
    return segs


def scan_batches(seg_id: str) -> list:
    root = ROOT / "batches"
    if not root.exists():
        return []

    compact = seg_id.replace("_", "")
    batches = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if not (
            d.name.startswith(compact + "_")
            or d.name.startswith(seg_id + "_")
        ):
            continue
        mp4s = sorted(d.glob("*.mp4"))
        if not mp4s:
            continue
        batches.append({
            "name": d.name,
            "videos": [m.name for m in mp4s],
            "mtime": d.stat().st_mtime,
        })

    batches.sort(key=lambda b: b["mtime"], reverse=True)
    return batches


def read_marks() -> dict:
    p = ROOT / "review_marks.json"
    if not p.exists():
        return {"episode": "", "liked": [], "rejected": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"episode": "", "liked": [], "rejected": []}


def segment_status(seg_id: str, liked_keys: set) -> dict:
    batches = scan_batches(seg_id)
    if not batches:
        return {
            "batch_count": 0,
            "video_count": 0,
            "latest_batch": None,
            "liked": [],
            "status": "pending",
        }

    seg_liked = [
        k for k in liked_keys
        if any(k.startswith(b["name"] + "/") for b in batches)
    ]

    return {
        "batch_count": len(batches),
        "video_count": sum(len(b["videos"]) for b in batches),
        "latest_batch": batches[0]["name"],
        "liked": seg_liked,
        "status": "reviewed" if seg_liked else "generated",
    }


def collect_episode_status() -> dict:
    episode = read_episode_id()
    segments = scan_segments()
    marks = read_marks()
    liked_keys = set(marks.get("liked", []))

    out = []
    for seg in segments:
        status = segment_status(seg["id"], liked_keys)
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