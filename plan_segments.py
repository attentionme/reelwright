import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from openai import OpenAI

# 复用 app.py 的配置读取（不依赖 gradio）
sys.path.insert(0, str(Path(__file__).parent))
from app import _read_config, _resolve_provider_config


H3_SECTIONS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

MAX_SEGMENT_SECONDS = 13.0
PREFERRED_SEGMENT_RANGE = (6.0, 12.0)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--out-root", default="segments")
    parser.add_argument("--ref-characters", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-retry", action="store_true")
    return parser.parse_args()


def build_llm_client():
    config = _read_config()
    provider = _resolve_provider_config(config, config.get("active_provider"))
    if not provider["configured"]:
        raise SystemExit(
            f"平台 {provider['display_name']} 配置不完整：base_url 或 model 缺失"
        )
    if not provider["api_key"]:
        raise SystemExit(
            f"平台 {provider['display_name']} 未配置 API Key"
        )
    client = OpenAI(
        api_key=provider["api_key"],
        base_url=provider["base_url"],
    )
    return client, provider["model"]


def load_script(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8-sig")
    if not text.strip():
        raise SystemExit(f"剧本文件为空：{path}")
    return text.strip()


def build_system_prompt(ref_characters: list) -> str:
    refs_line = "、".join(ref_characters)
    return f"""You are a storyboard planner for an animation production assistant. Your job is to split a script into generation segments, each corresponding to one ComfyUI H3 video generation run.

━━ SEGMENTATION RULES (MUST FOLLOW) ━━
1. Prefer plot boundaries: a complete action, a dialogue exchange, or a scene change constitutes one segment.
2. Hard limit: {MAX_SEGMENT_SECONDS:.0f} seconds per segment.
3. Preferred duration: {PREFERRED_SEGMENT_RANGE[0]:.0f}–{PREFERRED_SEGMENT_RANGE[1]:.0f} seconds per segment.
4. Adjacent segments must be continuous: the next segment's narrative start = previous segment's narrative end state.
5. Total segment count: 2–5.
6. NEVER generate a "pure subtitle card", "black screen", or "end card" segment.

━━ VISUAL BANS (HIGHEST PRIORITY) ━━
NEVER describe subtitles, captions, on-screen text, typography, text overlays, title cards, black-background white text, speech bubbles, or readable characters.

━━ MULTI-VIEW STRUCTURE INSIDE EACH SEGMENT (CRITICAL) ━━

Each segment should contain 2–3 distinct "views" (camera setups) inside its single video, so the segment is NOT one long monotonous shot. A "view" means the camera framing and the visible content change clearly, producing a natural cut.

━━ HOW TO WRITE VIEW CHANGES (MUST FOLLOW) ━━

DO NOT use:
- `[Shot 1]`, `[Shot 2]` markers
- Camera terminology: "close-up", "wide shot", "medium shot", "over-the-shoulder", "extreme close-up", "tracking shot", "dolly", "pan", "tilt", "zoom", "cut to", "the camera cuts"
- Any English film jargon

DO use natural language that describes WHAT IS VISIBLE, not HOW the camera moves:
- To open a segment: "The video starts with ..." + describe what the viewer sees
- To change view: "Then the view changes to ..." + describe what the viewer sees now
- To return: "Then the view changes back to ..." + describe what the viewer sees
- To end: "The camera holds on this view."

━━ VIEW SELECTION RULES (SAFEST TO RISKIEST) ━━

Prefer:
1. Wide view of the room → close view of a specific detail (a hand, an object, a face) → wide view again
2. Wide view of the room → different wide view from another angle (same space, both characters visible) → wide view again
3. Close view of one detail → wide view → close view of another detail

AVOID:
- Any view that requires both characters to be in specific positions relative to the camera when the previous view already had them in different positions (this causes spatial scrambling)
- "Over-the-shoulder" views (H3 misinterprets these and inserts duplicate bodies)
- Views that require the camera to be "behind" one character looking at another

SAFEST PATTERN (use this most of the time):
The video starts with a wide view of [the room/scene], showing [Subject 1] and [Subject 2] in their positions. Then the view changes to a close look at [a specific detail — a hand, a face, an object]. Then the view changes back to the wide view of the room, where [action continues].

━━ EACH VIEW MUST HAVE ━━
- A clear description of what is visible (who, what, where in the frame)
- The action that happens during this view
- Dialogue, if any, formatted as `(S1) says: <d>[Chinese] exact words</d>`
- A rough duration hint, e.g., "This view lasts about 2 seconds"

━━ OFFICIAL H3 Ref2VA SIX-SECTION FORMAT ━━

subject_definitions:
- One line per Subject.
- Format: `<Subject N> is [name], the [person] in <Picture N>, with all facial features, hairstyle, clothing, body proportions, and art style preserved exactly from <Picture N>. The character must be rendered in the exact 2D hand-drawn style of <Picture N>, with clean dark outlines and flat colors.`
- Do NOT invent facial features or clothing. LOCK them to the reference.
- Do NOT write actual filenames. Use `<Picture N>` only.
- Keep Subject order stable across all segments.
- Write in English.

summary:
- One short English paragraph.
- Begin with `[reference generation]`.
- Mention how many views this segment contains, e.g., "This segment has three views: a wide view of the room, a close view of a hand, and a return to the wide view."

retention_analysis:
- One line per Subject.
- Format: `<Subject N> (appears in [view 1], [view 3]): fully_preserved - preserve every visual detail from <Picture N>.`
- Write in English.

detailed_description:
- Follow the MULTI-VIEW STRUCTURE rules above.
- If NOT the first segment, open with: `The video begins exactly from the previous segment's final frame, which shows: [previous final state].`
- Dialogue format: `(S2) says: <d>[Chinese] exact words</d>`. Speaker ID must match Subject number (S1 = Subject 1, S2 = Subject 2).
- Keep each dialogue line SHORT (one sentence, under 15 Chinese characters).
- NEVER translate or paraphrase dialogue.
- Write all descriptions in English except inside `<d>` tags.
- End with: `No text, no subtitles, no captions on screen.`

overall_soundscape:
- Summarize ambience and physical sounds. Explicitly write: `No background music.`
- Write in English.

non_diegetic_music:
- Write `N/A`.

━━ REFERENCE IMAGE CONVENTION ━━
- `<Picture 1>`, `<Picture 2>` correspond to: {refs_line}
- From segment 2 onward, the previous segment's final frame is `<Picture 3>` (and so on).
- Always use `<Picture N>` format, NEVER actual filenames.

━━ OUTPUT FORMAT (STRICT JSON) ━━
{{
  "segments": [
    {{
      "id": "seg_01",
      "narrative_goal": "one sentence describing what this segment accomplishes",
      "estimated_duration": 9.0,
      "views": 2,
      "prompt": "complete six-section prompt",
      "refs": ["{ref_characters[0] if ref_characters else "role1.png"}", "{ref_characters[1] if len(ref_characters) > 1 else "role2.png"}"]
    }}
  ]
}}

REMEMBER:
- Each segment should have 2–3 views.
- From seg_02 onward, refs MUST include tail_from_seg_XX.png.
- Only output JSON.
"""


def call_llm(client, model, system_prompt, script_text,
             previous_plan=None, problems=None):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Please split the following script into generation segments:\n\n{script_text}"},
    ]
    if previous_plan is not None and problems:
        messages.append({"role": "assistant", "content": json.dumps(previous_plan, ensure_ascii=False)})
        messages.append({
            "role": "user",
            "content": (
                "Your previous output failed format validation:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n\nPlease fix and output JSON again. Follow the six-section format EXACTLY."
            ),
        })

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4 if previous_plan is None else 0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"LLM 返回的不是有效 JSON：{exc}\n{content[:500]}")


