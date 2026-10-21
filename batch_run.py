import argparse
import csv
import html
import random
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from comfy_adapter import WorkflowAdapter
from quality_check import check_batch


REVIEW_SCRIPT = """
<script>
(function() {
  var STORAGE_KEY = 'review_marks_v1';

  function loadMarks() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    } catch (e) {
      return {};
    }
  }

  function saveMarks(marks) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(marks));
  }

  function refreshButtons() {
    var marks = loadMarks();
    document.querySelectorAll('.mark-btn').forEach(function(btn) {
      var key = btn.dataset.batch + '/' + btn.dataset.seed;
      var type = btn.dataset.type;
      if (marks[key] === type) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    var count = Object.keys(marks).length;
    var status = document.getElementById('mark-status');
    if (status) {
      status.textContent = count > 0 ? ('已标记 ' + count + ' 项') : '';
    }
  }

  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.mark-btn');
    if (!btn) return;
    var key = btn.dataset.batch + '/' + btn.dataset.seed;
    var type = btn.dataset.type;
    var marks = loadMarks();
    if (marks[key] === type) {
      delete marks[key];
    } else {
      marks[key] = type;
    }
    saveMarks(marks);
    refreshButtons();
  });

  var exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', function() {
      var marks = loadMarks();
      var liked = [];
      var rejected = [];
      Object.keys(marks).forEach(function(k) {
        if (marks[k] === 'like') liked.push(k);
        else if (marks[k] === 'reject') rejected.push(k);
      });
      var payload = { liked: liked, rejected: rejected };
      var blob = new Blob(
        [JSON.stringify(payload, null, 2)],
        { type: 'application/json' }
      );
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'review_marks.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  refreshButtons();
})();
</script>
"""


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5,
                        help="要跑的次数（未指定 --seeds 时使用）")
    parser.add_argument("--seeds", type=str, default="",
                        help="逗号分隔的 seed 列表，指定后忽略 --count")
    parser.add_argument("--segment", type=str, default="",
                        help="片段名，如 seg_01。指定后从 segments/<name>/ 读 prompt 和 refs")
    parser.add_argument("--prompt-file", default="subject_definitions.txt",
                        help="仅在未指定 --segment 时使用")
    parser.add_argument("--ref-images", type=str, default="",
                        help="仅在未指定 --segment 时使用")
    parser.add_argument("--profile", default="workflow_profile.json")
    parser.add_argument("--log", default="batch_log.csv")
    parser.add_argument("--batch-root", default="batches",
                        help="批次目录的根目录")
    parser.add_argument("--duration", type=float, default=9.0)
    parser.add_argument("--aspect-ratio", default="16:9 (Widescreen)")
    parser.add_argument("--megapixels", type=float, default=1.0)
    parser.add_argument("--force", action="store_true",
                        help="强制重跑，即使 seed 已在日志里成功过")
    return parser.parse_args()


def load_segment(segment_name: str):
    """从 segments/<name>/ 读取 prompt 和 refs。"""
    seg_dir = Path("segments") / segment_name
    if not seg_dir.exists():
        raise SystemExit(f"片段目录不存在：{seg_dir}")

    prompt_file = seg_dir / "prompt.txt"
    if not prompt_file.exists():
        raise SystemExit(f"片段缺少 prompt.txt：{prompt_file}")
    prompt_text = prompt_file.read_text(encoding="utf-8-sig")
    if not prompt_text.strip():
        raise SystemExit(f"prompt 文件是空的：{prompt_file}")

    refs = []
    refs_file = seg_dir / "refs.txt"
    if refs_file.exists():
        for line in refs_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            refs.append(line)

    return prompt_text, refs


def resolve_inputs(args):
    """统一处理 --segment 和 --prompt-file/--ref-images 两条路径。"""
    if args.segment:
        prompt_text, refs = load_segment(args.segment)
        return prompt_text, refs, args.segment
    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8-sig")
    if not prompt_text.strip():
        raise SystemExit(
            f"prompt 文件是空的：{args.prompt_file}。"
            "请先填入内容再跑，否则会覆盖工作流里的原始提示词。"
        )
    refs = [s.strip() for s in args.ref_images.split(",") if s.strip()]
    return prompt_text, refs, ""


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


