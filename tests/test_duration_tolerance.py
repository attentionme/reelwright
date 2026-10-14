"""
最小回归测试：验证 _build_duration_check 的容差参数。

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

from tools import _build_duration_check


class TestDurationTolerance(unittest.TestCase):
    """验证 episode 分支在 tolerance 下的行为，以及 shot 分支不受影响。"""

    # --------------------------------------------------------
    # 向后兼容：tolerance 缺省为 0
    # --------------------------------------------------------

    def test_default_tolerance_is_zero(self):
        """不传 tolerance，等价于 tolerance=0。"""

        result = _build_duration_check(
            actual_duration=45.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["status"], "at_target")
        self.assertEqual(result["tolerance_seconds"], 0.0)

    def test_tolerance_zero_off_by_half_second_is_below(self):
        """tolerance=0，差 0.5 秒仍为 below_target。"""

        result = _build_duration_check(
            actual_duration=44.5,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=0,
        )

        self.assertEqual(result["status"], "below_target")

    # --------------------------------------------------------
    # 容差内的边界
    # --------------------------------------------------------

    def test_tolerance_2_lower_boundary_is_at_target(self):
        """tolerance=2，43 秒（差 -2）→ at_target。"""

        result = _build_duration_check(
            actual_duration=43.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "at_target")
        self.assertAlmostEqual(result["difference_seconds"], -2.0)

    def test_tolerance_2_upper_boundary_is_at_target(self):
        """tolerance=2，47 秒（差 +2）→ at_target。"""

        result = _build_duration_check(
            actual_duration=47.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "at_target")
        self.assertAlmostEqual(result["difference_seconds"], 2.0)

    def test_tolerance_2_just_below_lower_boundary(self):
        """tolerance=2，42.999 秒 → below_target。"""

        result = _build_duration_check(
            actual_duration=42.999,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "below_target")

    def test_tolerance_2_just_above_upper_boundary(self):
        """tolerance=2，47.001 秒 → above_target。"""

        result = _build_duration_check(
            actual_duration=47.001,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "above_target")

    # --------------------------------------------------------
    # 容差内外的 message 语义
    # --------------------------------------------------------

    def test_exact_match_message_says_consistent(self):
        """恰好等于目标时，message 里说“一致”。"""

        result = _build_duration_check(
            actual_duration=45.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "at_target")
        self.assertIn("一致", result["message"])

    def test_within_tolerance_message_mentions_range(self):
        """容差内非零差异时，message 里提到“允许误差”。"""

        result = _build_duration_check(
            actual_duration=44.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "at_target")
        self.assertIn("允许误差", result["message"])

    def test_below_out_of_tolerance_message_mentions_exceeded(self):
        """超出容差且低于目标时，message 提到“超出允许误差”。"""

        result = _build_duration_check(
            actual_duration=42.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "below_target")
        self.assertIn("超出允许误差", result["message"])

    def test_above_out_of_tolerance_message_mentions_exceeded(self):
        """超出容差且高于目标时，message 提到“超出允许误差”。"""

        result = _build_duration_check(
            actual_duration=48.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["status"], "above_target")
        self.assertIn("超出允许误差", result["message"])

    # --------------------------------------------------------
    # shot 分支不受影响
    # --------------------------------------------------------

    def test_shot_unaffected_by_tolerance(self):
        """shot 分支不使用 tolerance，行为不变。"""

        result = _build_duration_check(
            actual_duration=12.25,
            video_scope="shot",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=100,
        )

        self.assertEqual(result["status"], "fail")
        self.assertAlmostEqual(result["difference_seconds"], 0.25)

    # --------------------------------------------------------
    # 新字段
    # --------------------------------------------------------

    def test_tolerance_field_present_in_episode(self):
        result = _build_duration_check(
            actual_duration=45.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=2,
        )

        self.assertEqual(result["tolerance_seconds"], 2)

    def test_tolerance_zero_note_is_legacy(self):
        """tolerance=0 时，note 保持旧文案。"""

        result = _build_duration_check(
            actual_duration=45.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
            tolerance_seconds=0,
        )

        self.assertIn("没有规定允许误差", result["note"])


if __name__ == "__main__":
    unittest.main()