import json
import re
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

def _parse_silencedetect_output(
    ffmpeg_output: str,
    duration_seconds: float,
) -> list:
    """
    解析 FFmpeg silencedetect 的 stderr 输出。

    纯函数：不调用 ffmpeg，不访问文件，不访问网络。

    Args:
        ffmpeg_output:
            FFmpeg 在 stderr 中输出的文本。
        duration_seconds:
            媒体总时长，用于处理“视频结束时仍处于静音”的边界情况。

    Returns:
        静音区间列表，每项为：
        {
            "start_seconds": float,
            "end_seconds": float,
            "duration_seconds": float,
        }
    """

    silence_start_pattern = re.compile(
        r"silence_start:\s*([0-9.]+)"
    )
    silence_end_pattern = re.compile(
        r"silence_end:\s*([0-9.]+)"
        r"\s*\|\s*silence_duration:\s*([0-9.]+)"
    )

    silence_intervals = []
    current_silence_start = None

    for line in ffmpeg_output.splitlines():
        start_match = silence_start_pattern.search(line)

        if start_match:
            current_silence_start = float(start_match.group(1))
            continue

        end_match = silence_end_pattern.search(line)

        if end_match and current_silence_start is not None:
            silence_end = float(end_match.group(1))
            silence_duration = float(end_match.group(2))

            silence_intervals.append(
                {
                    "start_seconds": current_silence_start,
                    "end_seconds": silence_end,
                    "duration_seconds": silence_duration,
                }
            )

            current_silence_start = None

    # 视频结束时仍处于静音状态
    if current_silence_start is not None:
        silence_end = duration_seconds
        silence_duration = max(
            0.0,
            silence_end - current_silence_start,
        )

        silence_intervals.append(
            {
                "start_seconds": current_silence_start,
                "end_seconds": silence_end,
                "duration_seconds": silence_duration,
            }
        )

    return silence_intervals


def _analyze_audio_activity(video_path: str) -> str:
    """
    使用 FFmpeg silencedetect 分析视频中的音频活动/静音结构。

    注意：
    - 本函数只分析音频活动情况。
    - 不判断音频是否为对白。
    - 不判断音频是否为背景音乐。
    - 不判断音频内容类型。
    """

    ffmpeg_path = shutil.which("ffmpeg")

    if not ffmpeg_path:
        return json.dumps(
            {
                "success": False,
                "error": "未找到 ffmpeg，请确认 FFmpeg 已安装并已加入 PATH。",
            },
            ensure_ascii=False,
        )

    path = Path(video_path)

    if not path.exists():
        return json.dumps(
            {
                "success": False,
                "error": f"视频文件不存在：{video_path}",
            },
            ensure_ascii=False,
        )

    if not path.is_file():
        return json.dumps(
            {
                "success": False,
                "error": f"指定路径不是文件：{video_path}",
            },
            ensure_ascii=False,
        )

    # ----------------------------------------------------
    # 1. 先通过 ffprobe 获取媒体总时长
    # ----------------------------------------------------
    try:
        probe_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "success": False,
                "error": "ffprobe 获取视频时长超时。",
            },
            ensure_ascii=False,
        )
    except OSError as exc:
        return json.dumps(
            {
                "success": False,
                "error": f"启动 ffprobe 失败：{exc}",
            },
            ensure_ascii=False,
        )

    if probe_result.returncode != 0:
        return json.dumps(
            {
                "success": False,
                "error": (
                    "ffprobe 无法读取视频时长。"
                    f" stderr: {probe_result.stderr.strip()}"
                ),
            },
            ensure_ascii=False,
        )

    try:
        duration_seconds = float(probe_result.stdout.strip())
    except ValueError:
        return json.dumps(
            {
                "success": False,
                "error": (
                    "ffprobe 返回的时长无法解析："
                    f"{probe_result.stdout.strip()}"
                ),
            },
            ensure_ascii=False,
        )

    # ----------------------------------------------------
    # 2. 使用 FFmpeg silencedetect 分析静音区间
    # ----------------------------------------------------
    try:
        ffmpeg_result = subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-i",
                str(path),
                "-af",
                "silencedetect=noise=-35dB:d=0.3",
                "-f",
                "null",
                "NUL",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "success": False,
                "error": "FFmpeg 音频分析超时。",
            },
            ensure_ascii=False,
        )
    except OSError as exc:
        return json.dumps(
            {
                "success": False,
                "error": f"启动 FFmpeg 失败：{exc}",
            },
            ensure_ascii=False,
        )

    # silencedetect 的分析结果输出在 stderr。
    ffmpeg_output = ffmpeg_result.stderr

    if ffmpeg_result.returncode != 0:
        return json.dumps(
            {
                "success": False,
                "error": (
                    "FFmpeg 音频分析失败。"
                    f" stderr: {ffmpeg_output.strip()}"
                ),
            },
            ensure_ascii=False,
        )

    # ----------------------------------------------------
    # 3. 解析 silence_start / silence_end
    # ----------------------------------------------------
    silence_intervals = _parse_silencedetect_output(
        ffmpeg_output=ffmpeg_output,
        duration_seconds=duration_seconds,
    )

    # ----------------------------------------------------
    # 4. 计算音频活动情况
    # ----------------------------------------------------
    silence_duration_seconds = sum(
        item["duration_seconds"]
        for item in silence_intervals
    )

    silence_duration_seconds = min(
        silence_duration_seconds,
        duration_seconds,
    )

    active_duration_seconds = max(
        0.0,
        duration_seconds - silence_duration_seconds,
    )

    if duration_seconds > 0:
        activity_ratio = (
            active_duration_seconds / duration_seconds
        )
    else:
        activity_ratio = 0.0

    return json.dumps(
        {
            "success": True,
            "file_name": path.name,
            "file_path": str(path),
            "duration_seconds": round(
                duration_seconds,
                3,
            ),
            "silence_count": len(silence_intervals),
            "silence_duration_seconds": round(
                silence_duration_seconds,
                3,
            ),
            "active_duration_seconds": round(
                active_duration_seconds,
                3,
            ),
            "activity_ratio": round(
                activity_ratio,
                4,
            ),
            "silence_intervals": silence_intervals,
            "analysis_method": {
                "tool": "ffmpeg",
                "filter": "silencedetect",
                "noise_threshold": "-35dB",
                "minimum_silence_duration_seconds": 0.3,
            },
            "limitations": [
                "无法判断音频是否为人物对白。",
                "无法判断音频是否为背景音乐。",
                "无法判断音频是否为对白与背景音乐的混合。",
                "activity_ratio 仅表示音频活动比例，不代表人声比例或 BGM 概率。",
            ],
        },
        ensure_ascii=False,
    )


