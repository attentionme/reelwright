import copy
import csv
import gradio as gr
import json
import logging
import os
import re
from pathlib import Path

from openai import AsyncOpenAI

from agents import (
    Agent,
    Runner,
    OpenAIChatCompletionsModel,
    function_tool,
    set_tracing_disabled,
)

from tools import (
    get_project_info,
    get_video_info,
    check_video_requirements,
    check_directory_requirements,
)


logger = logging.getLogger(__name__)


CONFIG_PATH = Path(__file__).with_name("config.json")

DEFAULT_CONFIG = {
    "active_provider": "deepseek",
    "providers": {
        "deepseek": {
            "display_name": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "models": ["deepseek-flash", "deepseek-v4-pro"],
            "default_model": "deepseek-flash",
            "api_key": "",
        },
        "doubao": {
            "display_name": "豆包（火山方舟）",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "models": ["doubao-seed-1-6-250615"],
            "default_model": "doubao-seed-1-6-250615",
            "api_key": "",
        },
        "qwen": {
            "display_name": "通义千问（阿里云百炼）",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-plus", "qwen-max"],
            "default_model": "qwen-plus",
            "api_key": "",
        },
        "kimi": {
            "display_name": "Kimi（月之暗面）",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["kimi-k2-0905-preview"],
            "default_model": "kimi-k2-0905-preview",
            "api_key": "",
        },
        "zhipu": {
            "display_name": "智谱 GLM",
            "base_url": "https://open.bigmodel.cn/api/paas/v4/",
            "models": ["glm-4.6", "glm-4.5-air"],
            "default_model": "glm-4.6",
            "api_key": "",
        },
        "openai": {
            "display_name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-5.2", "gpt-5.2-mini"],
            "default_model": "gpt-5.2",
            "api_key": "",
        },
        "claude": {
            "display_name": "Anthropic Claude（OpenAI 兼容层）",
            "base_url": "https://api.anthropic.com/v1/",
            "models": ["claude-sonnet-4-5-20250929"],
            "default_model": "claude-sonnet-4-5-20250929",
            "api_key": "",
        },
    },
}


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:
        logger.exception("读取 config.json 失败，使用默认配置")
        return copy.deepcopy(DEFAULT_CONFIG)

    merged = copy.deepcopy(DEFAULT_CONFIG)

    if not isinstance(data, dict):
        return merged

    for key, value in data.items():
        if key == "providers":
            continue
        merged[key] = value

    data_providers = data.get("providers")
    if isinstance(data_providers, dict):
        merged_providers = merged.setdefault("providers", {})
        for name, provider_data in data_providers.items():
            if not isinstance(provider_data, dict):
                continue
            existing = merged_providers.get(name)
            if isinstance(existing, dict):
                existing.update(provider_data)
            else:
                merged_providers[name] = dict(provider_data)

    return merged


def _write_config(config: dict) -> None:
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    tmp_path.replace(CONFIG_PATH)


def _resolve_provider_config(config, provider_name=None) -> dict:
    if not isinstance(config, dict):
        config = {}

    providers = config.get("providers")
    if not isinstance(providers, dict):
        providers = {}

    default_cfg = DEFAULT_CONFIG["providers"]["deepseek"]

    candidates = []
    if isinstance(provider_name, str) and provider_name.strip():
        candidates.append(provider_name.strip())
    active = config.get("active_provider")
    if isinstance(active, str) and active.strip():
        candidates.append(active.strip())
    candidates.append("deepseek")

    chosen_name = candidates[-1]
    for name in candidates:
        if name in providers:
            chosen_name = name
            break

    raw = providers.get(chosen_name)
    if not isinstance(raw, dict):
        raw = {}

    is_default_provider = chosen_name == "deepseek"

    base_url = raw.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        base_url = default_cfg["base_url"] if is_default_provider else ""

    display_name = raw.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = chosen_name

    model = raw.get("default_model")
    if not isinstance(model, str) or not model.strip():
        models_field = raw.get("models")
        if (
            isinstance(models_field, list)
            and models_field
            and isinstance(models_field[0], str)
        ):
            model = models_field[0]
        else:
            legacy = raw.get("model")
            if isinstance(legacy, str) and legacy.strip():
                model = legacy
            elif is_default_provider:
                model = default_cfg["default_model"]
            else:
                model = ""

    models_list = raw.get("models")
    if not isinstance(models_list, list) or not models_list:
        models_list = [model] if model else []

    api_key = raw.get("api_key")
    if not isinstance(api_key, str):
        api_key = ""

    configured = bool(base_url and model)

    return {
        "name": chosen_name,
        "display_name": display_name,
        "base_url": base_url,
        "model": model,
        "models": models_list,
        "api_key": api_key,
        "configured": configured,
    }


