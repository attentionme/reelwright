"""
集成测试：用真实 ffmpeg 生成小视频，跑完整的 _check_video_requirements。

设计要点：
- fixture 在 setUpClass 中动态生成，不提交二进制到 Git
- 若 ffmpeg / ffprobe 不在 PATH，整个测试类自动跳过
- 断言的是 issue_report 的结构与 severity，不是具体数值
- 依赖当前 project.json 的配置（如 target_fps = 24）
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tools


def _ffmpeg_available() -> bool:
    return (
        shutil.which("ffmpeg") is not None
        and shutil.which("ffprobe") is not None
    )


def _make_video(
    output_path: Path,
    width: int,
    height: int,
    duration: int,
) -> bool:
    """
    用 ffmpeg lavfi 生成一个黑色 + 静音的小视频。

    编码 h264 + aac，帧率 24，符合 project.json 的常见配置。
    """

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r=24:d={duration}",
        "-f", "lavfi",
        "-i", "anullsrc=r=48000:cl=stereo",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-t", str(duration),
        "-shortest",
        "-y",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    return result.returncode == 0 and output_path.exists()


@unittest.skipUnless(
    _ffmpeg_available(),
    "ffmpeg / ffprobe 不在 PATH 中，跳过集成测试",
)
class TestIntegrationShot(unittest.TestCase):
    """
    端到端测试：从 ffprobe 到 issue_report 的完整链路。

    这些断言依赖当前 project.json 的配置：
      aspect_ratio = 9:16
      max_shot_duration_seconds = 12
      target_fps = 24
      video_codec = h264
      audio_codec = aac
    """

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmpdir.name)

        cls.shot_ok = tmp / "shot_ok.mp4"
        cls.shot_bad_ratio = tmp / "shot_bad_ratio.mp4"
        cls.shot_bad_duration = tmp / "shot_bad_duration.mp4"

        if not _make_video(cls.shot_ok, 540, 960, 8):
            raise unittest.SkipTest("无法生成 shot_ok.mp4")

        if not _make_video(cls.shot_bad_ratio, 960, 540, 8):
            raise unittest.SkipTest("无法生成 shot_bad_ratio.mp4")

        if not _make_video(cls.shot_bad_duration, 540, 960, 13):
            raise unittest.SkipTest("无法生成 shot_bad_duration.mp4")

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    # --------------------------------------------------------
    # 辅助
    # --------------------------------------------------------

    def _run(self, path: Path) -> dict:
        raw = tools._check_video_requirements(str(path), "shot")
        return json.loads(raw)

    def _find_item(self, result: dict, check_name: str):
        """在 issue_report.items 里查找指定 check 的条目。"""
        for item in result["issue_report"]["items"]:
            if item["check"] == check_name:
                return item
        return None

    def _passed_names(self, result: dict) -> set:
        """返回 issue_report.passed_items 里所有 check 名。"""
        return {
            item["check"]
            for item in result["issue_report"]["passed_items"]
        }

    # --------------------------------------------------------
    # 合规镜头：540×960、8 秒
    # --------------------------------------------------------

    def test_ok_shot_aspect_and_duration_pass(self):
        result = self._run(self.shot_ok)

        self.assertTrue(result["success"])

        passed = self._passed_names(result)

        self.assertIn("aspect_ratio", passed)
        self.assertIn("duration", passed)

    def test_ok_shot_no_error(self):
        result = self._run(self.shot_ok)

        self.assertEqual(
            result["issue_report"]["counts"]["error_count"],
            0,
        )

    def test_ok_shot_codec_and_fps_pass(self):
        """合成视频是 h264 + aac + 24fps，应该全部 pass。"""

        result = self._run(self.shot_ok)

        passed = self._passed_names(result)

        self.assertIn("fps", passed)
        self.assertIn("video_codec", passed)
        self.assertIn("audio_codec", passed)

    # --------------------------------------------------------
    # 横屏镜头：960×540、8 秒
    # --------------------------------------------------------

    def test_bad_ratio_shot_aspect_is_error(self):
        result = self._run(self.shot_bad_ratio)

        self.assertTrue(result["success"])

        item = self._find_item(result, "aspect_ratio")

        self.assertIsNotNone(item, "未找到 aspect_ratio 的问题项")
        self.assertEqual(item["severity"], "error")

    def test_bad_ratio_shot_overall_is_fail(self):
        result = self._run(self.shot_bad_ratio)

        self.assertEqual(
            result["compliance_summary"]["overall_status"],
            "fail",
        )

    # --------------------------------------------------------
    # 超时镜头：540×960、13 秒
    # --------------------------------------------------------

    def test_bad_duration_shot_duration_is_error(self):
        result = self._run(self.shot_bad_duration)

        self.assertTrue(result["success"])

        item = self._find_item(result, "duration")

        self.assertIsNotNone(item, "未找到 duration 的问题项")
        self.assertEqual(item["severity"], "error")
        self.assertIn("12", item["reason"])

    def test_bad_duration_shot_overall_is_fail(self):
        result = self._run(self.shot_bad_duration)

        self.assertEqual(
            result["compliance_summary"]["overall_status"],
            "fail",
        )

    def test_bad_duration_shot_aspect_still_pass(self):
        """时长超限不应影响画幅检查。"""

        result = self._run(self.shot_bad_duration)

        passed = self._passed_names(result)

        self.assertIn("aspect_ratio", passed)

@unittest.skipUnless(
    _ffmpeg_available(),
    "ffmpeg / ffprobe 不在 PATH 中，跳过集成测试",
)
class TestIntegrationDirectory(unittest.TestCase):
    """
    端到端测试：从 ffprobe 到目录级聚合的完整链路。

    使用与 TestIntegrationShot 相同的 _make_video 辅助函数。
    断言的是目录摘要的结构与关键字段，不硬编码具体秒数。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmpdir.name)

        cls.shot_a = tmp / "shot_01.mp4"
        cls.shot_b = tmp / "shot_02.mp4"

        if not _make_video(cls.shot_a, 540, 960, 8):
            raise unittest.SkipTest("无法生成 shot_01.mp4")

        if not _make_video(cls.shot_b, 540, 960, 8):
            raise unittest.SkipTest("无法生成 shot_02.mp4")

        cls.directory = str(tmp)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    # --------------------------------------------------------
    # 辅助
    # --------------------------------------------------------

    def _run_dir(self) -> dict:
        raw = tools._check_directory_requirements(self.directory)
        return json.loads(raw)

    # --------------------------------------------------------
    # 目录摘要
    # --------------------------------------------------------

    def test_directory_check_succeeds(self):
        result = self._run_dir()

        self.assertTrue(result["success"])
        self.assertEqual(result["failed_files"], [])

    def test_directory_file_count(self):
        result = self._run_dir()

        summary = result["directory_summary"]

        self.assertEqual(summary["file_count"], 2)

    def test_directory_total_duration(self):
        """两个 8 秒视频，总时长约 16 秒。"""

        result = self._run_dir()

        summary = result["directory_summary"]

        self.assertAlmostEqual(
            summary["total_duration_seconds"],
            16.0,
            delta=1.0,
        )

    def test_directory_below_target(self):
        """16 秒远低于 45 秒目标，且超出 2 秒容差。"""

        result = self._run_dir()

        summary = result["directory_summary"]

        self.assertEqual(summary["duration_status"], "below_target")
        self.assertLess(summary["duration_difference_seconds"], 0)

    def test_directory_consistency(self):
        """两个视频参数相同，一致性检查应全部通过。"""

        result = self._run_dir()

        summary = result["directory_summary"]

        self.assertTrue(summary["has_consistent_aspect_ratio"])
        self.assertTrue(summary["has_consistent_fps"])
        self.assertEqual(summary["distinct_video_codecs"], ["h264"])
        self.assertEqual(summary["distinct_audio_codecs"], ["aac"])

    def test_directory_files_sorted(self):
        """两个文件的 file_name 应按名字升序。"""

        result = self._run_dir()

        names = [
            f["file_name"]
            for f in result["directory_summary"]["files"]
        ]

        self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()