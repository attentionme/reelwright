import gradio as gr
import logging
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
def build_agent(api_key: str):
    client = AsyncOpenAI(
        api_key=api_key.strip(),
        base_url="https://api.deepseek.com",
    )

    model = OpenAIChatCompletionsModel(
        model="deepseek-flash",
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
    if not api_key or not api_key.strip():
        return "请先在“模型设置”中输入 DeepSeek API Key。"

    agent, client = build_agent(api_key)

    try:
        # 将最近的聊天记录整理成上下文
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

        # 运行 Agent，等待模型回答或调用工具
        result = await Runner.run(agent, prompt)

        return result.final_output

    except Exception as exc:
        # 不打印 API Key，也不把异常细节直接返回到聊天窗口
        print(f"请求失败，错误类型：{type(exc).__name__}")
        return (
            "请求失败。请检查 API Key、模型名称、网络连接和账户额度。"
            "具体排查时请查看启动终端。"
        )

    finally:
        # 关闭本次请求使用的客户端
        await client.close()


# 密钥输入框使用密码显示形式
key_input = gr.Textbox(
    label="DeepSeek API Key",
    type="password",
    placeholder="在这里输入你的 API Key",
)

demo = gr.ChatInterface(
    fn=chat,
    title="动画制作 Agent",
    description="输入问题，让 Agent 查询项目资料并回答。",
    additional_inputs=[key_input],
    additional_inputs_accordion="模型设置",
)

if __name__ == "__main__":
    # 启用工具调用日志，方便观察 Agent 的工具路由
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
    )