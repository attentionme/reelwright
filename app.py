
import gradio as gr
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
)

# 这是个人本地应用，关闭不需要的远程追踪上传
set_tracing_disabled(disabled=True)


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
      instructions=(
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

    "check_video_requirements 已经负责进行确定性的"
    "画幅和时长检查。"
    "不要自行重新计算检查结果，"
    "应以工具返回的 checks 结果为准。"

    "当 check_video_requirements 返回的数据中包含 issue_report 时，"
    "必须优先使用 issue_report 生成面向用户的检查报告。"

    "首先说明 issue_report 中的 headline，"
    "然后按照 items 中的内容逐项解释问题。"

    "每个问题应尽量包含 title、reason 和 recommendation，"
    "分别用于说明问题名称、具体原因和处理建议。"

    "必须严格区分三种严重程度："
    "error 表示已经确认的不合规问题；"
    "warning 表示需要人工复核、标准未配置或暂时无法判断的项目；"
    "info 表示参考信息，不属于违规问题。"

    "绝对不能把 warning 描述为已经确认的违规，"
    "也不能把 info 描述为不合格。"

    "如果整体状态为 fail，应明确指出存在确定问题；"
    "如果整体状态为 needs_review，"
    "应说明目前存在需要复核的项目，不能直接判定全部合格；"
    "如果整体状态为 pass，"
    "可以说明已检查的项目未发现明确违规，"
    "但不能声称未检测的内容也已经通过。"

    "如果项目不允许背景音乐，"
    "但报告只提示存在音频流或无法确认音频内容，"
    "必须说明需要试听确认，不能直接断言存在背景音乐。"

    "如果没有独立字幕轨道，"
    "不能据此断言画面没有内嵌字幕。"

    "必须以工具返回的数据为依据，"
    "不要自行重新计算检测数值或编造检测结果。"

    "总结检查结果时，必须同时核对 issue_report 和 checks 中的结果。"
    "除确定问题外，还应列出具有明确 pass 状态的重要检查项。"
    "不要将确定失败项的数量描述为全部已获得确定结论的项目数量。"

    "项目中的 target_duration_seconds 表示整集目标时长。"
    "max_shot_duration_seconds 表示单镜头最大时长。"
    "不能混淆这两个概念。"

    "当前工具无法检查字幕、音轨内容、"
    "画面中的角色风格、构图或每个镜头的实际数量。"
    "不要声称已经完成这些检查。"

    "只根据工具返回的真实信息回答。"
    "如果工具返回错误，明确告诉用户工具执行失败。"

    "请使用中文回答。"
),
        model=model,
       tools=[
    get_project_info,
    get_video_info,
    check_video_requirements,
],
    )

    return agent, client


# Gradio 会把用户问题、对话历史和密钥传给这个函数
async def chat(message, history, api_key):
    if not api_key or not api_key.strip():
        return "请先在“模型设置”中输入 DeepSeek API Key。"

    agent, client = build_agent(api_key)

    try:
        # 将最近的聊天记录整理成上下文
        history_lines = []

        for item in (history or [])[-8:]:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content", "")

            if role == "user" and isinstance(content, str):
                history_lines.append(f"用户：{content}")
            elif role == "assistant" and isinstance(content, str):
                history_lines.append(f"助手：{content}")

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
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
    )