def _provider_options(config) -> tuple:
    if not isinstance(config, dict):
        config = {}

    providers = config.get("providers")
    if not isinstance(providers, dict) or not providers:
        providers = DEFAULT_CONFIG.get("providers", {})

    choices = []
    for name, provider_data in providers.items():
        if not isinstance(name, str) or not name:
            continue
        label = name
        if isinstance(provider_data, dict):
            display = provider_data.get("display_name")
            if isinstance(display, str) and display.strip():
                label = display.strip()
        choices.append((label, name))

    choices.sort(key=lambda item: (item[1] != "deepseek", item[1]))

    if not choices:
        return [], "deepseek"

    names = [item[1] for item in choices]
    active = config.get("active_provider", "deepseek")

    if not isinstance(active, str) or active not in names:
        active = choices[0][1]

    return choices, active


def _save_api_key_from_ui(api_key: str) -> str:
    config = _read_config()
    active_provider = config.get("active_provider", "deepseek")

    providers = config.setdefault("providers", {})
    provider = providers.setdefault(active_provider, {})
    provider["api_key"] = (api_key or "").strip()

    _write_config(config)

    resolved = _resolve_provider_config(config, active_provider)
    return f"已保存到 config.json，当前平台：{resolved['display_name']}"


def _switch_active_provider(provider_name: str):
    config = _read_config()
    providers = config.get("providers", {})

    if not isinstance(provider_name, str) or provider_name not in providers:
        resolved = _resolve_provider_config(
            config, config.get("active_provider")
        )
        return (
            gr.update(
                value=resolved["api_key"],
                label=f"{resolved['display_name']} API Key",
            ),
            f"无效的平台标识：{provider_name}",
        )

    config["active_provider"] = provider_name
    _write_config(config)

    resolved = _resolve_provider_config(config, provider_name)

    return (
        gr.update(
            value=resolved["api_key"],
            label=f"{resolved['display_name']} API Key",
        ),
        f"已切换到 {resolved['display_name']}",
    )


def _load_default_api_key() -> str:
    config = _read_config()
    provider = _resolve_provider_config(config, config.get("active_provider"))
    key = provider["api_key"].strip()

    if key:
        return key

    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    env_path = Path(__file__).with_name(".env")

    if not env_path.exists():
        return ""

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        name, _, value = line.partition("=")

        if name.strip() == "DEEPSEEK_API_KEY":
            return value.strip().strip('"').strip("'")

    return ""


DEFAULT_API_KEY = _load_default_api_key()

set_tracing_disabled(disabled=True)


# ============================================================
# 集状态检查工具（只读，不执行任何生成脚本）
# ============================================================

def _read_episode_id() -> str:
    p = Path(__file__).with_name("episode.txt")
    if p.exists():
        text = p.read_text(encoding="utf-8-sig").strip()
        if text:
            return text
    return "ep01"


def _scan_segments() -> list:
    root = Path(__file__).with_name("segments")
    if not root.exists():
        return []

    segs = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if not re.fullmatch(r"seg_\d+", d.name):
            continue

        meta = {}
        meta_path = d / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        segs.append({
            "id": d.name,
            "duration": meta.get("estimated_duration"),
            "views": meta.get("views"),
            "narrative_goal": meta.get("narrative_goal"),
        })

    segs.sort(key=lambda s: int(s["id"].split("_")[1]))
    return segs


def _scan_batches(seg_id: str) -> list:
    root = Path(__file__).with_name("batches")
    if not root.exists():
        return []

    compact = seg_id.replace("_", "")
    batches = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if not (
            d.name.startswith(compact + "_")
            or d.name.startswith(seg_id + "_")
        ):
            continue
        mp4s = sorted(d.glob("*.mp4"))
        if not mp4s:
            continue
        batches.append({
            "name": d.name,
            "videos": [m.name for m in mp4s],
            "mtime": d.stat().st_mtime,
        })

    batches.sort(key=lambda b: b["mtime"], reverse=True)
    return batches


