"""
最小回归测试：验证 _parse_silencedetect_output 的解析与边界处理。

原则：
- 不调用 ffmpeg
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

from tools import _parse_silencedetect_output


class TestParseSilencedetectOutput(unittest.TestCase):
    """验证解析、边界与无效输入的处理。"""

    def test_multiple_silence_intervals(self):
        """两条完整的 silence_start / silence_end 应被正确解析。"""

        output = (
            "[silencedetect @ 0x1] silence_start: 0.5\n"
            "[silencedetect @ 0x1] silence_end: 1.2 | silence_duration: 0.7\n"
            "[silencedetect @ 0x1] silence_start: 3.0\n"
            "[silencedetect @ 0x1] silence_end: 4.5 | silence_duration: 1.5\n"
        )

        result = _parse_silencedetect_output(output, 10.0)

        self.assertEqual(len(result), 2)

        self.assertAlmostEqual(result[0]["start_seconds"], 0.5)
        self.assertAlmostEqual(result[0]["end_seconds"], 1.2)
        self.assertAlmostEqual(result[0]["duration_seconds"], 0.7)

        self.assertAlmostEqual(result[1]["start_seconds"], 3.0)
        self.assertAlmostEqual(result[1]["end_seconds"], 4.5)
        self.assertAlmostEqual(result[1]["duration_seconds"], 1.5)

    def test_silence_extending_to_end_of_media(self):
        """最后一段静音没有 silence_end：应延伸到视频总时长。"""

        output = (
            "[silencedetect @ 0x1] silence_start: 8.0\n"
        )

        result = _parse_silencedetect_output(output, 10.0)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["start_seconds"], 8.0)
        self.assertAlmostEqual(result[0]["end_seconds"], 10.0)
        self.assertAlmostEqual(result[0]["duration_seconds"], 2.0)

    def test_empty_output(self):
        """空输入应返回空列表。"""

        result = _parse_silencedetect_output("", 10.0)

        self.assertEqual(result, [])

    def test_irrelevant_lines_are_ignored(self):
        """FFmpeg 的版本、输入信息、进度行应被忽略。"""

        output = (
            "ffmpeg version 6.0\n"
            "  built with gcc\n"
            "Input #0, mov, from 'x.mp4':\n"
            "[silencedetect @ 0x1] silence_start: 1.0\n"
            "frame=  100 fps=0.0 q=-0.0 size=N/A time=00:00:02.00\n"
            "[silencedetect @ 0x1] silence_end: 2.0 | silence_duration: 1.0\n"
            "size=N/A time=00:00:10.00 bitrate=N/A speed= 100x\n"
        )

        result = _parse_silencedetect_output(output, 10.0)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["start_seconds"], 1.0)
        self.assertAlmostEqual(result[0]["duration_seconds"], 1.0)

    def test_end_without_start_is_ignored(self):
        """只有 silence_end，没有对应的 silence_start：不应产生区间。"""

        output = (
            "[silencedetect @ 0x1] silence_end: 2.0 | silence_duration: 1.0\n"
        )

        result = _parse_silencedetect_output(output, 10.0)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()