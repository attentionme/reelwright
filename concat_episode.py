import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--marks", default="review_marks.json")
    parser.add_argument("--batch-root", default="batches")
    parser.add_argument("--segments-root", default="segments")
    parser.add_argument("--out", default="episode_final.mp4")
    return parser.parse_args()


def find_segments(root):
    segs = []
    for d in root.iterdir():
        if d.is_dir() and re.fullmatch(r"seg_\d+", d.name):
            segs.append(d)
    segs.sort(key=lambda d: int(d.name.split("_")[1]))
    return segs


def resolve_video_in_batch(batch_dir, token):
    if re.fullmatch(r"v\d{2}", token):
        matches = sorted(batch_dir.glob(f"{token}_*.mp4"))
        if matches:
            return matches[0]

    m = re.match(r"(?:seed_)?(\d+)$", token)
    if m:
        seed = int(m.group(1))
        matches = [
            p for p in batch_dir.glob(f"seed_{seed}.*")
            if p.suffix.lower() == ".mp4"
        ]
        if matches:
            return matches[0]
        matches = sorted(batch_dir.glob(f"v*_seed{seed % 1000000:06d}.mp4"))
        if matches:
            return matches[0]

    return None


def find_segment_video(seg_name, marks, batch_root):
    compact = seg_name.replace("_", "")

    def matches(name):
        return (name.startswith(compact + "_") or
                name.startswith(seg_name + "_"))

    liked = marks.get("liked", []) if marks else []
    candidates = []
    for key in liked:
        parts = key.split("/")
        if len(parts) != 2:
            continue
        batch_name, token = parts
        if not matches(batch_name):
            continue
        candidates.append((batch_name, token))

    if candidates:
        # 按批次的 mtime 排序，最新优先
        candidates.sort(
            key=lambda x: (batch_root / x[0]).stat().st_mtime
            if (batch_root / x[0]).exists() else 0,
            reverse=True,
        )
        for batch_name, token in candidates:
            batch_dir = batch_root / batch_name
            if not batch_dir.exists():
                continue
            video = resolve_video_in_batch(batch_dir, token)
            if video:
                return video, f"liked:{batch_name}/{token}"

    all_batches = [
        d for d in batch_root.iterdir()
        if d.is_dir() and matches(d.name)
    ]
    all_batches.sort(key=lambda d: d.stat().st_mtime, reverse=True)

    for batch_dir in all_batches:
        mp4s = sorted(batch_dir.glob("*.mp4"))
        if mp4s:
            return mp4s[0], f"fallback:{batch_dir.name}/{mp4s[0].name}"

    return None, None


def main():
    args = parse_args()

    marks = {}
    marks_path = Path(args.marks)
    if marks_path.exists():
        marks = json.loads(marks_path.read_text(encoding="utf-8"))

    batch_root = Path(args.batch_root)
    seg_root = Path(args.segments_root)
    seg_dirs = find_segments(seg_root)

    if not seg_dirs:
        raise SystemExit(f"{seg_root} 下没有 seg_XX 目录")

    segments = []
    for seg_dir in seg_dirs:
        video, source = find_segment_video(seg_dir.name, marks, batch_root)
        if video is None:
            print(f"[skip] {seg_dir.name}: 没有找到视频")
            continue
        segments.append((seg_dir.name, video, source))
        print(f"[found] {seg_dir.name}: {video}  ({source})")

    if not segments:
        raise SystemExit("没有任何 segment 可拼接")

    print(f"\n共 {len(segments)} 段，开始拼接...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        list_lines = []

        for i, (seg_name, video, _source) in enumerate(segments, 1):
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
            "-f", "concat", "-safe", "0",
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