def _build_video_issue_report(
    checks: dict,
    compliance_summary: dict,
    video_scope: str,
) -> dict:
    """
    根据已有的视频检测结果生成结构化问题报告。

    本函数只负责整理和解释检测结果，不执行媒体分析。
    """

    report_items = []
    passed_items = []
    not_applicable_items = []
    unclassified_items = []

    title_by_check = {
        "aspect_ratio": "画幅不符合项目要求",
        "duration": "视频时长需要处理或复核",
        "fps": "帧率标准尚未配置",
        "subtitle_stream": "独立字幕轨道需要检查",
        "background_music": "背景音乐尚未确认",
        "burned_in_subtitles": "画面内嵌字幕尚未确认",
        "dialogue_content": "人物对白需要检查",
        "audio_activity": "音频活动分析结果",
    }

    passed_title_by_check = {
        "aspect_ratio": "画幅检查通过",
        "duration": "时长检查通过",
        "fps": "帧率检查通过",
        "subtitle_stream": "独立字幕轨道检查通过",
        "background_music": "背景音乐规则检查通过",
        "burned_in_subtitles": "内嵌字幕规则检查通过",
        "dialogue_content": "对白内容检查通过",
        "audio_activity": "音频活动分析完成",
    }

    not_applicable_title_by_check = {
        "dialogue_content": "对白内容检查不适用",
    }
    # 为不同类型的问题提供明确的处理建议。
    recommendation_by_check = {
        "aspect_ratio": (
            "优先在生成阶段设置正确的画幅。"
            "如果调整现有视频，请在剪辑软件中设置为项目要求的画幅，"
            "重新检查构图，避免直接裁切造成主体出框。"
        ),
        "fps": (
            "根据实际制作要求，在 project.json 中配置目标帧率，"
            "并在后续检测逻辑中接入该配置后再判断是否合格。"
        ),
        "subtitle_stream": (
            "如果独立字幕轨道不被允许，"
            "请在剪辑或封装软件中移除该轨道，再重新导出视频。"
        ),
        "background_music": (
            "请人工试听视频音轨，确认其中是人物对白、背景音乐，"
            "还是两者混合。当前检测结果不足以判断是否存在背景音乐。"
        ),
        "burned_in_subtitles": (
            "请人工检查视频画面中的文字。"
            "如果存在不允许的内嵌字幕，应移除相关文字后重新导出。"
        ),
        "dialogue_content": (
            "请人工试听音轨，或在后续接入语音检测能力后再进行判断。"
        ),
        "audio_activity": (
            "该结果只反映音频活动与静音的分布，"
            "不能把音频活动比例当作人声比例或背景音乐概率。"
        ),
    }


    for check_name, detail in checks.items():
        status = detail.get("status")
        original_message = detail.get("message", "")

        # ------------------------------------------------
        # 1. 明确通过的项目
        # ------------------------------------------------
        if status == "pass":
            passed_items.append({
                "check": check_name,
                "status": status,
                "title": passed_title_by_check.get(
                    check_name,
                    f"{check_name} 检查通过",
                ),
                "reason": original_message,
                "original_message": original_message,
            })
            continue

        # ------------------------------------------------
        # 2. 整集时长恰好达到目标
        # 不属于普通 pass，单独记录原始状态。
        # ------------------------------------------------
        if status == "at_target":
            passed_items.append({
                "check": check_name,
                "status": status,
                "title": "整集时长达到目标",
                "reason": original_message,
                "original_message": original_message,
            })
            continue

        # ------------------------------------------------
        # 3. 不适用的项目
        # ------------------------------------------------
        if status == "not_applicable":
            not_applicable_items.append({
                "check": check_name,
                "status": status,
                "title": not_applicable_title_by_check.get(
                    check_name,
                    f"{check_name} 检查不适用",
                ),
                "reason": original_message,
                "original_message": original_message,
            })
            continue


        # 把原始检测状态映射成便于用户理解的级别。
        if status == "fail":
            severity = "error"

        elif status in {
            "not_checked",
            "not_configured",
            "below_target",
            "above_target",
        }:
            severity = "warning"

        elif status == "informational":
            severity = "info"

        else:
            # 保留未知状态，避免生成报告时静默丢失检查项。
            unclassified_items.append({
                "check": check_name,
                "status": status,
                "title": f"{check_name} 状态暂无法归类",
                "reason": original_message or "暂无详细说明。",
                "original_message": original_message,
            })
            continue

        title = title_by_check.get(
            check_name,
            f"{check_name} 检查结果",
        )

        reason = detail.get("message", "暂无详细说明。")

        recommendation = recommendation_by_check.get(
            check_name,
            "请根据检测结果和项目规范进一步检查。",
        )

        # ------------------------------------------------
        # 画幅问题：说明项目要求与实际分辨率。
        # ------------------------------------------------
        if check_name == "aspect_ratio":
            expected = detail.get("expected", "未配置")
            width = detail.get("width")
            height = detail.get("height")

            reason = (
                f"项目要求画幅为 {expected}，"
                f"当前视频分辨率为 {width}×{height}。"
            )

        # ------------------------------------------------
        # 时长问题：区分单镜头超限与整集时长偏差。
        # ------------------------------------------------
        elif check_name == "duration":

            actual = detail.get("actual_seconds")

            if video_scope == "shot" and status == "fail":
                maximum = detail.get("maximum_seconds")

                difference = max(
                    0.0,
                    float(detail.get("difference_seconds", 0)),
                )

                title = "单镜头时长超过限制"

                reason = (
                    f"当前镜头时长为 {actual} 秒，"
                    f"最大允许时长为 {maximum} 秒，"
                    f"超出 {difference:.3f} 秒。"
                )

                recommendation = (
                    f"将该镜头至少剪短 {difference:.3f} 秒，"
                    f"使最终时长不超过 {maximum} 秒。"
                    "建议留出少量余量，避免导出时长误差造成再次超限。"
                )

            elif video_scope == "episode":
                target = detail.get("target_seconds")

                title = "整集时长与目标存在偏差"

                reason = (
                    f"整集实际时长为 {actual} 秒，"
                    f"项目目标时长为 {target} 秒。"
                    f"{detail.get('message', '')}"
                )

                recommendation = (
                    "请根据整集节奏和制作目标复核时长。"
                    "当前配置没有规定允许误差，因此该偏差需要复核，"
                    "不能仅凭偏差直接判定违规。"
                )

        # ------------------------------------------------
        # 未配置检测标准：记录实际值，但不判定合格性。
        # ------------------------------------------------
        elif check_name == "fps":
            actual_fps = detail.get("actual")

            reason = (
                f"当前视频帧率为 {actual_fps} fps，"
                "但项目配置中没有目标帧率。"
            )

        # 每条报告保留原始状态、原因与可执行建议。
        report_items.append({
            "check": check_name,
            "severity": severity,
            "status": status,
            "title": title,
            "reason": reason,
            "recommendation": recommendation,
            "original_message": detail.get("message", ""),
        })

    # ----------------------------------------------------
    # 汇总各级别的问题数量。
    # ----------------------------------------------------


    # ----------------------------------------------------
    # 汇总报告中的各类项目数量
    # ----------------------------------------------------

    error_count = sum(
        1 for item in report_items
        if item["severity"] == "error"
    )

    warning_count = sum(
        1 for item in report_items
        if item["severity"] == "warning"
    )

    info_count = sum(
        1 for item in report_items
        if item["severity"] == "info"
    )

    pass_count = sum(
        1 for item in passed_items
        if item["status"] == "pass"
    )

    target_met_count = sum(
        1 for item in passed_items
        if item["status"] == "at_target"
    )

    not_applicable_count = len(not_applicable_items)
    unclassified_count = len(unclassified_items)

    if error_count:
        headline = (
            f"发现 {error_count} 项确定问题，"
            f"{warning_count} 项需要复核。"
        )

    elif warning_count:
        headline = (
            "未发现确定违规项，"
            f"但有 {warning_count} 项需要复核。"
        )

    elif unclassified_count:
        headline = (
            "当前没有发现确定违规项，"
            f"但有 {unclassified_count} 项检查状态无法归类，"
            "需要进一步核实。"
        )

    else:
        headline = "未发现需要处理的违规项。"

    if info_count:
        headline += f"另有 {info_count} 项参考信息。"

    if pass_count or target_met_count:
        headline += (
            f"已通过 {pass_count} 项，"
            f"达到时长目标 {target_met_count} 项。"
        )

    if not_applicable_count:
        headline += f"另有 {not_applicable_count} 项不适用。"

    # 保留旧的 total_items 语义，同时增加总检查项数量。
    return {
        "overall_status": compliance_summary.get(
            "overall_status",
            "needs_review",
        ),
        "headline": headline,
        "counts": {
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "pass_count": pass_count,
            "target_met_count": target_met_count,
            "not_applicable_count": not_applicable_count,
            "unclassified_count": unclassified_count,
            "total_items": len(report_items),
            "total_check_count": len(checks),
        },
        "items": report_items,
        "passed_items": passed_items,
        "not_applicable_items": not_applicable_items,
        "unclassified_items": unclassified_items,
    }

