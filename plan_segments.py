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
    parser.add_argument("--no-retry", action="store_true",
                        help="校验失败时不自动重试")
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
2. Hard limit: {MAX_SEGMENT_SECONDS:.0f} seconds per segment. If exceeded, cut near a plot boundary, never mid-causality.
3. Preferred duration: {PREFERRED_SEGMENT_RANGE[0]:.0f}–{PREFERRED_SEGMENT_RANGE[1]:.0f} seconds per segment.
4. Adjacent segments must be continuous: the next segment's narrative start = previous segment's narrative end state.
5. Do not split a complete causal chain (setup → event → reaction) across segments.
6. Total segment count: 2–5. If the script is under 300 characters, prefer 2–3 segments.
7. NEVER generate a "pure subtitle card", "black screen", or "end card" segment. If the script ending mentions subtitles, theme text, or black-background white text, IGNORE IT completely.

━━ VISUAL BANS (HIGHEST PRIORITY) ━━
In all prompts, NEVER describe subtitles, captions, on-screen text, typography, text overlays, title cards, black-background white text, speech bubbles, or readable characters. IGNORE any subtitle/theme-text description in the script.

━━ OFFICIAL H3 Ref2VA SIX-SECTION FORMAT (ORDER AND HEADINGS MUST BE EXACT) ━━

subject_definitions:
- One line per Subject.
- Format: `<Subject N> is [name], the [person] in <Picture N>, with all facial features, hairstyle, clothing, body proportions, and art style preserved exactly from <Picture N>. The character must be rendered in the exact 2D hand-drawn style of <Picture N>, with clean dark outlines and flat colors.`
- CRITICAL: Do NOT invent or describe specific facial features, hair color, clothing color, or body type. The reference image already contains all of that. Your job is to LOCK it, not to re-imagine it.
- Identity MUST be inside the Subject line. NEVER write a separate line like `<Picture N> is the reference for ...`.
- Do NOT write actual filenames. Use `<Picture N>` only.
- Keep the Subject order stable: <Subject 1> must always be the SAME character across all segments, and <Subject 2> must always be the SAME character. Do not swap their order between segments.
- Write in English.

summary:
- One short English paragraph.
- Begin with a bracketed prefix: `[reference generation]` or `[keyframe completion]`.
- Do NOT write meta descriptions like "this is segment N".

retention_analysis:
- One line per Subject.
- Format: `<Subject N> (appears in [Shot 1], [Shot 2]): fully_preserved - preserve every visual detail from <Picture N> including face shape, eye shape, hairstyle, clothing color and cut, body proportions, and 2D hand-drawn line style.`
- Use `fully_preserved` for every Subject. Do not downgrade to `partially_preserved` unless the story explicitly requires a change.
- Write in English.

detailed_description:
- Write in playback order. Describe composition, subject position, environment and lighting, actions and state changes, camera movement, current sound.
- If NOT the first segment, open with: `The video begins exactly from the previous segment's final frame, which shows: [previous final state].`
- Dialogue MUST be formatted as: `(S1) says: <d>[Chinese] exact words</d>` or `(S2) says: <d>[Chinese] exact words</d>`.
- CRITICAL: Speaker ID MUST match the Subject number.
  * If <Subject 1> speaks, use (S1).
  * If <Subject 2> speaks, use (S2).
  * Do NOT assign speaker IDs by order of first vocal event. (S1) ALWAYS means <Subject 1>, regardless of who speaks first.
  * Example: if <Subject 1> is 小满 and <Subject 2> is 桃子, then 桃子's line is `(S2) says: <d>[Chinese] ...</d>` and 小满's line is `(S1) says: <d>[Chinese] ...</d>`, even if 桃子 speaks first.
- Put ONLY the language tag and exact spoken words inside `<d>`.
- Keep each dialogue line SHORT (one sentence, under 15 Chinese characters).
- NEVER translate or paraphrase dialogue. Write the exact Chinese words.
- Write all descriptions in English.

overall_soundscape:
- Summarize ambience and physical sounds. Explicitly write: `No background music.`
- Write in English.

non_diegetic_music:
- Write `N/A`.

━━ REFERENCE IMAGE CONVENTION ━━
- `<Picture 1>`, `<Picture 2>` correspond to: {refs_line}
- From segment 2 onward, the previous segment's final frame is `<Picture 3>` (and so on). Write "the previous segment's final frame", do NOT specify filename.
- Always use `<Picture N>` format, NEVER actual filenames.

