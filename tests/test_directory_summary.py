"""
最小回归测试：验证 _build_directory_summary 的聚合逻辑。

覆盖点：
- 空目录
- 单文件 / 多文件
- 总时长在容差内 / 外
- 画幅一致性
- 帧率一致性
- 从 streams 提取编码
- 缺少 streams 字段
- 按文件名排序
- duration 缺失 / 无效值
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import _build_directory_summary


def _make_file(
    name,
    duration,
    width=1600,
    height=896,
    fps=24.0,
    streams=None,
):
    info = {
        "file_name": name,
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": fps,
    }

    if streams is not None:
        info["streams"] = streams

    return info


class TestBuildDirectorySummary(unittest.TestCase):

    # --------------------------------------------------------
    # 空目录
    # --------------------------------------------------------

    def test_empty_directory(self):
        result = _build_directory_summary(
            file_infos=[],
            project_data={"target_duration_seconds": 45},
        )

        self.assertEqual(result["file_count"], 0)
        self.assertEqual(result["files"], [])
        self.assertEqual(result["duration_status"], "not_applicable")
        self.assertEqual(
            result["target_duration_seconds"], 45
        )

    # --------------------------------------------------------
    # 总时长 vs 目标
    # --------------------------------------------------------

    def test_single_file_at_target(self):
        result = _build_directory_summary(
            file_infos=[_make_file("a.mp4", 45.0)],
            project_data={
                "target_duration_seconds": 45,
                "target_duration_tolerance_seconds": 2,
            },
        )

        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["duration_status"], "at_target")
        self.assertEqual(
            result["total_duration_seconds"], 45.0
        )

    def test_multi_files_below_target(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("a.mp4", 10.0),
                _make_file("b.mp4", 12.0),
            ],
            project_data={
                "target_duration_seconds": 45,
                "target_duration_tolerance_seconds": 2,
            },
        )

        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["duration_status"], "below_target")
        self.assertAlmostEqual(
            result["total_duration_seconds"], 22.0
        )
        self.assertAlmostEqual(
            result["duration_difference_seconds"], -23.0
        )

    def test_multi_files_above_target(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("a.mp4", 30.0),
                _make_file("b.mp4", 25.0),
            ],
            project_data={
                "target_duration_seconds": 45,
                "target_duration_tolerance_seconds": 2,
            },
        )

        self.assertEqual(result["duration_status"], "above_target")
        self.assertAlmostEqual(
            result["total_duration_seconds"], 55.0
        )

    def test_within_tolerance_is_at_target(self):
        result = _build_directory_summary(
            file_infos=[_make_file("a.mp4", 43.5)],
            project_data={
                "target_duration_seconds": 45,
                "target_duration_tolerance_seconds": 2,
            },
        )

        self.assertEqual(result["duration_status"], "at_target")

    def test_no_tolerance_configured_requires_exact(self):
        result = _build_directory_summary(
            file_infos=[_make_file("a.mp4", 44.0)],
            project_data={"target_duration_seconds": 45},
        )

        self.assertEqual(result["duration_status"], "below_target")

    # --------------------------------------------------------
    # 一致性
    # --------------------------------------------------------

    def test_consistent_aspect_ratio_and_fps(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("a.mp4", 10.0),
                _make_file("b.mp4", 10.0),
            ],
            project_data={"target_duration_seconds": 45},
        )

        self.assertTrue(result["has_consistent_aspect_ratio"])
        self.assertTrue(result["has_consistent_fps"])
        self.assertEqual(
            result["distinct_aspect_ratios"], [[1600, 896]]
        )
        self.assertEqual(result["distinct_fps"], [24.0])

    def test_inconsistent_aspect_ratio(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("a.mp4", 10.0, 1600, 896),
                _make_file("b.mp4", 10.0, 1920, 1080),
            ],
            project_data={"target_duration_seconds": 45},
        )

        self.assertFalse(result["has_consistent_aspect_ratio"])
        self.assertEqual(len(result["distinct_aspect_ratios"]), 2)
        self.assertIn("画幅", result["message"])

    def test_inconsistent_fps(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("a.mp4", 10.0, fps=24.0),
                _make_file("b.mp4", 10.0, fps=30.0),
            ],
            project_data={"target_duration_seconds": 45},
        )

        self.assertFalse(result["has_consistent_fps"])
        self.assertEqual(result["distinct_fps"], [24.0, 30.0])
        self.assertIn("帧率", result["message"])

    # --------------------------------------------------------
    # 编码提取
    # --------------------------------------------------------

    def test_extract_codecs_from_streams(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file(
                    "a.mp4",
                    10.0,
                    streams=[
                        {"codec_type": "video", "codec_name": "h264"},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                ),
                _make_file(
                    "b.mp4",
                    10.0,
                    streams=[
                        {"codec_type": "video", "codec_name": "h264"},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                ),
            ],
            project_data={"target_duration_seconds": 45},
        )

        self.assertEqual(result["distinct_video_codecs"], ["h264"])
        self.assertEqual(result["distinct_audio_codecs"], ["aac"])

    def test_missing_streams_yields_empty_codec_lists(self):
        result = _build_directory_summary(
            file_infos=[_make_file("a.mp4", 10.0)],
            project_data={"target_duration_seconds": 45},
        )

        self.assertEqual(result["distinct_video_codecs"], [])
        self.assertEqual(result["distinct_audio_codecs"], [])

    def test_mixed_codecs_yields_multiple_entries(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file(
                    "a.mp4",
                    10.0,
                    streams=[
                        {"codec_type": "video", "codec_name": "h264"},
                    ],
                ),
                _make_file(
                    "b.mp4",
                    10.0,
                    streams=[
                        {"codec_type": "video", "codec_name": "hevc"},
                    ],
                ),
            ],
            project_data={"target_duration_seconds": 45},
        )

        self.assertEqual(
            result["distinct_video_codecs"], ["h264", "hevc"]
        )

    # --------------------------------------------------------
    # 排序与健壮性
    # --------------------------------------------------------

    def test_files_sorted_by_name(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("shot_03.mp4", 5.0),
                _make_file("shot_01.mp4", 5.0),
                _make_file("shot_02.mp4", 5.0),
            ],
            project_data={"target_duration_seconds": 45},
        )

        names = [f["file_name"] for f in result["files"]]

        self.assertEqual(
            names,
            ["shot_01.mp4", "shot_02.mp4", "shot_03.mp4"],
        )

    def test_invalid_duration_treated_as_zero(self):
        result = _build_directory_summary(
            file_infos=[
                _make_file("a.mp4", "not-a-number"),
                _make_file("b.mp4", 10.0),
            ],
            project_data={"target_duration_seconds": 45},
        )

        self.assertEqual(result["file_count"], 2)
        self.assertAlmostEqual(
            result["total_duration_seconds"], 10.0
        )


if __name__ == "__main__":
    unittest.main()