"""
最小回归测试：验证 _build_duration_check 的分支与字段。

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


class TestBuildDurationCheck(unittest.TestCase):
    """验证 episode / shot 两条分支以及边界行为。"""

    # --------------------------------------------------------
    # 单镜头分支
    # --------------------------------------------------------

    def test_shot_at_limit_is_pass(self):
        result = _build_duration_check(
            actual_duration=12.0,
            video_scope="shot",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["scope"], "shot")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["actual_seconds"], 12.0)
        self.assertEqual(result["maximum_seconds"], 12)
        self.assertEqual(result["difference_seconds"], 0.0)

    def test_shot_slightly_over_is_fail(self):
        result = _build_duration_check(
            actual_duration=12.25,
            video_scope="shot",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["status"], "fail")
        self.assertAlmostEqual(
            result["difference_seconds"], 0.25
        )

    def test_shot_way_over_is_fail(self):
        result = _build_duration_check(
            actual_duration=20.0,
            video_scope="shot",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["status"], "fail")
        self.assertAlmostEqual(
            result["difference_seconds"], 8.0
        )
        self.assertIn("超出", result["message"])

    # --------------------------------------------------------
    # 整集分支
    # --------------------------------------------------------

    def test_episode_at_target(self):
        result = _build_duration_check(
            actual_duration=45.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["scope"], "episode")
        self.assertEqual(result["status"], "at_target")
        self.assertEqual(result["difference_seconds"], 0.0)
        self.assertIn("note", result)

    def test_episode_below_target(self):
        result = _build_duration_check(
            actual_duration=40.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["status"], "below_target")
        self.assertAlmostEqual(
            result["difference_seconds"], -5.0
        )
        self.assertIn("少", result["message"])

    def test_episode_above_target(self):
        result = _build_duration_check(
            actual_duration=50.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
        )

        self.assertEqual(result["status"], "above_target")
        self.assertAlmostEqual(
            result["difference_seconds"], 5.0
        )
        self.assertIn("多", result["message"])

    # --------------------------------------------------------
    # 字段完整性
    # --------------------------------------------------------

    def test_shot_required_fields(self):
        result = _build_duration_check(
            actual_duration=8.0,
            video_scope="shot",
            target_duration=45,
            max_shot_duration=12,
        )

        for key in (
            "scope",
            "status",
            "actual_seconds",
            "maximum_seconds",
            "difference_seconds",
            "message",
        ):
            self.assertIn(key, result)

    def test_episode_required_fields(self):
        result = _build_duration_check(
            actual_duration=45.0,
            video_scope="episode",
            target_duration=45,
            max_shot_duration=12,
        )

        for key in (
            "scope",
            "status",
            "actual_seconds",
            "target_seconds",
            "difference_seconds",
            "message",
            "note",
        ):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()