def _build_compliance_summary(checks: dict) -> dict:
    """
    根据 checks 汇总整体合规状态。

    纯函数：不访问文件，不访问网络，不调用任何媒体工具。

    Args:
        checks:
            检查项字典，每项至少包含 "status" 字段。

    Returns:
        {
            "overall_status": "fail" | "needs_review" | "pass",
            "status_counts": {...},
            "failures": [...],
            "needs_review": [...],
        }
    """

    status_counts = {
        "pass": 0,
        "fail": 0,
        "not_checked": 0,
        "not_configured": 0,
        "not_applicable": 0,
        "informational": 0,
    }

    failures = []
    review_items = []

    # 整集时长目前只有目标值，没有允许误差。
    # 因此低于或高于目标时，只能要求复核，不能直接判为违规。
    informational_statuses = {
        "at_target",
        "below_target",
        "above_target",
    }

    for check_name, check_detail in checks.items():

        status = check_detail.get("status")

        if status in status_counts:
            status_counts[status] += 1

        elif status in informational_statuses:
            status_counts["informational"] += 1

        # 已经发现明确不合格的项目
        if status == "fail":
            failures.append({
                "check": check_name,
                "message": check_detail.get("message", ""),
            })

        # 无法检测或缺少检查标准的项目
        elif status in {
            "not_checked",
            "not_configured",
        }:
            review_items.append({
                "check": check_name,
                "status": status,
                "message": check_detail.get("message", ""),
            })

        # 整集时长偏离目标，但尚无允许误差标准
        elif status in {
            "below_target",
            "above_target",
        }:
            review_items.append({
                "check": check_name,
                "status": status,
                "message": check_detail.get("message", ""),
            })

    if failures:
        overall_status = "fail"

    elif review_items:
        overall_status = "needs_review"

    else:
        overall_status = "pass"

    return {
        "overall_status": overall_status,
        "status_counts": status_counts,
        "failures": failures,
        "needs_review": review_items,
    }

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
        # 9. 根据项目配置检查音频与字幕规范
        # ----------------------------------------------------

        # 读取音频和字幕规范。
        # 这样以后修改 project.json，就可以调整检查标准。
        audio_requirements = project.get(
            "audio_requirements", {}
        )

        subtitle_requirements = project.get(
            "subtitle_requirements", {}
        )

        # 避免配置结构异常时，调用 get() 导致检查中断
        if not isinstance(audio_requirements, dict):
            audio_requirements = {}

        if not isinstance(subtitle_requirements, dict):
            subtitle_requirements = {}

        background_music_allowed = (
            audio_requirements.get(
                "background_music_allowed"
            )
        )

        dialogue_allowed = (
            audio_requirements.get(
                "dialogue_allowed"
            )
        )

        subtitle_stream_allowed = (
            subtitle_requirements.get(
                "subtitle_stream_allowed"
            )
        )

        burned_in_subtitles_allowed = (
            subtitle_requirements.get(
                "burned_in_subtitles_allowed"
            )
        )

        # 获取之前已经由 ffprobe 统计的媒体流信息
        stream_summary = video_info.get(
            "stream_summary", {}
        )

        audio_stream_count = stream_summary.get(
            "audio_stream_count", 0
        )

        subtitle_stream_count = stream_summary.get(
            "subtitle_stream_count", 0
        )

        has_audio = stream_summary.get(
            "has_audio", audio_stream_count > 0
        )

        has_subtitle_stream = stream_summary.get(
            "has_subtitle_stream",
            subtitle_stream_count > 0,
        )

        # ----------------------------------------------------
        # 9.0 音频活动分析
        # ----------------------------------------------------

        audio_activity_raw = _analyze_audio_activity(
            video_path
        )

        try:
            audio_activity = json.loads(
                audio_activity_raw
            )
        except json.JSONDecodeError:
            audio_activity = {
                "success": False,
                "error": (
                    "音频活动分析返回的数据无法解析。"
                ),
            }

        if audio_activity.get("success"):
            audio_activity_status = "informational"

            audio_activity_message = (
                f"检测到视频音频活动比例为 "
                f"{audio_activity.get('activity_ratio', 0):.2%}，"
                f"静音区间 {audio_activity.get('silence_count', 0)} 个，"
                f"有声音时长 "
                f"{audio_activity.get('active_duration_seconds', 0)} 秒。"
                "该结果仅用于描述音频活动情况，"
                "不能用于判断是否存在 BGM 或人物对白。"
            )
        else:
            audio_activity_status = "not_checked"

            audio_activity_message = (
                "音频活动分析未能完成："
                f"{audio_activity.get('error', '未知错误')}"
            )

        checks["audio_activity"] = {
            "status": audio_activity_status,
            "duration_seconds": audio_activity.get(
                "duration_seconds"
            ),
            "silence_count": audio_activity.get(
                "silence_count"
            ),
            "silence_duration_seconds": audio_activity.get(
                "silence_duration_seconds"
            ),
            "active_duration_seconds": audio_activity.get(
                "active_duration_seconds"
            ),
            "activity_ratio": audio_activity.get(
                "activity_ratio"
            ),
            "analysis_method": audio_activity.get(
                "analysis_method"
            ),
            "message": audio_activity_message,
        }

        # ----------------------------------------------------
        # 9.1 检查独立字幕轨道
        # ----------------------------------------------------

        if subtitle_stream_allowed is False:

            if has_subtitle_stream:
                subtitle_status = "fail"

                subtitle_message = (
                    f"项目不允许独立字幕轨道，"
                    f"但视频检测到了 "
                    f"{subtitle_stream_count} 条字幕轨道。"
                )

            else:
                subtitle_status = "pass"

                subtitle_message = (
                    "项目不允许独立字幕轨道，"
                    "当前视频没有检测到独立字幕轨道。"
                )

        elif subtitle_stream_allowed is True:
            subtitle_status = "pass"

            subtitle_message = (
                "项目允许独立字幕轨道，"
                "本项不会因字幕轨道存在而判为不合格。"
            )

        else:
            subtitle_status = "not_configured"

            subtitle_message = (
                "项目没有配置独立字幕轨道的允许规则，"
                "因此不进行合格性判断。"
            )

        checks["subtitle_stream"] = {
            "status": subtitle_status,
            "allowed": subtitle_stream_allowed,
            "actual_count": subtitle_stream_count,
            "actual_present": has_subtitle_stream,
            "message": subtitle_message,
        }

        # ----------------------------------------------------
        # 9.2 检查背景音乐规范
        # ----------------------------------------------------

        if background_music_allowed is True:

            background_music_status = "pass"

            background_music_message = (
                "项目允许背景音乐，"
                "本项不会因背景音乐存在而判为不合格。"
            )

        elif background_music_allowed is False:

            if not has_audio:
                # 没有音频流，就没有通过音频流封装的 BGM
                background_music_status = "pass"

                background_music_message = (
                    "视频没有检测到音频流，"
                    "因此没有通过音频流封装的背景音乐。"
                )

            else:
                # 有音频不等于一定有 BGM，
                # 也可能只有人物对白，因此不能直接判 fail。
                background_music_status = "not_checked"

                background_music_message = (
                    f"项目不允许背景音乐，"
                    f"但当前检测到 {audio_stream_count} 条音频流。"
                    "ffprobe 只能读取媒体流信息，"
                    "不能判断音频具体是对白、背景音乐，"
                    "还是两者混合。需要进一步分析音频内容。"
                )

        else:
            background_music_status = "not_configured"

            background_music_message = (
                "项目没有配置背景音乐的允许规则，"
                "因此不进行合格性判断。"
            )

        checks["background_music"] = {
            "status": background_music_status,
            "allowed": background_music_allowed,
            "audio_stream_count": audio_stream_count,
            "has_audio": has_audio,
            "message": background_music_message,
        }

        # ----------------------------------------------------
        # 9.3 检查画面内嵌字幕规范
        # ----------------------------------------------------

        if burned_in_subtitles_allowed is True:

            burned_subtitle_status = "pass"

            burned_subtitle_message = (
                "项目允许画面内嵌字幕。"
                "当前版本不检查画面内是否实际存在字幕。"
            )

        elif burned_in_subtitles_allowed is False:

            burned_subtitle_status = "not_checked"

            burned_subtitle_message = (
                "项目不允许画面内嵌字幕，"
                "但当前版本还不能识别画面中的文字。"
                "没有独立字幕轨道不代表没有内嵌字幕，"
                "需要后续增加画面文字检测能力。"
            )

        else:
            burned_subtitle_status = "not_configured"

            burned_subtitle_message = (
                "项目没有配置画面内嵌字幕的允许规则，"
                "因此不进行合格性判断。"
            )

        checks["burned_in_subtitles"] = {
            "status": burned_subtitle_status,
            "allowed": burned_in_subtitles_allowed,
            "message": burned_subtitle_message,
        }

        # ----------------------------------------------------
        # 9.4 记录人物对白规范
        # ----------------------------------------------------

        if dialogue_allowed is True:
            dialogue_status = "not_applicable"
            dialogue_message = (
                "项目允许人物对白，且没有规定必须出现对白，"
                "因此不需要判断视频中是否实际包含人声。"
            )

        elif dialogue_allowed is False:
            dialogue_status = "not_checked"
            dialogue_message = (
                "项目不允许人物对白，但当前版本尚不能识别"
                "音轨中的人声，需要后续增加语音检测能力。"
            )

        else:
            dialogue_status = "not_configured"
            dialogue_message = (
                "项目没有配置人物对白规则，"
                "因此不进行合格性判断。"
            )

        checks["dialogue_content"] = {
            "status": dialogue_status,
            "allowed": dialogue_allowed,
            "message": dialogue_message,
        }

        # ----------------------------------------------------
        # 10. 汇总所有检查项的合规状态
        # ----------------------------------------------------

        compliance_summary = _build_compliance_summary(checks)

        # 根据已有的检测结果生成结构化问题报告。
        issue_report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope=video_scope,
        )

        # ----------------------------------------------------
        # 9. 整理最终检查结果
        # ----------------------------------------------------

        
        result = {
            "success": True,
            "video_scope": video_scope,
            "video_info": video_info,
            "compliance_summary": compliance_summary,
            "issue_report": issue_report,
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
                "audio_requirements": {
                    "background_music_allowed": (
                        background_music_allowed
                    ),
                    "dialogue_allowed": dialogue_allowed,
                },
                "subtitle_requirements": {
                    "subtitle_stream_allowed": (
                        subtitle_stream_allowed
                    ),
                    "burned_in_subtitles_allowed": (
                        burned_in_subtitles_allowed
                    ),
                },
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