def _extract_section(prompt, section, next_section):
    start_match = re.search(rf"^{re.escape(section)}\s*:", prompt, re.MULTILINE)
    if not start_match:
        return ""
    start = start_match.end()
    end_match = re.search(rf"^{re.escape(next_section)}\s*:", prompt[start:], re.MULTILINE)
    if end_match:
        return prompt[start:start + end_match.start()]
    return prompt[start:]


def validate_h3_prompt(prompt):
    errors = []

    positions = []
    for section in H3_SECTIONS:
        m = re.search(rf"^{re.escape(section)}\s*:", prompt, re.MULTILINE)
        if not m:
            errors.append(f"missing section: {section}")
        else:
            positions.append((section, m.start()))
    if not errors:
        found = [s for s, _ in sorted(positions, key=lambda x: x[1])]
        if found != H3_SECTIONS:
            errors.append(f"section order wrong: {found}")

    # 文件名
    if re.search(r"小满\d*[_\d]*\.png", prompt):
        errors.append("contains filename 小满N.png")
    if re.search(r"桃子\d*[_\d]*\.png", prompt):
        errors.append("contains filename 桃子N.png")

    # Subject 行（只在 subject_definitions 块内检查）
    subj_block = _extract_section(prompt, "subject_definitions", "summary")
    if not subj_block.strip():
        errors.append("subject_definitions block empty")
    else:
        lines = re.findall(r"<Subject \d+>[^\n]*", subj_block)
        if not lines:
            errors.append("no <Subject N> lines")
        for line in lines:
            if " is " not in line:
                errors.append(f"Subject missing 'is': {line[:80]}")
            if "<Picture " not in line:
                errors.append(f"Subject missing <Picture N>: {line[:80]}")

    # summary 前缀
    summary_block = _extract_section(prompt, "summary", "retention_analysis")
    first = summary_block.strip().splitlines()[0] if summary_block.strip() else ""
    if first and not first.startswith("["):
        errors.append(f"summary must start with '[', got: {first[:60]!r}")

    # 禁用摄影术语
    banned_terms = [
        r"\[Shot \d+\]",
        r"(?i)\bclose-?up\b",
        r"(?i)\bwide shot\b",
        r"(?i)\bmedium shot\b",
        r"(?i)\bextreme close-?up\b",
        r"(?i)over-the-shoulder",
        r"(?i)tracking shot",
        r"(?i)\bdolly\b",
        r"(?i)\bzoom\b",
        r"(?i)cut to",
        r"(?i)the camera cuts",
    ]
    for pat in banned_terms:
        if re.search(pat, prompt):
            errors.append(f"uses banned camera term: {pat}")

    return errors


