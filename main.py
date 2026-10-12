
import os

from openai import AsyncOpenAI
from agents import (
    Agent,
    Runner,
    function_tool,
    OpenAIChatCompletionsModel,
    set_tracing_disabled,
)

# 第一步：读取 API 密钥
api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise RuntimeError(
        "没有找到 DEEPSEEK_API_KEY，请先设置 API 密钥。"
    )

# 第二步：关闭 OpenAI 平台的追踪上传
set_tracing_disabled(disabled=True)

# 第三步：连接 DeepSeek
client = AsyncOpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)

model = OpenAIChatCompletionsModel(
    model="deepseek-flash",
    openai_client=client,
)


# 第四步：编写一个 Python 工具
@function_tool
def get_project_info() -> str:
    """查询动画项目的画幅、时长和角色风格。"""

    print("\n【工具执行记录】get_project_info 已被调用")

    return (
        "项目名称：动画制作助手\n"
        "画面比例：9:16\n"
        "目标时长：约45秒\n"
        "角色风格：二维角色叠加写实背景"
    )


# 第五步：创建可以使用这个工具的 Agent
agent = Agent(
    name="动画制作学习助手",
    instructions=(
        "你是一名动画制作助手。"
        "当用户询问项目已有的画幅、时长或角色风格时，"
        "必须先调用 get_project_info 工具查询资料，"
        "然后依据工具返回的内容回答。"
        "不要编造项目资料中没有的信息。"
    ),
    model=model,
    tools=[get_project_info],
)


# 第六步：执行任务
def main():
    result = Runner.run_sync(
        agent,
        "请查询项目资料，告诉我画面比例、目标时长和角色风格。",
    )

    print("\n【Agent 最终回答】")
    print(result.final_output)


if __name__ == "__main__":
    main()
