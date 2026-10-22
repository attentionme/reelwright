import json
import shutil
import subprocess
import tempfile
from pathlib import Path


# ── 可选依赖：未安装时静默跳过，不影响主流程 ──
try:
    from sead import DEFAULT_MODEL_PATH, SEADDetector
    _HAS_SEAD = True
except ImportError:
    _HAS_SEAD = False


# 视觉审核暂时关闭（aigcqa 在 Python 3.14 下无可用 wheel）
def _check_visual_quality(path: Path) -> dict:
    return {"verdict": "not_checked", "reasons": ["视觉审核暂未启用"]}


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


def _extract_audio(video_path: Path, audio_path: Path):
    """用 ffmpeg 提取单声道 16kHz WAV，供 SEAD 使用。"""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-ac", "1", "-ar", "16000",
        "-f", "wav", str(audio_path),
    ], check=True, capture_output=True)


def _check_audio_bgm(path: Path) -> dict:
    """用 SEAD 检测音频中 music 片段占比。"""
    if not _HAS_SEAD:
        return {"verdict": "not_checked", "reasons": ["未安装 sead"]}

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / "audio.wav"
        try:
            _extract_audio(path, audio_path)
        except Exception as exc:
            return {"verdict": "not_checked", "reasons": [f"音频提取失败：{exc}"]}

        try:
            detector = SEADDetector(Path(DEFAULT_MODEL_PATH))
            segments = detector.process_file(audio_path)
        except Exception as exc:
            return {"verdict": "not_checked", "reasons": [f"SEAD 执行失败：{exc}"]}

        total = sum(
            s.end_time - s.start_time
            for s in segments
            if s.end_time > s.start_time
        )
        music = sum(
            s.end_time - s.start_time
            for s in segments
            if s.end_time > s.start_time and s.label == "music"
        )

        if total <= 0:
            return {"verdict": "not_checked", "reasons": ["音频时长为零"]}

        ratio = music / total

        if ratio > 0.1:
            return {
                "verdict": "suspect",
                "reasons": [f"检测到 music 片段，占比 {ratio:.1%}"],
                "music_ratio": round(ratio, 3),
            }

        return {
            "verdict": "pass",
            "reasons": [],
            "music_ratio": round(ratio, 3),
        }


def _check_one(path: Path, expected_duration: float) -> dict:
    """对单个视频做技术检测 + 音频 AI 预审，返回 {verdict, reasons, metrics}。"""
    reasons = []
    probe = _probe_video(path)

    if not probe["ok"]:
        return {
            "verdict": "suspect",
            "reasons": [f"ffprobe 失败：{probe['error']}"],
            "metrics": {},
        }

    # ── 技术指标 ──
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

    # ── 视觉审核（当前占位）──
    visual = _check_visual_quality(path)
    if visual["verdict"] == "suspect":
        reasons.extend(visual["reasons"])

    # ── 音频 AI 预审 ──
    audio = _check_audio_bgm(path)
    if audio["verdict"] == "suspect":
        reasons.extend(audio["reasons"])

    return {
        "verdict": "suspect" if reasons else "pass",
        "reasons": reasons,
        "metrics": {
            "duration": probe["duration"],
            "fps": probe["fps"],
            "size_mb": round(size_mb, 2),
            "has_audio": probe["has_audio"],
            "visual_score": visual.get("score"),
            "music_ratio": audio.get("music_ratio"),
        },
    }


def check_batch(records: list, expected_duration: float) -> list:
    """
    对一批记录逐个做技术检测 + 音频 AI 预审，原地写入 record["quality"]。

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