def validate_visual_ban(prompt):
    errors = []
    banned = [
        (r"字幕", "contains 字幕"),
        (r"(?i)\bcaption", "contains caption"),
        (r"(?i)\bsubtitle", "contains subtitle"),
        (r"(?i)typography", "contains typography"),
        (r"(?i)text overlay", "contains text overlay"),
        (r"(?i)title card", "contains title card"),
        (r"黑底白字", "contains 黑底白字"),
    ]
    for pat, label in banned:
        if re.search(pat, prompt):
            errors.append(label)
    return errors


def validate_segments(plan):
    problems = []
    if "segments" not in plan or not isinstance(plan["segments"], list):
        return ["missing segments array"]
    if not plan["segments"]:
        return ["segments empty"]
    if len(plan["segments"]) > 5:
        problems.append(f"segment count {len(plan['segments'])} > 5")

    for i, seg in enumerate(plan["segments"]):
        tag = f"segments[{i}]"
        if not seg.get("id"):
            problems.append(f"{tag}: missing id")
            continue
        if not seg.get("prompt"):
            problems.append(f"{tag}: missing prompt")
            continue
        if not isinstance(seg.get("estimated_duration"), (int, float)):
            problems.append(f"{tag}: estimated_duration not numeric")
        elif seg["estimated_duration"] > MAX_SEGMENT_SECONDS:
            problems.append(f"{tag}: duration {seg['estimated_duration']} > {MAX_SEGMENT_SECONDS}")

        for err in validate_h3_prompt(seg["prompt"]):
            problems.append(f"{tag}: {err}")
        for err in validate_visual_ban(seg["prompt"]):
            problems.append(f"{tag}: {err}")

    return problems


