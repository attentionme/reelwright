"""
最小回归测试：验证 _build_aspect_ratio_check 的容差语义。

覆盖点：
- tolerance = 0：只接受精确匹配
- tolerance > 0：容差内 pass、容差外 fail
- 边界值：恰好等于容差
- 横屏等完全不符的情况
- 字段完整性
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import _build_aspect_ratio_check


class TestBuildAspectRatioCheck(unittest.TestCase):

    # --------------------------------------------------------
    # tolerance = 0：只接受精确匹配
    # --------------------------------------------------------

    def test_exact_match_tolerance_zero(self):
        result = _build_aspect_ratio_check(
            width=1080,
            height=1920,
            expected_aspect_ratio="9:16",
            tolerance=0,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["difference_ratio"], 0.0)

    def test_default_tolerance_zero(self):
        """不传 tolerance，等价于 tolerance=0。"""

        result = _build_aspect_ratio_check(
            width=1080,
            height=1920,
            expected_aspect_ratio="9:16",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["tolerance"], 0)

    def test_non_exact_tolerance_zero_fails(self):
        """tolerance=0 时，1080×1922 会 fail。"""

        result = _build_aspect_ratio_check(
            width=1080,
            height=1922,
            expected_aspect_ratio="9:16",
            tolerance=0,
        )

        self.assertEqual(result["status"], "fail")

    # --------------------------------------------------------
    # tolerance > 0：容差内 pass
    # --------------------------------------------------------

    def test_within_tolerance_lower(self):
        """540×990：比例 0.5455，相对偏差 3.03% < 5% → pass。"""

        result = _build_aspect_ratio_check(
            width=540,
            height=990,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertEqual(result["status"], "pass")
        self.assertLess(result["difference_ratio"], 0.05)

    def test_within_tolerance_upper(self):
        """540×930：比例 0.5806，相对偏差 3.22% < 5% → pass。"""

        result = _build_aspect_ratio_check(
            width=540,
            height=930,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertEqual(result["status"], "pass")

    def test_exact_match_with_tolerance_still_pass(self):
        result = _build_aspect_ratio_check(
            width=1080,
            height=1920,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["difference_ratio"], 0.0)

    # --------------------------------------------------------
    # tolerance > 0：容差外 fail
    # --------------------------------------------------------

    def test_outside_tolerance_fails(self):
        """540×1020：比例 0.5294，相对偏差 5.88% > 5% → fail。"""

        result = _build_aspect_ratio_check(
            width=540,
            height=1020,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertEqual(result["status"], "fail")
        self.assertGreater(result["difference_ratio"], 0.05)

    def test_horizontal_video_fails(self):
        """1600×896 是横屏，远超容差。"""

        result = _build_aspect_ratio_check(
            width=1600,
            height=896,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertEqual(result["status"], "fail")
        self.assertGreater(result["difference_ratio"], 1.0)

    # --------------------------------------------------------
    # 字段完整性
    # --------------------------------------------------------

    def test_pass_required_fields(self):
        result = _build_aspect_ratio_check(
            width=1080,
            height=1920,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        for key in (
            "status",
            "expected",
            "actual_ratio",
            "width",
            "height",
            "tolerance",
            "difference_ratio",
            "message",
        ):
            self.assertIn(key, result)

    def test_pass_message_mentions_ratio_when_within_tolerance(self):
        result = _build_aspect_ratio_check(
            width=540,
            height=990,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertIn("允许范围", result["message"])

    def test_fail_message_mentions_actual_size(self):
        result = _build_aspect_ratio_check(
            width=1600,
            height=896,
            expected_aspect_ratio="9:16",
            tolerance=0.05,
        )

        self.assertIn("不符合", result["message"])
        self.assertIn("1600", result["message"])
        self.assertIn("896", result["message"])


if __name__ == "__main__":
    unittest.main()