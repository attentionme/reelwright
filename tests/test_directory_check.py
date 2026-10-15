"""
最小回归测试：验证 _check_directory_requirements 的 IO 编排。

使用 unittest.mock 替换 _get_video_info 和 load_project_data，
不调用真实 ffprobe，不依赖外部文件。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tools


def _fake_video_info(file_name, duration=10.0):
    """构造一个 _get_video_info 成功时的 JSON 返回值。"""

    return json.dumps(
        {
            "file_name": file_name,
            "file_path": f"/fake/{file_name}",
            "duration_seconds": duration,
            "width": 1600,
            "height": 896,
            "fps": 24.0,
            "stream_summary": {
                "video_stream_count": 1,
                "audio_stream_count": 1,
                "subtitle_stream_count": 0,
                "other_stream_count": 0,
                "has_audio": True,
                "has_subtitle_stream": False,
            },
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
        ensure_ascii=False,
    )


FAKE_PROJECT = {
    "target_duration_seconds": 45,
    "target_duration_tolerance_seconds": 2,
}


class TestCheckDirectoryRequirements(unittest.TestCase):

    # --------------------------------------------------------
    # 路径校验
    # --------------------------------------------------------

    def test_directory_not_exists(self):
        raw = tools._check_directory_requirements(
            r"D:\AIProjects\agent-learnin\__not_exists__"
        )
        result = json.loads(raw)

        self.assertFalse(result["success"])
        self.assertIn("不存在", result["error"])

    def test_path_is_file_not_directory(self):
        with tempfile.NamedTemporaryFile(
            suffix=".mp4", delete=False
        ) as f:
            file_path = f.name

        try:
            raw = tools._check_directory_requirements(file_path)
            result = json.loads(raw)

            self.assertFalse(result["success"])
            self.assertIn("不是目录", result["error"])
        finally:
            Path(file_path).unlink(missing_ok=True)

    # --------------------------------------------------------
    # 空目录
    # --------------------------------------------------------

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertTrue(result["success"])
            self.assertEqual(
                result["directory_summary"]["file_count"], 0
            )
            self.assertEqual(result["failed_files"], [])

    # --------------------------------------------------------
    # 正常聚合
    # --------------------------------------------------------

    def test_two_valid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shot_01.mp4").write_bytes(b"")
            (Path(tmp) / "shot_02.mp4").write_bytes(b"")

            def fake_info(path):
                name = Path(path).name
                return _fake_video_info(name, duration=12.25)

            with patch.object(
                tools, "_get_video_info", side_effect=fake_info
            ), patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertTrue(result["success"])

            summary = result["directory_summary"]

            self.assertEqual(summary["file_count"], 2)
            self.assertAlmostEqual(
                summary["total_duration_seconds"], 24.5
            )
            self.assertEqual(
                summary["duration_status"], "below_target"
            )
            self.assertEqual(
                summary["distinct_video_codecs"], ["h264"]
            )
            self.assertEqual(
                summary["distinct_audio_codecs"], ["aac"]
            )
            self.assertEqual(result["failed_files"], [])

    # --------------------------------------------------------
    # 非 mp4 文件被忽略
    # --------------------------------------------------------

    def test_non_mp4_files_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shot_01.mp4").write_bytes(b"")
            (Path(tmp) / "readme.txt").write_text("hello")
            (Path(tmp) / "cover.png").write_bytes(b"")

            with patch.object(
                tools, "_get_video_info",
                return_value=_fake_video_info("shot_01.mp4"),
            ), patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertEqual(
                result["directory_summary"]["file_count"], 1
            )

    # --------------------------------------------------------
    # 大小写扩展名
    # --------------------------------------------------------

    def test_uppercase_extension_treated_as_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shot_01.MP4").write_bytes(b"")

            with patch.object(
                tools, "_get_video_info",
                return_value=_fake_video_info("shot_01.MP4"),
            ), patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertEqual(
                result["directory_summary"]["file_count"], 1
            )

    # --------------------------------------------------------
    # 单文件失败不中断
    # --------------------------------------------------------

    def test_one_file_fails_others_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shot_01.mp4").write_bytes(b"")
            (Path(tmp) / "shot_02.mp4").write_bytes(b"")

            def fake_info(path):
                name = Path(path).name
                if name == "shot_01.mp4":
                    return "读取视频失败：ffprobe 无法解析该视频。"
                return _fake_video_info(name)

            with patch.object(
                tools, "_get_video_info", side_effect=fake_info
            ), patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertTrue(result["success"])
            self.assertEqual(
                result["directory_summary"]["file_count"], 1
            )
            self.assertEqual(len(result["failed_files"]), 1)
            self.assertEqual(
                result["failed_files"][0]["file_name"],
                "shot_01.mp4",
            )

    # --------------------------------------------------------
    # 所有文件都失败
    # --------------------------------------------------------

    def test_all_files_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shot_01.mp4").write_bytes(b"")
            (Path(tmp) / "shot_02.mp4").write_bytes(b"")

            with patch.object(
                tools, "_get_video_info",
                return_value="读取视频失败：系统中找不到 ffprobe。",
            ), patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertTrue(result["success"])
            self.assertEqual(
                result["directory_summary"]["file_count"], 0
            )
            self.assertEqual(len(result["failed_files"]), 2)

    # --------------------------------------------------------
    # 输出稳定性：文件名排序
    # --------------------------------------------------------

    def test_files_processed_in_name_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shot_03.mp4").write_bytes(b"")
            (Path(tmp) / "shot_01.mp4").write_bytes(b"")
            (Path(tmp) / "shot_02.mp4").write_bytes(b"")

            def fake_info(path):
                return _fake_video_info(Path(path).name)

            with patch.object(
                tools, "_get_video_info", side_effect=fake_info
            ), patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            names = [
                f["file_name"]
                for f in result["directory_summary"]["files"]
            ]

            self.assertEqual(
                names,
                ["shot_01.mp4", "shot_02.mp4", "shot_03.mp4"],
            )

    # --------------------------------------------------------
    # 返回值包含 project_requirements
    # --------------------------------------------------------

    def test_project_requirements_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                tools, "load_project_data",
                return_value=FAKE_PROJECT,
            ):
                raw = tools._check_directory_requirements(tmp)
                result = json.loads(raw)

            self.assertIn("project_requirements", result)
            self.assertEqual(
                result["project_requirements"][
                    "target_duration_seconds"
                ],
                45,
            )
            self.assertEqual(
                result["project_requirements"][
                    "target_duration_tolerance_seconds"
                ],
                2,
            )


if __name__ == "__main__":
    unittest.main()