def _read_marks() -> dict:
    p = Path(__file__).with_name("review_marks.json")
    if not p.exists():
        return {"episode": "", "liked": [], "rejected": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"episode": "", "liked": [], "rejected": []}


def _segment_status(seg_id: str, liked_keys: set) -> dict:
    batches = _scan_batches(seg_id)
    if not batches:
        return {
            "batch_count": 0,
            "video_count": 0,
            "latest_batch": None,
            "liked": [],
            "status": "pending",
        }

    seg_liked = [
        k for k in liked_keys
        if any(k.startswith(b["name"] + "/") for b in batches)
    ]

    return {
        "batch_count": len(batches),
        "video_count": sum(len(b["videos"]) for b in batches),
        "latest_batch": batches[0]["name"],
        "liked": seg_liked,
        "status": "reviewed" if seg_liked else "generated",
    }


@function_tool
def inspect_episode() -> str:
    """
    扫描当前集的分镜、批次、标记状态，返回结构化 JSON。

    当用户问“现在什么状态”“跑到哪了”“哪段还没跑”“哪段还没标记”时调用。
    """
    episode = _read_episode_id()
    segments = _scan_segments()
    marks = _read_marks()
    liked_keys = set(marks.get("liked", []))

    result_segments = []
    for seg in segments:
        status = _segment_status(seg["id"], liked_keys)
        result_segments.append({
            "id": seg["id"],
            "duration": seg["duration"],
            "views": seg["views"],
            "narrative_goal": seg["narrative_goal"],
            **status,
        })

    return json.dumps({
        "episode": episode,
        "segment_count": len(segments),
        "segments": result_segments,
    }, ensure_ascii=False, indent=2)


@function_tool
def plan_next_step() -> str:
    """
    根据当前状态，返回下一步应该执行的命令。

    当用户问“下一步做什么”“我该跑什么”“接下来怎么办”时调用。
    本工具只返回命令建议，不执行命令。
    """
    segments = _scan_segments()

    if not segments:
        return (
            "当前没有 segments。先运行：\n"
            ".venv\\Scripts\\python.exe .\\plan_segments.py "
            "--script script.txt "
            "--ref-characters 小满1_2048.png,桃子1_2048.png "
            "--force"
        )

    marks = _read_marks()
    liked_keys = set(marks.get("liked", []))

    pending_generation = []
    pending_review = []
    reviewed = []

    for seg in segments:
        status = _segment_status(seg["id"], liked_keys)
        if status["status"] == "pending":
            pending_generation.append(seg["id"])
        elif status["status"] == "generated":
            pending_review.append(seg["id"])
        else:
            reviewed.append(seg["id"])

    lines = []

    if pending_generation:
        lines.append(
            f"还有 {len(pending_generation)} 段没有生成："
            f"{', '.join(pending_generation)}"
        )
        lines.append(
            f"建议先跑：\n"
            f".venv\\Scripts\\python.exe .\\pipeline.py "
            f"--segment {pending_generation[0]} --count 2"
        )
    elif pending_review:
        lines.append(
            f"还有 {len(pending_review)} 段没有标记喜欢："
            f"{', '.join(pending_review)}"
        )
        lines.append(
            "建议打开对应的 review.html，点击喜欢的视频，"
            "然后点「导出本集全部标记」，把 review_marks.json 覆盖到项目目录。"
        )
    else:
        lines.append(f"全部 {len(segments)} 段都已标记喜欢。")
        lines.append(
            "下一步：\n"
            ".venv\\Scripts\\python.exe .\\concat_episode.py"
        )

    return "\n".join(lines)


@function_tool
def summarize_review() -> str:
    """
    汇总 review_marks.json 的标记情况：哪些段标记了、哪些段没标记。

    当用户问“review 标记了几段”“还有哪段没挑”“哪些已选好”时调用。
    """
    episode = _read_episode_id()
    segments = _scan_segments()
    marks = _read_marks()
    liked_keys = set(marks.get("liked", []))

    rows = []
    for seg in segments:
        status = _segment_status(seg["id"], liked_keys)
        rows.append({
            "id": seg["id"],
            "status": status["status"],
            "liked": status["liked"],
        })

    return json.dumps({
        "episode": episode,
        "total_liked": len(liked_keys),
        "segments": rows,
    }, ensure_ascii=False, indent=2)


