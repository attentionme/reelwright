import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SEG_ORDER = ["seg_01", "seg_02", "seg_03", "seg_04"]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--marks", default="review_marks.json")
    parser.add_argument("--batch-root", default="batches")
    parser.add_argument("--out", default="episode_final.mp4")
    return parser.parse_args()


def find_segment_video(seg_name: str, marks: dict, batch_root: Path):
    """从 liked 列表里找指定 segment 的喜欢项，优先最新批次。"""
    liked = marks.get("liked", [])
    candidates = []
    for key in liked:
        parts = key.split("/")
        if len(parts) != 2:
            continue
        batch_name, seed_part = parts
        if not batch_name.startswith(seg_name + "_"):
            continue
        m = re.match(r"(?:seed_)?(\d+)$", seed_part)
        if not m:
            continue
        candidates.append((batch_name, int(m.group(1))))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    for batch_name, seed in candidates:
        batch_dir = batch_root / batch_name
        if not batch_dir.exists():
            continue
        matches = [
            p for p in batch_dir.glob(f"seed_{seed}.*")
            if p.suffix.lower() == ".mp4"
        ]
        if matches:
            return matches[0]
    return None


def main():
    args = parse_args()

    marks_path = Path(args.marks)
    if not marks_path.exists():
        raise SystemExit(f"找不到 {marks_path}")

    marks = json.loads(marks_path.read_text(encoding="utf-8"))
    batch_root = Path(args.batch_root)

    segments = []
    for seg_name in SEG_ORDER:
        video = find_segment_video(seg_name, marks, batch_root)
        if video is None:
            print(f"[skip] {seg_name}: 没有找到喜欢项")
            continue
        segments.append((seg_name, video))
        print(f"[found] {seg_name}: {video}")

    if not segments:
        raise SystemExit("没有任何 segment 可拼接")

    print(f"\n共 {len(segments)} 段，开始拼接...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        list_lines = []

        for i, (seg_name, video) in enumerate(segments, 1):
            dest = tmp_dir / f"{i:03d}.mp4"
            shutil.copy2(video, dest)
            list_lines.append(f"file '{dest.as_posix()}'")
            print(f"  {i:03d}.mp4 <- {seg_name} ({video.name})")

        list_file = tmp_dir / "list.txt"
        list_file.write_text("\n".join(list_lines), encoding="utf-8")

        out_path = Path(args.out)
        if out_path.exists():
            out_path.unlink()

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out_path),
        ]
        print(f"\n执行: ffmpeg concat ...")
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
        if result.returncode != 0:
            print(f"concat 失败: {result.stderr[-500:]}")
            raise SystemExit(1)

    print(f"\n已生成: {out_path.resolve()}")
    if out_path.exists():
        size_mb = out_path.stat().st_size / 1024 / 1024
        print(f"大小: {size_mb:.2f} MB")


if __name__ == "__main__":
    main()