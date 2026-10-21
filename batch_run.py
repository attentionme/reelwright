import argparse
import csv
import random
import time
from datetime import datetime
from pathlib import Path

from comfy_adapter import WorkflowAdapter


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5,
                        help="要跑的次数（未指定 --seeds 时使用）")
    parser.add_argument("--seeds", type=str, default="",
                        help="逗号分隔的 seed 列表，指定后忽略 --count")
    parser.add_argument("--prompt-file", default="subject_definitions.txt")
    parser.add_argument("--profile", default="workflow_profile.json")
    parser.add_argument("--log", default="batch_log.csv")
    parser.add_argument("--duration", type=float, default=9.0)
    parser.add_argument("--aspect-ratio", default="16:9 (Widescreen)")
    parser.add_argument("--megapixels", type=float, default=1.0)
    return parser.parse_args()


def resolve_seeds(args):
    if args.seeds:
        return [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    return [random.randint(1, 2**53) for _ in range(args.count)]


def load_done_seeds(log_file):
    if not Path(log_file).exists():
        return set()
    done = set()
    with open(log_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "ok":
                try:
                    done.add(int(row["seed"]))
                except (ValueError, KeyError):
                    pass
    return done


def main():
    args = parse_args()
    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8-sig")

    if not prompt_text.strip():
        raise SystemExit(
            f"prompt 文件是空的：{args.prompt_file}。"
            "请先填入内容再跑，否则会覆盖工作流里的原始提示词。"
        )

    seeds = resolve_seeds(args)
    done_seeds = load_done_seeds(args.log)

    log_path = Path(args.log)
    write_header = not log_path.exists()

    print(f"计划跑 {len(seeds)} 次，已完成 {len(done_seeds & set(seeds))} 次")
    print(f"prompt 长度：{len(prompt_text)} 字符")

    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "timestamp", "seed", "duration", "aspect_ratio",
                "megapixels", "status", "output_path", "file_size",
                "elapsed_seconds", "error",
            ])
            f.flush()

        for i, seed in enumerate(seeds, 1):
            if seed in done_seeds:
                print(f"[{i}/{len(seeds)}] [skip] seed={seed} 已完成")
                continue

            print(f"[{i}/{len(seeds)}] [run] seed={seed}")
            start = time.time()
            try:
                adapter = WorkflowAdapter(args.profile)
                adapter.set_many(
                    prompt=prompt_text,
                    seed=seed,
                    duration=args.duration,
                    aspect_ratio=args.aspect_ratio,
                    megapixels=args.megapixels,
                )
                path = adapter.run_once()
                elapsed = time.time() - start
                writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    seed, args.duration, args.aspect_ratio, args.megapixels,
                    "ok", str(path), path.stat().st_size,
                    round(elapsed, 1), "",
                ])
                f.flush()
                print(f"[{i}/{len(seeds)}] [ok] seed={seed} -> {path.name} ({elapsed:.0f}s)")

            except Exception as e:
                elapsed = time.time() - start
                writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    seed, args.duration, args.aspect_ratio, args.megapixels,
                    "error", "", "", round(elapsed, 1), str(e),
                ])
                f.flush()
                print(f"[{i}/{len(seeds)}] [error] seed={seed}: {e}")


if __name__ == "__main__":
    main()