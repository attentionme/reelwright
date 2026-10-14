"""
最小回归测试：验证 _build_compliance_summary 的状态汇总逻辑。

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

from tools import _build_compliance_summary


class TestBuildComplianceSummary(unittest.TestCase):
    """验证整体状态判定、status_counts 分发与列表归类。"""

    def test_empty_checks_is_pass(self):
        result = _build_compliance_summary({})

        self.assertEqual(result["overall_status"], "pass")
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["needs_review"], [])
        self.assertEqual(
            result["status_counts"]["pass"], 0
        )

    def test_all_pass_is_pass(self):
        checks = {
            "a": {"status": "pass", "message": "ok"},
            "b": {"status": "pass", "message": "ok"},
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "pass")
        self.assertEqual(result["status_counts"]["pass"], 2)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["needs_review"], [])

    def test_fail_dominates_review(self):
        """同时存在 fail 和 not_checked，整体必须是 fail。"""

        checks = {
            "a": {"status": "fail", "message": "hard fail"},
            "b": {"status": "not_checked", "message": "unknown"},
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "fail")
        self.assertEqual(result["status_counts"]["fail"], 1)
        self.assertEqual(result["status_counts"]["not_checked"], 1)
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(len(result["needs_review"]), 1)

    def test_not_checked_triggers_needs_review(self):
        checks = {
            "a": {"status": "not_checked", "message": "unknown"},
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "needs_review")
        self.assertEqual(result["failures"], [])
        self.assertEqual(len(result["needs_review"]), 1)
        self.assertEqual(
            result["needs_review"][0]["check"], "a"
        )
        self.assertEqual(
            result["needs_review"][0]["status"], "not_checked"
        )

    def test_not_configured_triggers_needs_review(self):
        checks = {
            "fps": {"status": "not_configured", "message": "no target"},
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "needs_review")
        self.assertEqual(
            result["status_counts"]["not_configured"], 1
        )
        self.assertEqual(len(result["needs_review"]), 1)

    def test_below_target_triggers_needs_review(self):
        checks = {
            "duration": {
                "status": "below_target",
                "message": "short",
            },
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "needs_review")
        self.assertEqual(
            result["status_counts"]["informational"], 1
        )
        self.assertEqual(len(result["needs_review"]), 1)
        self.assertEqual(
            result["needs_review"][0]["status"], "below_target"
        )

    def test_above_target_triggers_needs_review(self):
        checks = {
            "duration": {
                "status": "above_target",
                "message": "long",
            },
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "needs_review")
        self.assertEqual(
            result["status_counts"]["informational"], 1
        )
        self.assertEqual(len(result["needs_review"]), 1)

    def test_at_target_does_not_trigger_review(self):
        """at_target 计入 informational，但不进入 needs_review。"""

        checks = {
            "duration": {
                "status": "at_target",
                "message": "on target",
            },
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "pass")
        self.assertEqual(
            result["status_counts"]["informational"], 1
        )
        self.assertEqual(result["needs_review"], [])
        self.assertEqual(result["failures"], [])

    def test_not_applicable_does_not_trigger_review(self):
        """not_applicable 只计数，不触发 fail / needs_review。"""

        checks = {
            "dialogue_content": {
                "status": "not_applicable",
                "message": "n/a",
            },
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "pass")
        self.assertEqual(
            result["status_counts"]["not_applicable"], 1
        )
        self.assertEqual(result["needs_review"], [])

    def test_full_distribution(self):
        """一次覆盖全部状态类型，核对计数。"""

        checks = {
            "aspect_ratio": {"status": "fail", "message": "bad ratio"},
            "duration": {
                "status": "fail",
                "message": "too long",
            },
            "fps": {"status": "not_configured", "message": "no target"},
            "subtitle_stream": {"status": "pass", "message": "ok"},
            "background_music": {
                "status": "not_checked",
                "message": "unknown",
            },
            "burned_in_subtitles": {
                "status": "not_checked",
                "message": "unknown",
            },
            "dialogue_content": {
                "status": "not_applicable",
                "message": "n/a",
            },
            "audio_activity": {
                "status": "informational",
                "message": "ratio",
            },
        }

        result = _build_compliance_summary(checks)

        self.assertEqual(result["overall_status"], "fail")
        self.assertEqual(result["status_counts"]["fail"], 2)
        self.assertEqual(result["status_counts"]["pass"], 1)
        self.assertEqual(result["status_counts"]["not_checked"], 2)
        self.assertEqual(result["status_counts"]["not_configured"], 1)
        self.assertEqual(result["status_counts"]["not_applicable"], 1)
        self.assertEqual(result["status_counts"]["informational"], 1)
        self.assertEqual(len(result["failures"]), 2)
        self.assertEqual(len(result["needs_review"]), 3)

        review_checks = sorted(
            item["check"] for item in result["needs_review"]
        )
        self.assertEqual(
            review_checks,
            ["background_music", "burned_in_subtitles", "fps"],
        )

        failure_checks = sorted(
            item["check"] for item in result["failures"]
        )
        self.assertEqual(
            failure_checks,
            ["aspect_ratio", "duration"],
        )


if __name__ == "__main__":
    unittest.main()