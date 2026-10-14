"""
最小回归测试：验证 _build_fps_check 的分支与字段。

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

from tools import _build_fps_check


class TestBuildFpsCheck(unittest.TestCase):
    """验证 not_configured / not_checked / pass / fail 四条分支。"""

    def test_target_not_configured(self):
        result = _build_fps_check(actual_fps=24.0, target_fps=None)

        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["actual"], 24.0)
        self.assertIsNone(result["target"])

    def test_target_configured_but_actual_missing(self):
        result = _build_fps_check(actual_fps=None, target_fps=24)

        self.assertEqual(result["status"], "not_checked")
        self.assertIsNone(result["actual"])
        self.assertEqual(result["target"], 24)

    def test_exact_match(self):
        result = _build_fps_check(actual_fps=24.0, target_fps=24)

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["difference"], 0.0)

    def test_23_976_against_24_is_pass(self):
        """23.976 与 24 的差异在容差内，应判 pass。"""

        result = _build_fps_check(actual_fps=23.976, target_fps=24)

        self.assertEqual(result["status"], "pass")
        self.assertLessEqual(result["difference"], 0.5)

    def test_25_against_24_is_fail(self):
        """25 与 24 差异超容差，应判 fail。"""

        result = _build_fps_check(actual_fps=25.0, target_fps=24)

        self.assertEqual(result["status"], "fail")
        self.assertGreater(result["difference"], 0.5)
        self.assertIn("不符合", result["message"])

    def test_30_against_24_is_fail(self):
        result = _build_fps_check(actual_fps=30.0, target_fps=24)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["difference"], 6.0)

    def test_custom_tolerance(self):
        """自定义容差应生效。"""

        result = _build_fps_check(
            actual_fps=25.0,
            target_fps=24,
            tolerance=1.0,
        )

        self.assertEqual(result["status"], "pass")

    def test_pass_required_fields(self):
        result = _build_fps_check(actual_fps=24.0, target_fps=24)

        for key in ("status", "actual", "target", "difference", "message"):
            self.assertIn(key, result)

    def test_not_configured_required_fields(self):
        result = _build_fps_check(actual_fps=24.0, target_fps=None)

        for key in ("status", "actual", "target", "message"):
            self.assertIn(key, result)

    def test_not_checked_required_fields(self):
        result = _build_fps_check(actual_fps=None, target_fps=24)

        for key in ("status", "actual", "target", "message"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()