def write_segments(plan, out_root, force, dry_run):
    out_root.mkdir(parents=True, exist_ok=True)
    written = []
    planned_ids = {s["id"] for s in plan["segments"]}

    if force and not dry_run:
        for existing in out_root.iterdir():
            if not existing.is_dir():
                continue
            if not re.fullmatch(r"seg_\d+[a-z]?", existing.name):
                continue
            if existing.name not in planned_ids:
                shutil.rmtree(existing)
                print(f"  清理旧目录：{existing.name}")

    for seg in plan["segments"]:
        seg_id = seg["id"]
        seg_dir = out_root / seg_id

        if seg_dir.exists() and not force and not dry_run:
            raise SystemExit(f"{seg_dir} 已存在。加 --force 覆盖。")

        if dry_run:
            written.append({
                "id": seg_id,
                "dir": str(seg_dir),
                "narrative_goal": seg["narrative_goal"],
                "duration": seg["estimated_duration"],
                "views": seg.get("views", "?"),
                "refs": seg.get("refs", []),
                "prompt_len": len(seg["prompt"]),
            })
            continue

        seg_dir.mkdir(parents=True, exist_ok=True)
        (seg_dir / "prompt.txt").write_text(seg["prompt"], encoding="utf-8")
        refs = seg.get("refs", [])
        (seg_dir / "refs.txt").write_text("\n".join(refs) + "\n", encoding="utf-8")
        meta = {
            "narrative_goal": seg["narrative_goal"],
            "estimated_duration": seg["estimated_duration"],
            "views": seg.get("views"),
            "refs": refs,
        }
        (seg_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written.append({
            "id": seg_id,
            "dir": str(seg_dir),
            "narrative_goal": seg["narrative_goal"],
            "duration": seg["estimated_duration"],
            "views": seg.get("views", "?"),
            "refs": refs,
            "prompt_len": len(seg["prompt"]),
        })

    return written


def print_summary(written, dry_run):
    print()
    print("=" * 60)
    print(f"{'[dry-run] ' if dry_run else ''}共 {len(written)} 段")
    print("=" * 60)
    total = 0
    for w in written:
        total += w["duration"]
        print(f"\n[{w['id']}] {w['duration']}s · {w['views']} 个视图 · refs={w['refs']}")
        print(f"  narrative_goal: {w['narrative_goal']}")
        print(f"  prompt 长度: {w['prompt_len']} 字符")
        if not dry_run:
            print(f"  目录: {w['dir']}")
    print()
    print(f"总时长估算: {total:.1f}s")


def main():
    args = parse_args()
    ref_characters = [s.strip() for s in args.ref_characters.split(",") if s.strip()]
    if not ref_characters:
        raise SystemExit("--ref-characters 不能为空")

    script_text = load_script(args.script)
    print(f"剧本长度: {len(script_text)} 字符")
    print(f"角色参考图: {ref_characters}")

    client, model = build_llm_client()
    print(f"使用模型: {model}")

    system_prompt = build_system_prompt(ref_characters)
    max_attempts = 1 if args.no_retry else 2
    plan = None
    problems = []

    for attempt in range(max_attempts):
        if attempt == 0:
            print("\n正在调用 LLM 规划分段...")
            plan = call_llm(client, model, system_prompt, script_text)
        else:
            print(f"\n校验失败，反馈给 LLM 重试（第 {attempt} 次）...")
            plan = call_llm(client, model, system_prompt, script_text,
                            previous_plan=plan, problems=problems)

        Path("_raw_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("正在校验格式...")
        problems = validate_segments(plan)
        if not problems:
            break

    if problems:
        print(f"\n发现 {len(problems)} 个问题，未写入文件：")
        for p in problems:
            print(f"  - {p}")
        print("\n原始输出保存在 _raw_plan.json")
        raise SystemExit(1)

    print(f"校验通过，共 {len(plan['segments'])} 段")

    written = write_segments(plan, Path(args.out_root), force=args.force, dry_run=args.dry_run)
    print_summary(written, dry_run=args.dry_run)

    if not args.dry_run:
        print("\n下一步：")
        print("  1. 检查每段 prompt.txt 的 detailed_description，确认有 2–3 个视图")
        print("  2. 跑：.venv\\Scripts\\python.exe .\\run_episode.py --trial")


if __name__ == "__main__":
    main()