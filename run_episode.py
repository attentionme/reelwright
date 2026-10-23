import argparse
import re
import subprocess
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments-root", default="segments")
    parser.add_argument("--profile", default="workflow_profile_2.json")
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--megapixels", type=float, default=1.5)
    parser.add_argument("--start-from", type=str, default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--trial", action="store_true",
                        help="试验模式：duration=5, megapixels=1.0, count=1")
    parser.add_argument("--concat", action="store_true",
                        help="跑完后自动拼接（默认不拼）")
    return parser.parse_args()


def find_segments(root):
    segs = []
    for d in root.iterdir():
        if d.is_dir() and re.fullmatch(r"seg_\d+", d.name):
            segs.append(d)
    segs.sort(key=lambda d: int(d.name.split("_")[1]))
    return segs


def main():
    args = parse_args()
    segs = find_segments(Path(args.segments_root))
    if not segs:
        raise SystemExit(f"{args.segments_root} 下没有 seg_XX 目录")

    if args.trial:
        args.count = 1
        args.megapixels = 1.0
        print("[trial] 试验模式：duration=5.0, megapixels=1.0, count=1")

    print(f"共 {len(segs)} 段：{[s.name for s in segs]}")

    started = not args.start_from
    for seg_dir in segs:
        if not started:
            if seg_dir.name == args.start_from:
                started = True
            else:
                print(f"[skip] {seg_dir.name}")
                continue

        print(f"\n{'=' * 60}")
        print(f"跑 {seg_dir.name}")
        print(f"{'=' * 60}")

        cmd = [
            str(Path(".venv") / "Scripts" / "python.exe"),
            "pipeline.py",
            "--segment", seg_dir.name,
            "--profile", args.profile,
            "--count", str(args.count),
            "--megapixels", str(args.megapixels),
        ]
        if args.trial:
            cmd.append("--trial")
        if args.force:
            cmd.append("--force")
        subprocess.run(cmd, check=True)

    print(f"\n{'=' * 60}")
    print("所有段跑完。")
    print(f"{'=' * 60}")

    if args.concat:
        print("按 --concat 指定，自动拼接...")
        subprocess.run([
            str(Path(".venv") / "Scripts" / "python.exe"),
            "concat_episode.py",
        ], check=True)
        print("成片: episode_final.mp4")
    else:
        print("下一步：")
        print("  1. 逐个打开 review.html，标记喜欢")
        print("  2. 导出 review_marks.json 到项目目录")
        print("  3. 跑 concat_episode.py 出片")
        print("")
        print("  或者加 --concat 自动拼接")


if __name__ == "__main__":
    main()