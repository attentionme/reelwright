import copy
import gradio as gr
import json
import logging
import os
from pathlib import Path
logger = logging.getLogger(__name__)

from openai import AsyncOpenAI

from agents import (
    Agent,
    Runner,
    OpenAIChatCompletionsModel,
    set_tracing_disabled,
)

from tools import (
    get_project_info,
    get_video_info,
    check_video_requirements,
    check_directory_requirements,
)

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
    """读取 config.json，与默认结构逐 provider 深度合并。读取失败时回退到默认配置。"""

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

    # 顶层字段（active_provider 等）直接覆盖
    for key, value in data.items():
        if key == "providers":
            continue
        merged[key] = value

    # providers 逐项深度合并：保留默认字段，用用户值覆盖
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
    """原子写入 config.json，避免半写文件。"""

    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    tmp_path.replace(CONFIG_PATH)

def _resolve_provider_config(config, provider_name=None) -> dict:
    """
    从 config 中解析指定 provider 的完整配置。

    纯函数：不访问文件，不访问网络。

    查找顺序：
        1. 显式传入的 provider_name（若存在）
        2. config["active_provider"]
        3. "deepseek"

    api_key 不回退：缺失即返回空字符串，由调用方决定如何处理。

    返回字典字段：
        name, display_name, base_url, model, models, api_key, configured
        configured 表示 base_url 与 model 是否均非空。
    """

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

    # model 解析优先级：default_model → models[0] → 旧字段 model → 默认
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

def _save_api_key_from_ui(api_key: str) -> str:
    """把 UI 中输入的 API Key 保存到当前 active_provider。"""

    config = _read_config()
    active_provider = config.get("active_provider", "deepseek")

    providers = config.setdefault("providers", {})
    provider = providers.setdefault(active_provider, {})
    provider["api_key"] = (api_key or "").strip()

    _write_config(config)

    resolved = _resolve_provider_config(config, active_provider)
    return f"已保存到 config.json，当前平台：{resolved['display_name']}"


def _load_default_api_key() -> str:
    """按 config.json > 环境变量 > .env 的顺序读取 API Key。"""

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

# 这是个人本地应用，关闭不需要的远程追踪上传
set_tracing_disabled(disabled=True)


# ============================================================
# Agent instructions：按主题分段
#
# 每个常量承载一类指令，最终用空行连接后传给 Agent。
# 分段只是为了便于维护，最终内容与历史版本逐字一致。
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
        INSTR_TOOL_LIMITS,
    ]
)


# 根据界面输入的 API Key 创建 Agent
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
        ],
    )

    return agent, client

def _format_request_error(exc: Exception, provider: dict) -> str:
    """
    把请求异常转换为面向用户的中文提示。

    纯函数：不访问文件，不访问网络。
    """

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
    """
    从 Gradio 的 history 中提取对话行。

    兼容两种 content 格式：
    - Gradio 5.x：content 是 list of message blocks，
      例如 [{"text": "...", "type": "text"}, ...]
    - 旧格式：content 是 str

    纯函数：不访问网络，不依赖 Gradio 运行时。
    """

    lines = []

    for item in (history or [])[-8:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content", "")

        # Gradio 5.x：content 是 message block 列表
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

        # content 必须是字符串才继续
        if not isinstance(content, str):
            continue

        if not content:
            continue

        if role == "user":
            lines.append(f"用户：{content}")
        elif role == "assistant":
            lines.append(f"助手：{content}")

    return lines


# Gradio 会把用户问题、对话历史和密钥传给这个函数
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


# 密钥输入框使用密码显示形式
_startup_config = _read_config()
_active_provider_config = _resolve_provider_config(
    _startup_config,
    _startup_config.get("active_provider", "deepseek"),
)

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
        save_settings_btn = gr.Button("保存设置", scale=0)
        save_settings_status = gr.Markdown("")

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