def make_batch_dir(root: str, segment: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{segment}_" if segment else ""
    path = Path(root) / f"{prefix}{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_last_frame(video_path: Path, output_path: Path):
    """用 ffmpeg 抽取视频的最后一帧。"""
    subprocess.run([
        "ffmpeg", "-y", "-sseof", "-1",
        "-i", str(video_path),
        "-update", "1",
        str(output_path),
    ], check=True, capture_output=True)


def render_review_html(batch_dir: Path, records: list, prompt_preview: str) -> Path:
    """生成审片页面，带喜欢/淘汰标记和导出功能。records 应已按可疑优先排序。"""
    items_html = []
    for r in records:
        if r["status"] != "ok":
            items_html.append(
                f'<div class="item error">'
                f'<div class="meta">seed={r["seed"]} · 失败 · {html.escape(r["error"])}</div>'
                f'</div>'
            )
            continue

        rel = Path(r["batch_file"]).name
        size_mb = r["file_size"] / 1024 / 1024
        q = r.get("quality", {})
        verdict = q.get("verdict", "unknown")
        reasons = q.get("reasons", [])
        metrics = q.get("metrics", {})

        badge_class = {"pass": "badge-pass", "suspect": "badge-suspect"}.get(verdict, "badge-unknown")
        badge_text = {"pass": "通过", "suspect": "可疑"}.get(verdict, verdict)

        reasons_html = ""
        if reasons:
            reasons_html = '<div class="reasons">' + "<br>".join(
                html.escape(x) for x in reasons
            ) + "</div>"

        metrics_str = ""
        if metrics.get("duration") is not None:
            metrics_str = (
                f' · {metrics["duration"]:.1f}s'
                f' · {metrics.get("fps", "?")}fps'
            )

        items_html.append(
            f'<div class="item">'
            f'<span class="badge {badge_class}">{badge_text}</span>'
            f'<video src="{html.escape(rel)}" controls preload="metadata"></video>'
            f'<div class="meta">seed={r["seed"]} · {r["elapsed"]:.0f}s · {size_mb:.2f}MB{metrics_str}</div>'
            f'{reasons_html}'
            f'<div class="actions">'
            f'<button class="mark-btn like" data-batch="{batch_dir.name}" data-seed="{r["seed"]}" data-type="like">👍 喜欢</button>'
            f'<button class="mark-btn reject" data-batch="{batch_dir.name}" data-seed="{r["seed"]}" data-type="reject">👎 淘汰</button>'
            f'</div>'
            f'<div class="path">{html.escape(rel)}</div>'
            f'</div>'
        )

    if not items_html:
        items_html.append(
            '<div class="item error"><div class="meta">本批次没有生成任何视频。</div></div>'
        )

    ok_count = len([r for r in records if r["status"] == "ok"])
    suspect_count = len([r for r in records if r.get("quality", {}).get("verdict") == "suspect"])

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>审片 · {batch_dir.name}</title>
<style>
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:-apple-system,"Segoe UI",sans-serif; margin:0; padding:24px; }}
  h1 {{ font-size:18px; font-weight:500; margin:0 0 8px; }}
  .toolbar {{ display:flex; align-items:center; gap:12px; margin:16px 0; }}
  .toolbar button {{ background:#2a2a2a; color:#e0e0e0; border:1px solid #444; padding:6px 14px; border-radius:4px; cursor:pointer; font-size:13px; }}
  .toolbar button:hover {{ background:#333; }}
  #mark-status {{ font-size:13px; color:#8f8; }}
  .summary {{ font-size:13px; color:#888; margin-bottom:16px; }}
  .prompt {{ font-size:12px; color:#888; margin-bottom:24px; white-space:pre-wrap; max-height:100px; overflow:auto; background:#111; padding:12px; border-radius:6px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:20px; }}
  .item {{ background:#222; border-radius:8px; padding:12px; position:relative; }}
  .item.error {{ color:#c66; font-size:13px; }}
  .badge {{ position:absolute; top:20px; right:20px; font-size:11px; padding:3px 8px; border-radius:4px; font-weight:500; z-index:1; }}
  .badge-pass {{ background:#2d4a2d; color:#8f8; }}
  .badge-suspect {{ background:#4a2d2d; color:#f99; }}
  .badge-unknown {{ background:#333; color:#aaa; }}
  video {{ width:100%; border-radius:4px; display:block; background:#000; }}
  .meta {{ font-size:13px; color:#aaa; margin-top:8px; }}
  .reasons {{ font-size:12px; color:#f99; margin-top:6px; line-height:1.5; }}
  .actions {{ display:flex; gap:8px; margin-top:10px; }}
  .mark-btn {{ flex:1; background:#2a2a2a; color:#888; border:1px solid #444; padding:6px 10px; border-radius:4px; cursor:pointer; font-size:13px; }}
  .mark-btn:hover {{ background:#333; }}
  .mark-btn.like.active {{ background:#2d4a2d; color:#8f8; border-color:#4a6a4a; }}
  .mark-btn.reject.active {{ background:#4a2d2d; color:#f99; border-color:#6a4a4a; }}
  .path {{ font-size:11px; color:#666; margin-top:6px; font-family:monospace; word-break:break-all; }}
</style>
</head>
<body>
<h1>审片 · {batch_dir.name}</h1>
<div class="summary">成功 {ok_count} 个 · 可疑 {suspect_count} 个 · 可疑排在前面</div>
<div class="toolbar">
  <button id="export-btn">导出已选中</button>
  <span id="mark-status"></span>
</div>
<div class="prompt">prompt 预览：{html.escape(prompt_preview)}</div>
<div class="grid">
{"".join(items_html)}
</div>
{REVIEW_SCRIPT}
</body>
</html>
"""
    out = batch_dir / "review.html"
    out.write_text(html_content, encoding="utf-8")
    return out


def main():
    args = parse_args()
    prompt_text, ref_images, segment = resolve_inputs(args)

    seeds = resolve_seeds(args)
    done_seeds = set() if args.force else load_done_seeds(args.log)

    log_path = Path(args.log)
    write_header = not log_path.exists()

    batch_dir = make_batch_dir(args.batch_root, segment)
    tail_dir = batch_dir / "tail_frames"
    tail_dir.mkdir(exist_ok=True)

    print(f"计划跑 {len(seeds)} 次，已完成 {len(done_seeds & set(seeds))} 次")
    if segment:
        print(f"片段：{segment}")
    print(f"prompt 长度：{len(prompt_text)} 字符")
    print(f"参考图：{ref_images if ref_images else '（使用工作流默认）'}")
    print(f"批次目录：{batch_dir.resolve()}")

    records = []

    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "timestamp", "segment", "seed", "duration", "aspect_ratio",
                "megapixels", "status", "output_path", "file_size",
                "elapsed_seconds", "error",
            ])
            f.flush()

        for i, seed in enumerate(seeds, 1):
            if seed in done_seeds:
                print(f"[{i}/{len(seeds)}] [skip] seed={seed} 已完成（加 --force 可重跑）")
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
                if ref_images:
                    adapter.set_reference_images(ref_images)

                path = adapter.run_once()
                elapsed = time.time() - start

                batch_file = batch_dir / f"seed_{seed}{path.suffix}"
                shutil.copy2(path, batch_file)

                tail_path = tail_dir / f"seed_{seed}.png"
                extract_last_frame(path, tail_path)

                writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    segment, seed, args.duration, args.aspect_ratio, args.megapixels,
                    "ok", str(path), path.stat().st_size,
                    round(elapsed, 1), "",
                ])
                f.flush()

                records.append({
                    "seed": seed, "status": "ok",
                    "batch_file": str(batch_file),
                    "file_size": path.stat().st_size,
                    "elapsed": elapsed, "error": "",
                })
                print(f"[{i}/{len(seeds)}] [ok] seed={seed} -> {batch_file.name} ({elapsed:.0f}s)")
                print(f"    尾帧：{tail_path.name}")

            except Exception as e:
                elapsed = time.time() - start
                writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    segment, seed, args.duration, args.aspect_ratio, args.megapixels,
                    "error", "", "", round(elapsed, 1), str(e),
                ])
                f.flush()

                records.append({
                    "seed": seed, "status": "error",
                    "batch_file": "", "file_size": 0,
                    "elapsed": elapsed, "error": str(e),
                })
                print(f"[{i}/{len(seeds)}] [error] seed={seed}: {e}")

    if records:
        print("\n正在做技术质量检测...")
        records = check_batch(records, args.duration)

        suspects = [r for r in records if r.get("quality", {}).get("verdict") == "suspect"]
        if suspects:
            print(f"发现 {len(suspects)} 个可疑视频：")
            for r in suspects:
                print(f"  seed={r['seed']}: {'; '.join(r['quality']['reasons'])}")
        else:
            print("所有成功视频都通过了技术检测。")

    preview = prompt_text[:200].replace("\n", " ")
    review_path = render_review_html(batch_dir, records, preview)
    print(f"\n审片页面：{review_path.resolve()}")

    if records:
        print("用浏览器打开这个文件即可一次性查看本批视频（可疑的排在前面）。")
        print("在审片页面里可以点『喜欢』或『淘汰』，点『导出已选中』下载 JSON。")
    else:
        print("本次没有生成任何新视频（全部被跳过）。加 --force 可强制重跑。")


if __name__ == "__main__":
    main()