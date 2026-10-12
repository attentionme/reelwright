import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from agents import function_tool


# ============================================================
# 1. 项目配置
# ============================================================

# project.json 与当前 tools.py 位于同一个目录
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
        encoding="utf-8",
    ) as file:
        return json.load(file)


# ============================================================
# 2. Agent 工具：查询项目资料
# ============================================================

@function_tool
def get_project_info() -> str:
    """
    获取当前动画项目的完整项目资料。
    """

    print(
        "\n【Agent 工具调用记录】"
        "get_project_info 已被调用"
    )

    try:
        project = load_project_data()

        return json.dumps(
            project,
            ensure_ascii=False,
            indent=2,
        )

    except Exception as exc:
        return f"读取项目资料失败：{exc}"


# ============================================================
# 3. 普通 Python 函数：读取视频元数据
# ============================================================

def _get_video_info(video_path: str) -> str:
    """
    使用 ffprobe 读取本地视频文件的实际信息。

    Args:
        video_path: 本地视频文件的完整路径。

    Returns:
        JSON 字符串，包括：
        - file_name：文件名
        - file_path：完整路径
        - duration_seconds：视频时长
        - width：视频宽度
        - height：视频高度
        - fps：视频帧率
    """

    print(
        "\n【底层函数执行记录】"
        f"_get_video_info({video_path}) 正在执行"
    )

    try:
        # 1. 检查系统能否找到 ffprobe
        ffprobe_path = shutil.which("ffprobe")

        if not ffprobe_path:
            return "读取视频失败：系统中找不到 ffprobe。"

        # 2. 验证输入路径
        video_file = Path(
            video_path
        ).expanduser()

        if not video_file.exists():
            return (
                f"读取视频失败：文件不存在：{video_file}"
            )

        if not video_file.is_file():
            return (
                f"读取视频失败：路径不是文件：{video_file}"
            )

        # 3. 构造 ffprobe 命令
        command = [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_file),
        ]

        # 不使用 shell=True，避免通过 Shell 解释用户输入
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )

        # 4. 检查 ffprobe 的执行结果
        if result.returncode != 0:
            error_message = result.stderr.strip()

            return (
                "读取视频失败：ffprobe 无法解析该视频。"
                f"\n详细信息：{error_message}"
            )

        # 5. 解析 ffprobe 返回的 JSON
        data = json.loads(result.stdout)

        streams = data.get("streams", [])
        format_data = data.get("format", {})

        if not streams:
            return "读取视频失败：没有找到视频流。"

        video_stream = streams[0]

        # 6. 提取视频实际信息
        duration = float(format_data["duration"])

        width = int(video_stream["width"])
        height = int(video_stream["height"])

        raw_fps = video_stream.get("r_frame_rate")

        if not raw_fps or raw_fps == "0/0":
            fps = None
        else:
            fps = float(Fraction(raw_fps))

        # 7. 整理结果，供业务检查函数和 Agent 使用
        video_info = {
            "file_name": video_file.name,
            "file_path": str(video_file.resolve()),
            "duration_seconds": round(duration, 3),
            "width": width,
            "height": height,
            "fps": (
                round(fps, 3)
                if fps is not None
                else None
            ),
        }

        return json.dumps(
            video_info,
            ensure_ascii=False,
            indent=2,
        )

    except subprocess.TimeoutExpired:
        return (
            "读取视频失败：ffprobe 执行超时，"
            "已停止本次读取。"
        )

    except json.JSONDecodeError:
        return (
            "读取视频失败：ffprobe 返回的数据"
            "不是有效 JSON。"
        )

    except Exception as exc:
        return f"读取视频信息失败：{exc}"


# ============================================================
# 4. Agent 工具：直接查询视频信息
# ============================================================

@function_tool
def get_video_info(video_path: str) -> str:
    """
    读取本地视频文件的实际信息。

    Args:
        video_path: 本地视频文件的完整路径。
    """

    print(
        "\n【Agent 工具调用记录】"
        f"get_video_info({video_path}) 已被调用"
    )

    return _get_video_info(video_path)


