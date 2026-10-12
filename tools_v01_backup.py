import json
from pathlib import Path

from agents import function_tool


# 获取当前项目目录
PROJECT_FILE = Path(__file__).with_name("project.json")


def load_project_data() -> dict:
    """
    读取 project.json，并返回 Python 字典。
    """
    if not PROJECT_FILE.exists():
        raise FileNotFoundError(
            f"找不到项目文件：{PROJECT_FILE}"
        )

    with PROJECT_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


@function_tool
def get_project_info() -> str:
    """
    获取当前动画项目的完整项目资料。
    """

    print("\n【工具执行记录】get_project_info 已被调用")

    try:
        project = load_project_data()

        return json.dumps(
            project,
            ensure_ascii=False,
            indent=2
        )

    except Exception as exc:
        return f"读取项目资料失败：{exc}"


@function_tool
def check_duration(duration_seconds: int) -> str:
    """
    检查指定的视频时长是否符合当前项目的要求。

    Args:
        duration_seconds: 要检查的视频时长，单位为秒。
    """

    print(
        "\n【工具执行记录】"
        f"check_duration({duration_seconds}) 已被调用"
    )

    try:
        project = load_project_data()

        target = project["target_duration_seconds"]
        maximum = project["max_shot_duration_seconds"]

        result = []

        # 检查整段视频目标时长
        if duration_seconds == target:
            result.append(
                f"总时长 {duration_seconds} 秒，"
                f"符合项目目标时长 {target} 秒。"
            )

        elif duration_seconds < target:
            result.append(
                f"总时长 {duration_seconds} 秒，"
                f"低于项目目标时长 {target} 秒。"
            )

        else:
            result.append(
                f"总时长 {duration_seconds} 秒，"
                f"超过项目目标时长 {target} 秒。"
            )

        # 检查单个镜头最大时长
        if duration_seconds <= maximum:
            result.append(
                f"单段 {duration_seconds} 秒没有超过"
                f"单镜头最大时长 {maximum} 秒。"
            )
        else:
            result.append(
                f"单段 {duration_seconds} 秒超过"
                f"单镜头最大时长 {maximum} 秒。"
            )

        return "\n".join(result)

    except Exception as exc:
        return f"时长检查失败：{exc}"