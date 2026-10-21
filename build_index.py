import argparse
import html
import re
from pathlib import Path


def parse_seed(filename: str):
    m = re.search(r"seed_(\d+)", filename)
    return m.group(1) if m else None


def scan_batches(batch_root: Path):
    batches = []
    for d in sorted(batch_root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        videos = sorted(d.glob("*.mp4"))
        if not videos:
            continue
        batches.append({
            "name": d.name,
            "videos": [
                {
                    "name": v.name,
                    "seed": parse_seed(v.name),
                    "size_mb": v.stat().st_size / 1024 / 1024,
                }
                for v in videos
            ],
        })
    return batches


def render_index(batch_root: Path, batches: list) -> Path:
    total_videos = sum(len(b["videos"]) for b in batches)
    sections = []

    for b in batches:
        items = []
        for v in b["videos"]:
            rel = f'{b["name"]}/{v["name"]}'
            seed_str = f'seed={v["seed"]}' if v["seed"] else v["name"]
            items.append(
                f'<div class="item">'
                f'<video src="{html.escape(rel)}" controls preload="metadata"></video>'
                f'<div class="meta">{html.escape(seed_str)} · {v["size_mb"]:.2f}MB</div>'
                f'</div>'
            )
        sections.append(
            f'<section>'
            f'<h2>{b["name"]} · {len(b["videos"])} 个</h2>'
            f'<div class="grid">{"".join(items)}</div>'
            f'</section>'
        )

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>所有批次 · {len(batches)} 批 · {total_videos} 个视频</title>
<style>
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:-apple-system,"Segoe UI",sans-serif; margin:0; padding:24px; }}
  h1 {{ font-size:20px; font-weight:500; margin:0 0 8px; }}
  .summary {{ font-size:13px; color:#888; margin-bottom:32px; }}
  h2 {{ font-size:15px; font-weight:500; color:#bbb; margin:32px 0 12px; border-bottom:1px solid #333; padding-bottom:6px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }}
  .item {{ background:#222; border-radius:8px; padding:10px; }}
  video {{ width:100%; border-radius:4px; display:block; background:#000; }}
  .meta {{ font-size:12px; color:#aaa; margin-top:6px; }}
</style>
</head>
<body>
<h1>所有批次</h1>
<div class="summary">{len(batches)} 个批次 · 共 {total_videos} 个视频</div>
{"".join(sections)}
</body>
</html>
"""
    out = batch_root / "index.html"
    out.write_text(html_content, encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", default="batches")
    args = parser.parse_args()

    batch_root = Path(args.batch_root)
    if not batch_root.exists():
        raise SystemExit(f"目录不存在：{batch_root}")

    batches = scan_batches(batch_root)
    if not batches:
        raise SystemExit(f"{batch_root} 下没有找到任何批次的 mp4 文件")

    out = render_index(batch_root, batches)
    print(f"已生成：{out.resolve()}")
    print(f"共 {len(batches)} 个批次，{sum(len(b['videos']) for b in batches)} 个视频")
    print("用浏览器打开这个文件即可查看所有批次。")


if __name__ == "__main__":
    main()