━━ OUTPUT FORMAT (STRICT JSON) ━━
{{
  "segments": [
    {{
      "id": "seg_01",
      "narrative_goal": "one sentence describing what this segment accomplishes",
      "estimated_duration": 8.0,
      "prompt": "complete six-section prompt, starting with subject_definitions: and ending with non_diegetic_music:\\nN/A",
      "refs": ["{ref_characters[0] if ref_characters else "role1.png"}", "{ref_characters[1] if len(ref_characters) > 1 else "role2.png"}"]
    }}
  ]
}}

REMEMBER:
- From seg_02 onward, refs MUST include tail_from_seg_01.png, etc.
- Only output JSON, no explanation text.
"""


def call_llm(client, model: str, system_prompt: str, script_text: str,
             previous_plan: dict = None, problems: list = None) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Please split the following script into generation segments:\n\n{script_text}"},
    ]
    if previous_plan is not None and problems:
        messages.append({
            "role": "assistant",
            "content": json.dumps(previous_plan, ensure_ascii=False),
        })
        messages.append({
            "role": "user",
            "content": (
                "Your previous output failed format validation. Problems:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n\nPlease fix these issues and output the complete JSON again, "
                  "following the six-section format EXACTLY. "
                  "Each <Subject N> line in subject_definitions MUST contain ' is ' "
                  "and '<Picture N>'. Each summary MUST start with a bracketed prefix "
                  "like [reference generation]."
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
        raise SystemExit(f"LLM 返回的不是有效 JSON：{exc}\n原始内容：\n{content[:500]}")


def _extract_section(prompt: str, section: str, next_section: str) -> str:
    """按 section header 提取内容。用位置匹配，避免正则模糊性。"""
    start_match = re.search(
        rf"^{re.escape(section)}\s*:",
        prompt,
        re.MULTILINE,
    )
    if not start_match:
        return ""
    start = start_match.end()
    end_match = re.search(
        rf"^{re.escape(next_section)}\s*:",
        prompt[start:],
        re.MULTILINE,
    )
    if end_match:
        return prompt[start:start + end_match.start()]
    return prompt[start:]


def validate_h3_prompt(prompt: str) -> list:
    errors = []

    # 1. 六段式是否齐全、顺序是否正确
    positions = []
    for section in H3_SECTIONS:
        pattern = rf"^{re.escape(section)}\s*:"
        m = re.search(pattern, prompt, re.MULTILINE)
        if not m:
            errors.append(f"missing section: {section}")
        else:
            positions.append((section, m.start()))
    if not errors:
        found_order = [s for s, _ in sorted(positions, key=lambda x: x[1])]
        if found_order != H3_SECTIONS:
            errors.append(
                f"section order wrong: actual {found_order}, expected {H3_SECTIONS}"
            )

    # 2. 文件名不能出现
    if re.search(r"小满\d*[_\d]*\.png", prompt):
        errors.append("prompt contains filename '小满N.png'")
    if re.search(r"桃子\d*[_\d]*\.png", prompt):
        errors.append("prompt contains filename '桃子N.png'")

    # 3. 只在 subject_definitions 范围内检查 Subject 行
    subj_block = _extract_section(prompt, "subject_definitions", "summary")
    if not subj_block.strip():
        errors.append("subject_definitions block is empty")
    else:
        subject_lines = re.findall(r"<Subject \d+>[^\n]*", subj_block)
        if not subject_lines:
            errors.append(
                f"no <Subject N> lines found in subject_definitions "
                f"(block: {subj_block[:150]!r})"
            )
        for line in subject_lines:
            if " is " not in line:
                errors.append(f"Subject line missing 'is': {line[:100]}")
            if "<Picture " not in line:
                errors.append(f"Subject line missing <Picture N>: {line[:100]}")

    # 4. summary 前缀
    summary_block = _extract_section(prompt, "summary", "retention_analysis")
    first_line = summary_block.strip().splitlines()[0] if summary_block.strip() else ""
    if first_line and not first_line.startswith("["):
        errors.append(
            f"summary must start with bracketed prefix, got: {first_line[:60]!r}"
        )

    return errors


def validate_visual_ban(prompt: str) -> list:
    errors = []
    banned_patterns = [
        (r"字幕", "contains 「字幕」"),
        (r"(?i)\bcaption", "contains 'caption'"),
        (r"(?i)\bsubtitle", "contains 'subtitle'"),
        (r"(?i)typography", "contains 'typography'"),
        (r"(?i)text overlay", "contains 'text overlay'"),
        (r"(?i)title card", "contains 'title card'"),
        (r"黑底白字", "contains 「黑底白字」"),
    ]
    for pattern, label in banned_patterns:
        if re.search(pattern, prompt):
            errors.append(label)
    return errors


def validate_segments(plan: dict) -> list:
    problems = []
    if "segments" not in plan or not isinstance(plan["segments"], list):
        return ["LLM 输出缺少 segments 数组"]
    if not plan["segments"]:
        return ["segments 数组为空"]

    if len(plan["segments"]) > 5:
        problems.append(f"段数过多：{len(plan['segments'])} 段，应控制在 2–5 段")

    for i, seg in enumerate(plan["segments"]):
        tag = f"segments[{i}]"
        if not seg.get("id"):
            problems.append(f"{tag} 缺少 id")
            continue
        if not seg.get("narrative_goal"):
            problems.append(f"{tag} 缺少 narrative_goal")
        if not seg.get("prompt"):
            problems.append(f"{tag} 缺少 prompt")
            continue
        if not isinstance(seg.get("estimated_duration"), (int, float)):
            problems.append(f"{tag} estimated_duration 不是数字")
        elif seg["estimated_duration"] > MAX_SEGMENT_SECONDS:
            problems.append(
                f"{tag} estimated_duration={seg['estimated_duration']}s "
                f"超过上限 {MAX_SEGMENT_SECONDS}s"
            )

        for err in validate_h3_prompt(seg["prompt"]):
            problems.append(f"{tag}: {err}")
        for err in validate_visual_ban(seg["prompt"]):
            problems.append(f"{tag}: 视觉禁令违反 - {err}")

    return problems


def write_segments(plan: dict, out_root: Path, force: bool, dry_run: bool):
    out_root.mkdir(parents=True, exist_ok=True)
    written = []
    planned_ids = {seg["id"] for seg in plan["segments"]}

    if force and not dry_run:
        for existing in out_root.iterdir():
            if not existing.is_dir():
                continue
            if not re.fullmatch(r"seg_\d+", existing.name):
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
                "refs": seg.get("refs", []),
                "prompt_len": len(seg["prompt"]),
            })
            continue

        seg_dir.mkdir(parents=True, exist_ok=True)
        (seg_dir / "prompt.txt").write_text(seg["prompt"], encoding="utf-8")

        refs = seg.get("refs", [])
        (seg_dir / "refs.txt").write_text(
            "\n".join(refs) + "\n", encoding="utf-8"
        )

        meta = {
            "narrative_goal": seg["narrative_goal"],
            "estimated_duration": seg["estimated_duration"],
            "refs": refs,
        }
        (seg_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        written.append({
            "id": seg_id,
            "dir": str(seg_dir),
            "narrative_goal": seg["narrative_goal"],
            "duration": seg["estimated_duration"],
            "refs": refs,
            "prompt_len": len(seg["prompt"]),
        })

    return written


def print_summary(written: list, dry_run: bool):
    print()
    print("=" * 60)
    print(f"{'[dry-run] ' if dry_run else ''}共 {len(written)} 段")
    print("=" * 60)
    total = 0
    for w in written:
        total += w["duration"]
        print(f"\n[{w['id']}] {w['duration']}s · refs={w['refs']}")
        print(f"  narrative_goal: {w['narrative_goal']}")
        print(f"  prompt 长度: {w['prompt_len']} 字符")
        if not dry_run:
            print(f"  目录: {w['dir']}")
    print()
    print(f"总时长估算: {total:.1f}s")


def main():
    args = parse_args()

    ref_characters = [
        s.strip() for s in args.ref_characters.split(",") if s.strip()
    ]
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
            print(f"\n格式校验失败，反馈给 LLM 重试（第 {attempt} 次）...")
            plan = call_llm(
                client, model, system_prompt, script_text,
                previous_plan=plan, problems=problems,
            )

        Path("_raw_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("正在校验格式...")
        problems = validate_segments(plan)
        if not problems:
            break

    if problems:
        print(f"\n发现 {len(problems)} 个问题，未写入文件：")
        for p in problems:
            print(f"  - {p}")
        print(f"\nLLM 原始输出已保存到 _raw_plan.json，可打开查看具体内容")
        raise SystemExit(1)

    print(f"校验通过，共 {len(plan['segments'])} 段")

    written = write_segments(
        plan,
        Path(args.out_root),
        force=args.force,
        dry_run=args.dry_run,
    )

    print_summary(written, dry_run=args.dry_run)

    if not args.dry_run:
        print("\n下一步：")
        print("  1. 人工检查每段的 prompt.txt 和 narrative_goal")
        print(f"  2. 确认无误后运行：")
        print(f"     .\\.venv\\Scripts\\python.exe .\\batch_run.py --segment seg_01 "
              f"--profile workflow_profile_2.json --count 1 --megapixels 1.5 --duration <该段时长>")


if __name__ == "__main__":
    main()