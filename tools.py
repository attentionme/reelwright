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

    返回 JSON 字符串，包括：
    - file_name：文件名
    - file_path：完整路径
    - duration_seconds：视频时长
    - width / height：视频分辨率
    - fps：视频帧率
    - stream_summary：媒体流统计摘要
    - streams：各媒体流的详细信息
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
        video_file = Path(video_path).expanduser()

        if not video_file.exists():
            return (
                f"读取视频失败：文件不存在：{video_file}"
            )

        if not video_file.is_file():
            return (
                f"读取视频失败：路径不是文件：{video_file}"
            )

        # 3. 读取全部媒体流，而不是只读取第一条视频流
        #
        # video: 视频流
        # audio: 音频流
        # subtitle: 独立字幕流
        #
        # 同时读取视频时长、编码格式及相关媒体属性。
        command = [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            (
                "stream=index,codec_type,codec_name,"
                "width,height,r_frame_rate,"
                "sample_rate,channels:"
                "stream_tags=language,title:"
                "format=duration"
            ),
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

        raw_streams = data.get("streams", [])
        format_data = data.get("format", {})

        # 没有媒体流时，直接报告错误
        if not raw_streams:
            return "读取视频失败：文件中没有找到媒体流。"

        # 获取容器报告的视频时长
        raw_duration = format_data.get("duration")

        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            return (
                "读取视频失败：ffprobe 没有返回"
                "有效的视频时长。"
            )

        # 6. 统一整理全部媒体流的数据
        normalized_streams = []

        for stream in raw_streams:
            codec_type = stream.get(
                "codec_type",
                "unknown",
            )

            stream_info = {
                "index": stream.get("index"),
                "codec_type": codec_type,
                "codec_name": stream.get("codec_name"),
            }

            # 视频流：记录分辨率与帧率
            if codec_type == "video":

                if stream.get("width") is not None:
                    stream_info["width"] = int(
                        stream["width"]
                    )

                if stream.get("height") is not None:
                    stream_info["height"] = int(
                        stream["height"]
                    )

                raw_fps = stream.get("r_frame_rate")

                try:
                    fps = (
                        float(Fraction(raw_fps))
                        if raw_fps
                        else None
                    )
                except (
                    ValueError,
                    ZeroDivisionError,
                    TypeError,
                ):
                    fps = None

                stream_info["fps"] = (
                    round(fps, 3)
                    if fps is not None
                    else None
                )

            # 音频流：记录采样率与声道数
            elif codec_type == "audio":

                if stream.get("sample_rate") is not None:
                    try:
                        stream_info["sample_rate"] = int(
                            stream["sample_rate"]
                        )
                    except (TypeError, ValueError):
                        stream_info["sample_rate"] = (
                            stream["sample_rate"]
                        )

                if stream.get("channels") is not None:
                    stream_info["channels"] = int(
                        stream["channels"]
                    )

            # 字幕流不需要额外解析画面内容。
            # 这里只确认它是否作为独立媒体流存在。

            # 保留媒体流附带的语言与标题信息
            tags = stream.get("tags", {})

            if tags.get("language"):
                stream_info["language"] = tags["language"]

            if tags.get("title"):
                stream_info["title"] = tags["title"]

            normalized_streams.append(stream_info)

        # 7. 找到第一条视频流，保持原有视频信息接口兼容
        video_streams = [
            stream
            for stream in normalized_streams
            if stream["codec_type"] == "video"
        ]

        if not video_streams:
            return "读取视频失败：没有找到视频流。"

        video_stream = video_streams[0]

        if (
            video_stream.get("width") is None
            or video_stream.get("height") is None
        ):
            return (
                "读取视频失败：无法读取有效的视频"
                "宽度和高度。"
            )

        # 8. 统计各类媒体流数量
        video_count = sum(
            1
            for stream in normalized_streams
            if stream["codec_type"] == "video"
        )

        audio_count = sum(
            1
            for stream in normalized_streams
            if stream["codec_type"] == "audio"
        )

        subtitle_count = sum(
            1
            for stream in normalized_streams
            if stream["codec_type"] == "subtitle"
        )

        other_count = sum(
            1
            for stream in normalized_streams
            if stream["codec_type"]
            not in {"video", "audio", "subtitle"}
        )

        stream_summary = {
            "video_stream_count": video_count,
            "audio_stream_count": audio_count,
            "subtitle_stream_count": subtitle_count,
            "other_stream_count": other_count,
            "has_audio": audio_count > 0,
            "has_subtitle_stream": subtitle_count > 0,
        }

        # 9. 整理最终结果
        #
        # 保留原来的 file_name、file_path、duration_seconds、
        # width、height、fps 字段。
        # 新增 stream_summary 与 streams。
        video_info = {
            "file_name": video_file.name,
            "file_path": str(video_file.resolve()),
            "duration_seconds": round(duration, 3),
            "width": video_stream["width"],
            "height": video_stream["height"],
            "fps": video_stream["fps"],
            "stream_summary": stream_summary,
            "streams": normalized_streams,
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