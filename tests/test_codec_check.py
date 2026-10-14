"""
最小回归测试：验证 _build_codec_check 的分支与字段。

原则：
- 不调用 ffprobe / ffmpeg
- 不访问文件
- 不访问网络
- 只测纯函数行为
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import _build_codec_check


class TestBuildCodecCheck(unittest.TestCase):

    # --------------------------------------------------------
    # not_configured
    # --------------------------------------------------------

    def test_target_not_configured_video(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec="h264",
            target_codec=None,
            stream_present=True,
        )

        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["actual"], "h264")
        self.assertIsNone(result["target"])

    def test_target_not_configured_audio(self):
        result = _build_codec_check(
            stream_type="audio",
            actual_codec="aac",
            target_codec=None,
            stream_present=True,
        )

        self.assertEqual(result["status"], "not_configured")

    # --------------------------------------------------------
    # pass / fail
    # --------------------------------------------------------

    def test_video_pass(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec="h264",
            target_codec="h264",
            stream_present=True,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["actual"], "h264")
        self.assertEqual(result["target"], "h264")
        self.assertIn("符合", result["message"])

    def test_video_fail(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec="hevc",
            target_codec="h264",
            stream_present=True,
        )

        self.assertEqual(result["status"], "fail")
        self.assertIn("不符合", result["message"])
        self.assertIn("hevc", result["message"])
        self.assertIn("h264", result["message"])

    def test_audio_pass(self):
        result = _build_codec_check(
            stream_type="audio",
            actual_codec="aac",
            target_codec="aac",
            stream_present=True,
        )

        self.assertEqual(result["status"], "pass")

    def test_audio_fail(self):
        result = _build_codec_check(
            stream_type="audio",
            actual_codec="mp3",
            target_codec="aac",
            stream_present=True,
        )

        self.assertEqual(result["status"], "fail")

    # --------------------------------------------------------
    # audio 流不存在 → not_applicable
    # --------------------------------------------------------

    def test_audio_no_stream_is_not_applicable(self):
        result = _build_codec_check(
            stream_type="audio",
            actual_codec=None,
            target_codec="aac",
            stream_present=False,
        )

        self.assertEqual(result["status"], "not_applicable")
        self.assertIn("没有音频流", result["message"])

    # --------------------------------------------------------
    # video 流不存在 → not_checked（防御性分支）
    # --------------------------------------------------------

    def test_video_no_stream_is_not_checked(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec=None,
            target_codec="h264",
            stream_present=False,
        )

        self.assertEqual(result["status"], "not_checked")

    # --------------------------------------------------------
    # 流存在但 codec_name 读不到 → not_checked
    # --------------------------------------------------------

    def test_video_codec_unreadable_is_not_checked(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec=None,
            target_codec="h264",
            stream_present=True,
        )

        self.assertEqual(result["status"], "not_checked")

    def test_audio_codec_unreadable_is_not_checked(self):
        result = _build_codec_check(
            stream_type="audio",
            actual_codec=None,
            target_codec="aac",
            stream_present=True,
        )

        self.assertEqual(result["status"], "not_checked")

    # --------------------------------------------------------
    # 字段完整性
    # --------------------------------------------------------

    def test_pass_required_fields(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec="h264",
            target_codec="h264",
            stream_present=True,
        )

        for key in ("status", "actual", "target", "message"):
            self.assertIn(key, result)

    def test_not_configured_required_fields(self):
        result = _build_codec_check(
            stream_type="video",
            actual_codec="h264",
            target_codec=None,
            stream_present=True,
        )

        for key in ("status", "actual", "target", "message"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()