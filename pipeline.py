import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", required=True)
    parser.add_argument("--profile", default="workflow_profile_2.json")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--megapixels", type=float, default=1.5)
    parser.add_argument("--duration", type=float, default=0.0,
                        help="0 表示从 segments/<name>/meta.json 读")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--batch-root", default="batches")
    parser.add_argument("--trial", action="store_true",
                        help="试验模式：duration=5, megapixels=1.0, count=1")
    return parser.parse_args()


def load_refs(seg_name):
    refs_file = Path("segments") / seg_name / "refs.txt"
    if not refs_file.exists():
        return []
    refs = []
    for line in refs_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        refs.append(line)
    return refs


def find_tail_ref(refs):
    for ref in refs:
        m = re.match(r"tail_from_(\w+)\.png$", ref)
        if m:
            return m.group(1), ref
    return None, None


def load_duration(seg_name, explicit_duration):
    if explicit_duration > 0:
        return explicit_duration
    meta_path = Path("segments") / seg_name / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return float(meta.get("estimated_duration", 10.0))
    return 10.0


def find_selected_video(prev_seg, batch_root):
    """只用最新批次：优先 liked，其次第一个 mp4。忽略旧批次的 liked。"""
    all_batches = sorted(
        [d for d in Path(batch_root).iterdir()
         if d.is_dir() and d.name.startswith(prev_seg + "_")],
        reverse=True,
    )
    if not all_batches:
        raise SystemExit(f"找不到 {prev_seg} 的任何批次")

    latest = all_batches[0]
    print(f"[latest] 使用最新批次：{latest.name}")

    marks_path = Path("review_marks.json")
    if marks_path.exists():
        data = json.loads(marks_path.read_text(encoding="utf-8"))
        for key in data.get("liked", []):
            if key.startswith(latest.name + "/"):
                seed_part = key.split("/")[1]
                m = re.match(r"(?:seed_)?(\d+)$", seed_part)
                if m:
                    seed = int(m.group(1))
                    matches = [
                        p for p in latest.glob(f"seed_{seed}.*")
                        if p.suffix.lower() == ".mp4"
                    ]
                    if matches:
                        print(f"[liked] 最新批次的喜欢项：{key}")
                        return matches[0]

    mp4s = sorted(latest.glob("*.mp4"))
    if not mp4s:
        raise SystemExit(f"{latest} 里没有 mp4")
    print(f"[fallback] 最新批次第一个：{mp4s[0].name}")
    return mp4s[0]


def get_input_dir(profile_path):
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8-sig"))
    output_dir = Path(profile["output_dir"])
    return output_dir.parent / "input"


def extract_last_frame(video_path, output_path):
    subprocess.run([
        "ffmpeg", "-y", "-sseof", "-1",
        "-i", str(video_path),
        "-update", "1",
        str(output_path),
    ], check=True, capture_output=True, timeout=120)


def prepare_tail(prev_seg, tail_name, profile_path, batch_root):
    video = find_selected_video(prev_seg, batch_root)
    print(f"上一段选中视频：{video}")

    input_dir = get_input_dir(profile_path)
    if not input_dir.exists():
        raise SystemExit(f"input 目录不存在：{input_dir}")

    tmp = Path(batch_root) / f"_tmp_tail_{prev_seg}.png"
    extract_last_frame(video, tmp)

    dest = input_dir / tail_name
    shutil.copy2(tmp, dest)
    tmp.unlink()

    print(f"尾帧已准备：{dest}")
    return dest


def main():
    args = parse_args()

    if args.trial:
        args.duration = 5.0
        args.megapixels = 1.0
        args.count = 1
        print("[trial] 试验模式：duration=5.0, megapixels=1.0, count=1")

    seg_dir = Path("segments") / args.segment
    if not seg_dir.exists():
        raise SystemExit(f"片段目录不存在：{seg_dir}")

    refs = load_refs(args.segment)
    prev_seg, tail_name = find_tail_ref(refs)

    if prev_seg:
        print(f"检测到自动尾帧引用：{tail_name}（来自 {prev_seg}）")
        prepare_tail(prev_seg, tail_name, args.profile, args.batch_root)
    else:
        print("没有自动尾帧引用，直接跑。")

    duration = args.duration if args.duration > 0 else load_duration(args.segment, 0)
    print(f"本段时长：{duration}s")

    cmd = [
        str(Path(".venv") / "Scripts" / "python.exe"),
        "batch_run.py",
        "--segment", args.segment,
        "--profile", args.profile,
        "--count", str(args.count),
        "--megapixels", str(args.megapixels),
        "--duration", str(duration),
    ]
    if args.force:
        cmd.append("--force")
    if args.trial:
        cmd.append("--trial")

    print(f"\n执行：{' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()