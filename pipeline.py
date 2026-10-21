import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", required=True, help="要跑的片段名，如 seg_02")
    parser.add_argument("--profile", default="workflow_profile_2.json")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--megapixels", type=float, default=1.5)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--batch-root", default="batches")
    return parser.parse_args()


def load_refs(seg_name: str):
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
    """找 refs 里 tail_from_<prev>.png 这样的引用。"""
    for ref in refs:
        m = re.match(r"tail_from_(\w+)\.png$", ref)
        if m:
            return m.group(1), ref
    return None, None


def find_selected_video(prev_seg: str, batch_root: str):
    """从 review_marks.json 里找上一段被标记为喜欢的视频。"""
    marks_path = Path("review_marks.json")
    if not marks_path.exists():
        raise SystemExit(
            f"找不到 review_marks.json。"
            f"请先跑完 {prev_seg}，在审片页面标记喜欢，然后导出 review_marks.json。"
        )

    data = json.loads(marks_path.read_text(encoding="utf-8"))
    liked = data.get("liked", [])

    for key in liked:
        parts = key.split("/")
        if len(parts) != 2:
            continue
        batch_name, seed_part = parts
        if not batch_name.startswith(prev_seg + "_"):
            continue
        m = re.match(r"(?:seed_)?(\d+)$", seed_part)
        if not m:
            continue
        seed = int(m.group(1))
        batch_dir = Path(batch_root) / batch_name
        if not batch_dir.exists():
            continue
        candidates = [
            p for p in batch_dir.glob(f"seed_{seed}.*")
            if p.suffix.lower() == ".mp4"
        ]
        if candidates:
            return candidates[0]

    raise SystemExit(
        f"review_marks.json 里没有 {prev_seg} 的喜欢项。"
        f"请先在审片页面把 {prev_seg} 的视频标记为喜欢。"
    )


def get_input_dir(profile_path: str) -> Path:
    """从 profile 的 output_dir 推导 input 目录。"""
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8-sig"))
    output_dir = Path(profile["output_dir"])
    return output_dir.parent / "input"


def extract_last_frame(video_path: Path, output_path: Path):
    subprocess.run([
        "ffmpeg", "-y", "-sseof", "-1",
        "-i", str(video_path),
        "-update", "1",
        str(output_path),
    ], check=True, capture_output=True)


def prepare_tail(prev_seg: str, tail_name: str, profile_path: str, batch_root: str):
    """从上一段选中的视频抽尾帧，复制到 input。"""
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

    cmd = [
        str(Path(".venv") / "Scripts" / "python.exe"),
        "batch_run.py",
        "--segment", args.segment,
        "--profile", args.profile,
        "--count", str(args.count),
        "--megapixels", str(args.megapixels),
        "--duration", str(args.duration),
    ]
    if args.force:
        cmd.append("--force")

    print(f"\n执行：{' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()