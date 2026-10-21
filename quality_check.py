import json
import shutil
import subprocess
from pathlib import Path


def _probe_video(path: Path) -> dict:
    """用 ffprobe 读取视频的实际时长、帧率、是否有音频流。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"ok": False, "error": "系统中找不到 ffprobe"}

    cmd = [
        ffprobe, "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,r_frame_rate",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ffprobe 超时"}

    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "ffprobe 返回非 JSON"}

    streams = data.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    duration = None
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass

    fps = None
    for s in streams:
        if s.get("codec_type") == "video" and s.get("r_frame_rate"):
            try:
                num, den = s["r_frame_rate"].split("/")
                fps = round(float(num) / float(den), 2)
            except (ValueError, ZeroDivisionError):
                pass
            break

    return {
        "ok": True,
        "duration": duration,
        "fps": fps,
        "has_video": has_video,
        "has_audio": has_audio,
    }


def _check_one(path: Path, expected_duration: float) -> dict:
    """对单个视频做技术检测，返回 {verdict, reasons, metrics}。"""
    reasons = []
    probe = _probe_video(path)

    if not probe["ok"]:
        return {
            "verdict": "suspect",
            "reasons": [f"ffprobe 失败：{probe['error']}"],
            "metrics": {},
        }

    if not probe["has_video"]:
        reasons.append("没有视频流")

    if not probe["has_audio"]:
        reasons.append("没有音频流")

    if probe["duration"] is None:
        reasons.append("无法读取时长")
    else:
        diff = abs(probe["duration"] - expected_duration)
        if diff > 1.0:
            reasons.append(
                f"时长异常：{probe['duration']:.1f}s（预期 {expected_duration}s）"
            )

    size_mb = path.stat().st_size / 1024 / 1024
    if size_mb < 0.5:
        reasons.append(f"文件过小：{size_mb:.2f}MB")

    if probe["fps"] is not None and abs(probe["fps"] - 24) > 0.5:
        reasons.append(f"帧率异常：{probe['fps']}fps（预期 24）")

    return {
        "verdict": "suspect" if reasons else "pass",
        "reasons": reasons,
        "metrics": {
            "duration": probe["duration"],
            "fps": probe["fps"],
            "size_mb": round(size_mb, 2),
            "has_audio": probe["has_audio"],
        },
    }


def check_batch(records: list, expected_duration: float) -> list:
    """
    对一批记录逐个做技术检测，原地写入 record["quality"]。

    返回新列表，按“可疑优先”排序：suspect 在前，pass 在后。
    同一状态内按 seed 升序，保证结果稳定。
    """
    for r in records:
        if r["status"] != "ok":
            r["quality"] = {"verdict": "error", "reasons": [], "metrics": {}}
            continue
        r["quality"] = _check_one(Path(r["batch_file"]), expected_duration)

    def sort_key(r):
        order = {"error": 0, "suspect": 1, "pass": 2}
        return (order.get(r["quality"]["verdict"], 3), r["seed"])

    return sorted(records, key=sort_key)