# ============================================================
# 后台生成任务工具（真正执行，通过 task_manager.py）
# ============================================================

@function_tool
def start_generation(
    segment: str,
    count: int = 2,
    megapixels: float = 1.5,
    force: bool = True,
) -> str:
    """
    后台启动一段视频生成（pipeline.py），立即返回 task_id，不阻塞对话。

    当用户说“帮我跑 seg_XX”“重跑 seg_XX”“生成 seg_XX”时调用。
    本工具会在后台运行 pipeline.py，不会阻塞对话。启动后立即返回 task_id。
    """
    from task_manager import start_task

    args = [
        "--segment", segment,
        "--count", str(count),
        "--megapixels", str(megapixels),
    ]
    if force:
        args.append("--force")

    try:
        task = start_task("pipeline.py", args)
    except Exception as exc:
        return json.dumps(
            {"error": f"启动失败：{type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )

    return json.dumps(task, ensure_ascii=False, indent=2)


@function_tool
def check_generation(task_id: str) -> str:
    """
    查询一个后台生成任务的状态。

    当用户问“跑完了吗”“那个任务怎么样了”“seg_XX 跑完了吗”时调用。
    状态为 running / done / failed。
    """
    from task_manager import check_task

    try:
        task = check_task(task_id)
    except Exception as exc:
        return json.dumps(
            {"error": f"查询失败：{type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )

    return json.dumps(task, ensure_ascii=False, indent=2)


@function_tool
def list_generations() -> str:
    """
    列出最近的后台生成任务。

    当用户问“有哪些任务在跑”“最近跑了什么”“任务列表”时调用。
    返回最近 10 个任务，按时间倒序。
    """
    from task_manager import list_tasks

    try:
        tasks = list_tasks()
    except Exception as exc:
        return json.dumps(
            {"error": f"查询失败：{type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )

    return json.dumps(tasks, ensure_ascii=False, indent=2)


# ============================================================
# Agent instructions
# ============================================================

INSTR_ROLE_AND_ROUTING = (
    "你是一名动画制作助手。"
    "当用户询问项目的画幅、目标时长、"
    "角色风格或其他项目资料时，"
    "调用 get_project_info 查询真实项目文件。"
    "如果用户要求检查具体视频是否符合项目规范，"
    "只使用 check_video_requirements 完成规范检查。"
    "不要为了进行规范检查而额外调用 get_project_info。"
    "check_video_requirements 会自行读取项目配置。"
    "只有当用户单独询问项目资料或配置，"
    "且没有要求检查具体视频时，"
    "才调用 get_project_info。"
    "只有当用户只要求读取视频实际信息，"
    "而不要求检查项目规范时，"
    "才调用 get_video_info。"
    "当用户要求检查具体视频是否符合项目规范时，"
    "使用 check_video_requirements 完成规范检查。"
    "check_video_requirements 会自行读取视频元数据"
    "和项目配置。"
    "进行这项规范检查时，不要再额外调用"
    "get_project_info 或 get_video_info 重复获取数据。"
    "如果用户明确说明视频是整集，"
    "使用 episode。"
    "如果用户明确说明视频是单个镜头，"
    "使用 shot。"
    "如果用户没有说明视频是整集还是单个镜头，"
    "不要自行猜测。"
    "先获取视频实际信息；"
    "如果规范检查必须区分视频范围，"
    "向用户询问视频属于整集还是单个镜头。"
    "如果用户在后续对话中补充了视频范围，"
    "并且之前的对话里已经提供了视频路径，"
    "应结合对话历史直接执行规范检查，"
    "不要再次询问视频路径。"
    "check_video_requirements 已经负责进行确定性的"
    "画幅和时长检查。"
    "不要自行重新计算检查结果，"
    "应优先以工具返回的 issue_report 为准；"
    "只有 issue_report 缺失时，才参考 checks。"
)

INSTR_REPORT_FORMAT = (
    "当 check_video_requirements 返回结果中包含 issue_report 时，"
    "必须优先根据 issue_report 生成完整的中文检查报告。"
    "先说明 overall_status 和 headline。"
    "然后按照 items 中的 severity 分类展示检查结果："
    "error 是已经确认的不合规问题；"
    "warning 是需要复核、检测能力不足或标准未配置的项目；"
    "info 是参考信息，不属于违规问题。"
    "每个问题应使用 title、reason 和 recommendation，"
    "说明问题名称、具体原因和处理建议。"
    "随后检查 passed_items，"
    "列出其中具有明确 pass 状态的重要检查项。"
    "如果存在 status 为 at_target 的项目，"
    "应单独说明已达到目标，不要把它误认为普通违规问题。"
    "如果 not_applicable_items 不为空，"
    "应说明这些项目不适用，不得将其计为违规或通过。"
    "如果 unclassified_items 不为空，"
    "应说明这些项目的状态暂时无法归类，需要进一步核实，"
    "不能擅自将其判为合格或不合格。"
    "可以使用 issue_report 中的 counts 和 headline 汇总结果，"
    "不要根据 checks 重新计算统计数字。"
)

INSTR_SAFETY = (
    "必须严格区分 error、warning 和 info。"
    "绝对不能把 warning 描述为已经确认的违规，"
    "也不能把 info 描述为不合格。"
    "如果整体状态为 fail，应明确指出存在确定问题。"
    "如果整体状态为 needs_review，应明确说明仍有项目待复核。"
    "如果整体状态为 pass，只能说明已检查的项目没有发现明确违规，"
    "不能声称所有未经检测的内容也已经通过。"
    "如果项目不允许背景音乐，"
    "但报告只提示存在音频流或无法确认音频内容，"
    "必须说明需要试听确认，不能断言存在背景音乐。"
    "没有独立字幕轨道不代表画面没有内嵌字幕。"
    "不能仅凭没有字幕轨道就判定画面中不存在文字。"
    "如果 issue_report 缺失，才参考 checks 组织报告，"
    "并且只能陈述检测数据能够支持的结论。"
    "不要自行重新计算检测数值，也不要编造检测结果。"
)

INSTR_CONFIG_FIELDS = (
    "项目中的 target_duration_seconds 表示整集目标时长。"
    "max_shot_duration_seconds 表示单镜头最大时长。"
    "不能混淆这两个概念。"
    "项目中的 target_fps 表示目标帧率，"
    "target_duration_tolerance_seconds 表示整集目标时长的允许误差。"
    "这两个字段都是可选配置："
    "如果 project.json 中没有 target_fps，"
    "fps 检查会返回 not_configured，而不是 pass 或 fail。"
    "如果没有 target_duration_tolerance_seconds，"
    "整集时长按精确匹配处理。"
    "不要在没有目标帧率时声称 fps 检查通过或失败。"
    "项目中的 video_codec 和 audio_codec 分别表示目标视频编码和目标音频编码。"
    "这两个字段同样是可选配置："
    "如果 project.json 中没有 video_codec 或 audio_codec，"
    "对应的编码检查会返回 not_configured，而不是 pass 或 fail。"
    "如果项目配置了 audio_codec，但视频没有音频流，"
    "音频编码检查会返回 not_applicable，而不是 fail。"
    "不要在没有配置目标编码时声称编码检查通过或失败。"
    "项目中的 file_name_pattern 是一个正则表达式，"
    "用来规定合法的文件名格式。"
    "file_name_pattern_description 只是给人看的示例，"
    "不参与检测。"
    "如果 project.json 中没有 file_name_pattern，"
    "文件名检查会返回 not_configured。"
    "不要在没有配置命名规则时声称文件名检查通过或失败。"
    "项目中的 aspect_ratio_tolerance 表示画幅比例的相对容差，"
    "默认 0 表示只接受精确匹配。"
    "配置后，实际比例与目标比例的相对偏差在容差内的视为符合要求。"
)

INSTR_DIRECTORY = (
    "如果用户要求检查一个镜头目录，而不是单个视频文件，"
    "使用 check_directory_requirements。"
    "它只做目录级聚合：统计文件数量、汇总总时长、"
    "检查画幅 / 帧率 / 编码是否一致。"
    "它不递归子目录，也不对每个镜头执行完整的单文件规范检查。"
    "如果用户需要对每个镜头做完整规范检查，"
    "应逐个调用 check_video_requirements。"
    "目录检查返回的 duration_status 只表示总时长与整集目标时长的偏差，"
    "它本身不是一个已经判定的合规结论。"
    "报告这一项时，应说明实际总时长、目标时长和偏差量，"
    "由用户结合项目语境判断是否需要调整，"
    "不要替用户把它直接定性为「不合规」或「通过」。"
)

INSTR_AGENT_WORKFLOW = (
    "当用户询问当前集的状态、进度、下一步该做什么、"
    "或者 review 标记情况时，"
    "调用 inspect_episode、plan_next_step、summarize_review "
    "这三个工具获取真实数据。"
    "不要凭记忆或猜测回答。"
    "当用户说“帮我跑 seg_XX”“重跑 seg_XX”“生成 seg_XX”时，"
    "调用 start_generation 工具，参数 segment=seg_XX，"
    "count 默认 2，megapixels 默认 1.5，force 默认 True。"
    "启动后立即告诉用户 task_id，"
    "并说明“后台运行中，预计 20–30 分钟，稍后可以问我跑完了吗”。"
    "不要阻塞等待完成，不要假装已经看到结果。"
    "当用户问“跑完了吗”“那个任务怎么样了”“seg_XX 跑完了吗”时，"
    "调用 check_generation，传用户提到的 task_id；"
    "如果用户没提 task_id，先调用 list_generations 找到最近的 running 任务。"
    "任务状态为 done 时，告诉用户“已完成”，"
    "并从 log_tail 里提取关键信息（生成了几个候选、审片页面路径）。"
    "任务状态为 failed 时，告诉用户“失败了”，"
    "并贴出 log_tail 尾部的错误信息，"
    "建议用户检查 ComfyUI 是否在线、显存是否足够。"
    "当用户问“有哪些任务在跑”“最近跑了什么”时，调用 list_generations。"
    "如果用户要求“帮我跑一段”但你没有 start_generation 工具，"
    "必须给出完整、可直接复制粘贴的命令，"
    "格式为：.venv\\Scripts\\python.exe .\\pipeline.py "
    "--segment seg_XX --count 2 --megapixels 1.5"
    "（segment 用用户提到的段名，count 默认 2，"
    "megapixels 默认 1.5）。"
    "如果用户要求的段已经生成过视频，"
    "先说“该段已有 N 个视频”，"
    "再给出重跑命令（带 --force），"
    "同时给出查看现有结果的 review.html 完整路径，"
    "格式为 batches/<最新批次名>/review.html，"
    "最新批次名可以从 inspect_episode 返回的 latest_batch 字段拿到，"
    "不要只说“去看输出目录”。"
    "不要替用户决定哪个视频“更好看”，"
    "审美判断交给用户。"
    "挑片这一步必须由用户打开 review.html 亲自完成。"
)

INSTR_TOOL_LIMITS = (
    "当前工具无法检查字幕、音轨内容、"
    "画面中的角色风格、构图或每个镜头的实际数量。"
    "不要声称已经完成这些检查。"
    "只根据工具返回的真实信息回答。"
    "如果工具返回错误，明确告诉用户工具执行失败。"
    "请使用中文回答。"
)

INSTRUCTIONS = "\n\n".join(
    [
        INSTR_ROLE_AND_ROUTING,
        INSTR_REPORT_FORMAT,
        INSTR_SAFETY,
        INSTR_CONFIG_FIELDS,
        INSTR_DIRECTORY,
        INSTR_AGENT_WORKFLOW,
        INSTR_TOOL_LIMITS,
    ]
)


def build_agent(api_key_override: str = ""):
    config = _read_config()
    provider = _resolve_provider_config(config, config.get("active_provider"))

    if not provider["configured"]:
        raise ValueError(
            f"平台 {provider['display_name']} 的配置不完整："
            f"base_url={'缺失' if not provider['base_url'] else '已配置'}，"
            f"model={'缺失' if not provider['model'] else '已配置'}。"
            "请在 config.json 中补全该平台的配置后重试。"
        )

    api_key = (api_key_override or "").strip() or provider["api_key"]

    if not api_key:
        raise ValueError(
            f"平台 {provider['display_name']} 未配置 API Key。"
            "请在“模型设置”中输入 Key，或写入 config.json 后重试。"
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=provider["base_url"],
    )

    model = OpenAIChatCompletionsModel(
        model=provider["model"],
        openai_client=client,
    )

    agent = Agent(
        name="动画制作助手",
        instructions=INSTRUCTIONS,
        model=model,
        tools=[
            get_project_info,
            get_video_info,
            check_video_requirements,
            check_directory_requirements,
            inspect_episode,
            plan_next_step,
            summarize_review,
            start_generation,
            check_generation,
            list_generations,
        ],
    )

    return agent, client


def _format_request_error(exc: Exception, provider: dict) -> str:
    display_name = provider.get("display_name") or "当前平台"
    base_url = provider.get("base_url") or ""
    model = provider.get("model") or ""

    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    if status_code in (401, 403):
        return (
            f"{display_name} 拒绝了本次请求（HTTP {status_code}）。"
            "API Key 可能无效、已过期，或不属于当前平台。"
            "请检查“模型设置”中的 Key，并确认 config.json 中 "
            "active_provider 与 Key 所属平台一致。"
        )

    if status_code == 404:
        return (
            f"{display_name} 返回 404：模型或接口地址不存在。"
            f"请检查 config.json 中 {display_name} 的 base_url"
            f"（当前 {base_url}）与 model（当前 {model}）是否正确。"
        )

    if status_code == 429:
        return f"{display_name} 返回 429：请求频率或额度受限，请稍后重试。"

    if isinstance(status_code, int) and status_code >= 500:
        return f"{display_name} 返回 {status_code}：服务端临时故障，请稍后重试。"

    message_lower = str(exc).lower()

    if "timeout" in message_lower or "timed out" in message_lower:
        return (
            f"无法在限定时间内连接到 {display_name}（{base_url}）。"
            "请检查网络、代理或防火墙设置。"
        )

    if "connection" in message_lower or "connect" in message_lower:
        return (
            f"无法连接到 {display_name}（{base_url}）。"
            "请检查网络是否通畅，代理是否正确。"
        )

    return (
        f"请求失败（{type(exc).__name__}）。当前平台：{display_name}。"
        "请检查 API Key、模型名称、网络连接和账户额度，"
        "或查看启动终端的详细日志。"
    )


def _extract_history_lines(history) -> list:
    lines = []

    for item in (history or [])[-8:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content", "")

        if isinstance(content, list):
            text_parts = []

            for block in content:
                if (
                    isinstance(block, dict)
                    and isinstance(block.get("text"), str)
                ):
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)

            content = "\n".join(text_parts)

        if not isinstance(content, str):
            continue

        if not content:
            continue

        if role == "user":
            lines.append(f"用户：{content}")
        elif role == "assistant":
            lines.append(f"助手：{content}")

    return lines


async def chat(message, history, api_key):
    try:
        agent, client = build_agent(api_key or "")
    except ValueError as exc:
        return str(exc)

    try:
        history_lines = _extract_history_lines(history)

        if history_lines:
            prompt = (
                "以下是此前的对话记录：\n"
                + "\n".join(history_lines)
                + "\n\n当前用户的问题：\n"
                + message
            )
        else:
            prompt = message

        result = await Runner.run(agent, prompt)

        return result.final_output

    except Exception as exc:
        logger.error(
            "请求失败：%s: %s",
            type(exc).__name__,
            exc,
        )
        provider = _resolve_provider_config(_read_config(), None)
        return _format_request_error(exc, provider)

    finally:
        await client.close()


_startup_config = _read_config()
_active_provider_config = _resolve_provider_config(
    _startup_config,
    _startup_config.get("active_provider", "deepseek"),
)
_provider_choices, _default_provider = _provider_options(_startup_config)

key_input = gr.Textbox(
    label=f"{_active_provider_config['display_name']} API Key",
    type="password",
    placeholder="在这里输入你的 API Key",
    value=DEFAULT_API_KEY,
)

with gr.Blocks(
    title="动画制作 Agent",
) as demo:
    gr.ChatInterface(
        fn=chat,
        title="动画制作 Agent",
        description="输入问题，让 Agent 查询项目资料并回答。",
        additional_inputs=[key_input],
        additional_inputs_accordion="模型设置",
    )

    with gr.Row():
        provider_dropdown = gr.Dropdown(
            choices=_provider_choices,
            value=_default_provider,
            label="大模型平台",
        )
        save_settings_btn = gr.Button("保存设置", scale=0)
        save_settings_status = gr.Markdown("")

    provider_dropdown.change(
        fn=_switch_active_provider,
        inputs=[provider_dropdown],
        outputs=[key_input, save_settings_status],
    )

    save_settings_btn.click(
        fn=_save_api_key_from_ui,
        inputs=[key_input],
        outputs=[save_settings_status],
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    demo.launch(
        theme=gr.themes.Soft(),
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
    )