# ============================================================
# 5. 普通 Python 函数：执行视频规范检查
# ============================================================

def _check_video_requirements(
    video_path: str,
    video_scope: str,
) -> str:
    """
    根据项目配置检查视频是否符合当前项目要求。

    Args:
        video_path:
            本地视频文件的完整路径。

        video_scope:
            episode = 整集视频
            shot = 单个镜头

    Returns:
        JSON 字符串，包含实际视频数据和规范检查结果。
    """

    print(
        "\n【业务函数执行记录】"
        f"_check_video_requirements("
        f"{video_path}, {video_scope}) 正在执行"
    )

    try:
        # ----------------------------------------------------
        # 1. 验证检查对象
        # ----------------------------------------------------

        allowed_scopes = {
            "episode",
            "shot",
        }

        if video_scope not in allowed_scopes:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        "video_scope 参数无效。"
                        "必须是 episode 或 shot。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )

        # ----------------------------------------------------
        # 2. 获取视频的真实元数据
        # ----------------------------------------------------

        # 直接调用普通 Python 函数，
        # 而不是再次调用 Agent 工具包装对象
        video_result = _get_video_info(video_path)

        try:
            video_info = json.loads(video_result)

        except json.JSONDecodeError:
            return json.dumps(
                {
                    "success": False,
                    "error": video_result,
                },
                ensure_ascii=False,
                indent=2,
            )

        # 视频读取失败时，返回明确的失败结果
        if "duration_seconds" not in video_info:
            return json.dumps(
                {
                    "success": False,
                    "error": video_result,
                },
                ensure_ascii=False,
                indent=2,
            )

        # ----------------------------------------------------
        # 3. 读取项目配置
        # ----------------------------------------------------

        project = load_project_data()

        # ----------------------------------------------------
        # 4. 获取已配置的检查要求
        # ----------------------------------------------------

        expected_aspect_ratio = project[
            "aspect_ratio"
        ]

        target_duration = float(
            project["target_duration_seconds"]
        )

        max_shot_duration = float(
            project["max_shot_duration_seconds"]
        )

        # ----------------------------------------------------
        # 5. 解析目标画幅
        # ----------------------------------------------------

        ratio_width, ratio_height = map(
            int,
            expected_aspect_ratio.split(":"),
        )

        width = video_info["width"]
        height = video_info["height"]

        # 使用整数交叉相乘，避免浮点数比较误差
        aspect_ratio_match = (
            width * ratio_height
            == height * ratio_width
        )

        actual_aspect_ratio = width / height

        actual_duration = video_info[
            "duration_seconds"
        ]

        checks = {}

        # ----------------------------------------------------
        # 6. 检查画幅
        # ----------------------------------------------------

        checks["aspect_ratio"] = {
            "status": (
                "pass"
                if aspect_ratio_match
                else "fail"
            ),
            "expected": expected_aspect_ratio,
            "actual_ratio": round(
                actual_aspect_ratio,
                6,
            ),
            "width": width,
            "height": height,
            "message": (
                "视频画幅符合项目要求。"
                if aspect_ratio_match
                else (
                    "视频画幅不符合项目要求。"
                    f"项目要求 {expected_aspect_ratio}，"
                    f"实际为 {width}:{height}。"
                )
            ),
        }

        # ----------------------------------------------------
        # 7. 根据视频范围检查时长
        # ----------------------------------------------------

        if video_scope == "episode":

            # 整集只与目标时长比较
            duration_difference = round(
                actual_duration - target_duration,
                3,
            )

            if duration_difference == 0:
                duration_status = "at_target"

                duration_message = (
                    f"整集实际时长 {actual_duration} 秒，"
                    f"与目标时长 {target_duration} 秒一致。"
                )

            elif duration_difference < 0:
                duration_status = "below_target"

                duration_message = (
                    f"整集实际时长 {actual_duration} 秒，"
                    f"比目标时长 {target_duration} 秒"
                    f"少 {abs(duration_difference)} 秒。"
                )

            else:
                duration_status = "above_target"

                duration_message = (
                    f"整集实际时长 {actual_duration} 秒，"
                    f"比目标时长 {target_duration} 秒"
                    f"多 {duration_difference} 秒。"
                )

            checks["duration"] = {
                "scope": "episode",
                "status": duration_status,
                "actual_seconds": actual_duration,
                "target_seconds": target_duration,
                "difference_seconds": duration_difference,
                "message": duration_message,
                "note": (
                    "当前项目只规定整集目标时长，"
                    "没有规定允许误差，因此只报告差异，"
                    "不自动判定整集时长是否合格。"
                ),
            }

        else:

            # 单镜头与最大时长比较
            duration_difference = round(
                actual_duration - max_shot_duration,
                3,
            )

            duration_pass = (
                actual_duration <= max_shot_duration
            )

            checks["duration"] = {
                "scope": "shot",
                "status": (
                    "pass"
                    if duration_pass
                    else "fail"
                ),
                "actual_seconds": actual_duration,
                "maximum_seconds": max_shot_duration,
                "difference_seconds": duration_difference,
                "message": (
                    f"单镜头时长 {actual_duration} 秒，"
                    f"没有超过最大时长 "
                    f"{max_shot_duration} 秒。"
                    if duration_pass
                    else (
                        f"单镜头时长 {actual_duration} 秒，"
                        f"超过最大时长 "
                        f"{max_shot_duration} 秒，"
                        f"超出 {duration_difference} 秒。"
                    )
                ),
            }

        # ----------------------------------------------------
        # 8. 记录帧率
        # ----------------------------------------------------

        checks["fps"] = {
            "status": "not_configured",
            "actual": video_info["fps"],
            "message": (
                "项目配置中没有规定目标帧率，"
                "因此只记录实际值，不进行合格性判断。"
            ),
        }

        # ----------------------------------------------------
        # 9. 整理最终检查结果
        # ----------------------------------------------------

        result = {
            "success": True,
            "video_scope": video_scope,
            "video_info": video_info,
            "project_requirements": {
                "aspect_ratio": expected_aspect_ratio,
                "target_duration_seconds": (
                    target_duration
                ),
                "max_shot_duration_seconds": (
                    max_shot_duration
                ),
                "character_style": project.get(
                    "character_style"
                ),
            },
            "checks": checks,
        }

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )

    except Exception as exc:
        return json.dumps(
            {
                "success": False,
                "error": f"视频规范检查失败：{exc}",
            },
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# 6. Agent 工具：检查视频是否符合项目规范
# ============================================================

@function_tool
def check_video_requirements(
    video_path: str,
    video_scope: str,
) -> str:
    """
    检查视频是否符合当前动画项目的已配置规范。

    Args:
        video_path:
            本地视频文件的完整路径。

        video_scope:
            视频类型：
            - episode：整集视频
            - shot：单个镜头
    """

    print(
        "\n【Agent 工具调用记录】"
        "check_video_requirements 已被调用"
    )

    return _check_video_requirements(
        video_path,
        video_scope,
    )


# ============================================================
# 7. 本地测试入口
# ============================================================

if __name__ == "__main__":

    test_video = (
        input("请输入 MP4 文件路径：")
        .strip()
        .strip('"')
    )

    print("\n请选择视频类型：")
    print("1. 整集视频")
    print("2. 单个镜头")

    scope_choice = input(
        "请输入 1 或 2："
    ).strip()

    if scope_choice == "1":
        video_scope = "episode"

    elif scope_choice == "2":
        video_scope = "shot"

    else:
        print("输入无效。")
        raise SystemExit(1)

    print("\n【视频规范检查结果】")

    print(
        _check_video_requirements(
            test_video,
            video_scope,
        )
    )