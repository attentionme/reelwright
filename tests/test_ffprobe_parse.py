"""
最小回归测试：验证 _normalize_ffprobe_streams 的字段与边界处理。

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

from tools import _normalize_ffprobe_streams


class TestNormalizeFfprobeStreams(unittest.TestCase):
    """验证媒体流归一化的字段与边界处理。"""

    def test_empty_list(self):
        result = _normalize_ffprobe_streams([])
        self.assertEqual(result, [])

    def test_typical_video_and_audio(self):
        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 896,
                "r_frame_rate": "24/1",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertEqual(len(result), 2)

        video = result[0]
        self.assertEqual(video["index"], 0)
        self.assertEqual(video["codec_type"], "video")
        self.assertEqual(video["codec_name"], "h264")
        self.assertEqual(video["width"], 1600)
        self.assertEqual(video["height"], 896)
        self.assertAlmostEqual(video["fps"], 24.0)

        audio = result[1]
        self.assertEqual(audio["index"], 1)
        self.assertEqual(audio["codec_type"], "audio")
        self.assertEqual(audio["codec_name"], "aac")
        self.assertEqual(audio["sample_rate"], 48000)
        self.assertEqual(audio["channels"], 2)

    def test_no_audio(self):
        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 720,
                "height": 1280,
                "r_frame_rate": "30/1",
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["codec_type"], "video")
        self.assertAlmostEqual(result[0]["fps"], 30.0)

    def test_with_subtitle_stream(self):
        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 896,
                "r_frame_rate": "24/1",
            },
            {
                "index": 1,
                "codec_type": "subtitle",
                "codec_name": "mov_text",
                "tags": {"language": "chi", "title": "中文"},
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertEqual(len(result), 2)

        subtitle = result[1]
        self.assertEqual(subtitle["codec_type"], "subtitle")
        self.assertEqual(subtitle["codec_name"], "mov_text")
        self.assertEqual(subtitle["language"], "chi")
        self.assertEqual(subtitle["title"], "中文")

    def test_with_other_stream(self):
        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 896,
                "r_frame_rate": "24/1",
            },
            {
                "index": 1,
                "codec_type": "data",
                "codec_name": "bin_data",
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["codec_type"], "data")
        self.assertEqual(result[1]["codec_name"], "bin_data")

    def test_fps_zero_division(self):
        """r_frame_rate = '0/0' 时应兜底为 None，而不是抛异常。"""

        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 896,
                "r_frame_rate": "0/0",
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertIsNone(result[0]["fps"])

    def test_fps_missing(self):
        """没有 r_frame_rate 字段时，fps 应为 None。"""

        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 896,
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertIsNone(result[0]["fps"])

    def test_fps_invalid_string(self):
        """r_frame_rate 为非数字字符串时，fps 应为 None。"""

        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1600,
                "height": 896,
                "r_frame_rate": "not-a-fraction",
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertIsNone(result[0]["fps"])

    def test_video_missing_width_height(self):
        """视频流缺 width/height 时，不应注入 width/height 字段。"""

        raw = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "r_frame_rate": "24/1",
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertNotIn("width", result[0])
        self.assertNotIn("height", result[0])

    def test_sample_rate_non_int_string_falls_back(self):
        """sample_rate 不是数字时，应保留原始字符串，不抛异常。"""

        raw = [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "not-a-number",
                "channels": 2,
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertEqual(result[0]["sample_rate"], "not-a-number")
        self.assertEqual(result[0]["channels"], 2)

    def test_unknown_codec_type_preserved(self):
        """codec_type 缺失时，默认使用 'unknown'。"""

        raw = [
            {
                "index": 0,
                "codec_name": "some_codec",
            },
        ]

        result = _normalize_ffprobe_streams(raw)

        self.assertEqual(result[0]["codec_type"], "unknown")


if __name__ == "__main__":
    unittest.main()