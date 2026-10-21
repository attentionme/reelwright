import argparse
import html
import json
import re
import shutil
from pathlib import Path


def parse_mark_key(key: str):
    """
    把 "20261021_183239/seed_123" 或 "20261021_183239/123"
    拆成 (batch_name, seed)。
    """
    parts = key.split("/")
    if len(parts) != 2:
        return None, None
    batch_name, seed_part = parts
    m = re.match(r"(?:seed_)?(\d+)$", seed_part)
    if not m:
        return None, None
    return batch_name, int(m.group(1))


def find_video(batch_root: Path, batch_name: str, seed: int):
    """
    在批次目录里找 seed 对应的 mp4。

    用 seed_{seed}.* 精确匹配，避免 seed_123 误匹配 seed_1234.mp4。
    """
    batch_dir = batch_root / batch_name
    if not batch_dir.exists():
        return None

    candidates = [
        p for p in batch_dir.glob(f"seed_{seed}.*")
        if p.suffix.lower() == ".mp4"
    ]
    if not candidates:
        return None
    return candidates[0]


def render_final_index(final_dir: Path, items: list) -> Path:
    """生成 final/index.html，一次看所有精选视频。"""
    cards = []
    for it in items:
        rel = Path(it["dest"]).name
        cards.append(
            f'<div class="item">'
            f'<video src="{html.escape(rel)}" controls preload="metadata"></video>'
            f'<div class="meta">{html.escape(it["batch"])} · seed={it["seed"]} · {it["size_mb"]:.2f}MB</div>'
            f'</div>'
        )

    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>精选 · {len(items)} 个</title>
<style>
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:-apple-system,"Segoe UI",sans-serif; margin:0; padding:24px; }}
  h1 {{ font-size:20px; font-weight:500; margin:0 0 8px; }}
  .summary {{ font-size:13px; color:#888; margin-bottom:32px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:16px; }}
  .item {{ background:#222; border-radius:8px; padding:10px; }}
  video {{ width:100%; border-radius:4px; display:block; background:#000; }}
  .meta {{ font-size:12px; color:#aaa; margin-top:6px; }}
</style>
</head>
<body>
<h1>精选</h1>
<div class="summary">{len(items)} 个视频</div>
<div class="grid">
{"".join(cards)}
</div>
</body>
</html>
"""
    out = final_dir / "index.html"
    out.write_text(content, encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--marks", default="review_marks.json",
                        help="从审片页面导出的 review_marks.json")
    parser.add_argument("--batch-root", default="batches")
    parser.add_argument("--final-dir", default="final")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印，不复制")
    args = parser.parse_args()

    marks_path = Path(args.marks)
    if not marks_path.exists():
        raise SystemExit(
            f"找不到 {marks_path}。"
            "请先在审片页面点喜欢/淘汰，然后点『导出已选中』，把 JSON 保存到项目目录。"
        )

    data = json.loads(marks_path.read_text(encoding="utf-8"))
    liked = data.get("liked", [])

    if not liked:
        raise SystemExit("review_marks.json 里没有 liked 项。")

    batch_root = Path(args.batch_root)
    final_dir = Path(args.final_dir)
    if not args.dry_run:
        final_dir.mkdir(parents=True, exist_ok=True)

    items = []
    missing = []

    for key in liked:
        batch_name, seed = parse_mark_key(key)
        if batch_name is None:
            missing.append(key)
            continue

        src = find_video(batch_root, batch_name, seed)
        if src is None:
            missing.append(key)
            continue

        dest_name = f"{batch_name}__seed_{seed}{src.suffix}"
        dest = final_dir / dest_name

        size_mb = src.stat().st_size / 1024 / 1024
        items.append({
            "batch": batch_name,
            "seed": seed,
            "src": str(src),
            "dest": str(dest),
            "size_mb": size_mb,
        })

        if args.dry_run:
            print(f"[dry-run] {src.name} -> {dest_name} ({size_mb:.2f}MB)")
        else:
            shutil.copy2(src, dest)
            print(f"[copied] {src.name} -> {dest_name} ({size_mb:.2f}MB)")

    if missing:
        print(f"\n{len(missing)} 项没找到对应视频：")
        for k in missing:
            print(f"  {k}")

    if not items:
        raise SystemExit("没有任何视频被复制。")

    if not args.dry_run:
        index_path = render_final_index(final_dir, items)
        print(f"\n精选目录：{final_dir.resolve()}")
        print(f"总览页面：{index_path.resolve()}")
        print(f"共 {len(items)} 个视频。")
    else:
        print(f"\n[dry-run] 会复制 {len(items)} 个视频到 {final_dir}")


if __name__ == "__main__":
    main()