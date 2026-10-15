"""
最小回归测试：验证 _build_file_name_check 的分支与字段。

原则：
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

from tools import _build_file_name_check


PATTERN = r"^ep\d{2}_shot_\d{3}\.mp4$"


class TestBuildFileNameCheck(unittest.TestCase):

    # --------------------------------------------------------
    # not_configured
    # --------------------------------------------------------

    def test_pattern_not_configured(self):
        result = _build_file_name_check(
            file_name="anything.mp4",
            pattern=None,
        )

        self.assertEqual(result["status"], "not_configured")
        self.assertIsNone(result["pattern"])
        self.assertEqual(result["actual"], "anything.mp4")

    # --------------------------------------------------------
    # not_checked
    # --------------------------------------------------------

    def test_file_name_empty(self):
        result = _build_file_name_check(
            file_name=None,
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "not_checked")
        self.assertIsNone(result["actual"])

    def test_empty_string_file_name(self):
        result = _build_file_name_check(
            file_name="",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "not_checked")

    def test_invalid_pattern(self):
        result = _build_file_name_check(
            file_name="ep01_shot_001.mp4",
            pattern="[unclosed",
        )

        self.assertEqual(result["status"], "not_checked")
        self.assertIn("正则", result["message"])

    # --------------------------------------------------------
    # pass
    # --------------------------------------------------------

    def test_match_pass(self):
        result = _build_file_name_check(
            file_name="ep01_shot_001.mp4",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["actual"], "ep01_shot_001.mp4")
        self.assertEqual(result["pattern"], PATTERN)
        self.assertIn("符合", result["message"])

    def test_match_pass_high_numbers(self):
        result = _build_file_name_check(
            file_name="ep99_shot_999.mp4",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "pass")

    # --------------------------------------------------------
    # fail
    # --------------------------------------------------------

    def test_non_matching_name_fails(self):
        result = _build_file_name_check(
            file_name="第一段.mp4",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "fail")
        self.assertIn("不符合", result["message"])

    def test_wrong_digit_count_fails(self):
        """ep1_shot_001.mp4 集号位数不足。"""

        result = _build_file_name_check(
            file_name="ep1_shot_001.mp4",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "fail")

    def test_uppercase_fails(self):
        """正则区分大小写。"""

        result = _build_file_name_check(
            file_name="EP01_shot_001.mp4",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "fail")

    def test_missing_extension_fails(self):
        result = _build_file_name_check(
            file_name="ep01_shot_001",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "fail")

    def test_extra_suffix_fails(self):
        """正则用 $ 锚定结尾，多后缀应该失败。"""

        result = _build_file_name_check(
            file_name="ep01_shot_001.mp4.bak",
            pattern=PATTERN,
        )

        self.assertEqual(result["status"], "fail")

    # --------------------------------------------------------
    # 字段完整性
    # --------------------------------------------------------

    def test_pass_required_fields(self):
        result = _build_file_name_check(
            file_name="ep01_shot_001.mp4",
            pattern=PATTERN,
        )

        for key in ("status", "actual", "pattern", "message"):
            self.assertIn(key, result)

    def test_fail_required_fields(self):
        result = _build_file_name_check(
            file_name="第一段.mp4",
            pattern=PATTERN,
        )

        for key in ("status", "actual", "pattern", "message"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()