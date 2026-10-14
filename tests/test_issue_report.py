"""
最小回归测试：验证 _build_video_issue_report 的分类与计数逻辑。

原则：
- 不调用 ffprobe / ffmpeg
- 不调用 LLM
- 不访问网络
- 只测纯函数行为
"""

import sys
import unittest
from pathlib import Path

# 保证无论从哪个工作目录运行，都能 import tools
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import _build_video_issue_report


class TestIssueReportClassification(unittest.TestCase):
    """验证 issue_report 的分类、计数、整体状态与定制输出。"""

    def test_full_mix_classification(self):
        """一次性覆盖 7 类状态，验证 counts 与 items 分布。"""

        checks = {
            "aspect_ratio": {
                "status": "fail",
                "message": "画幅不符",
                "expected": "9:16",
                "width": 1600,
                "height": 896,
            },
            "duration": {
                "status": "fail",
                "message": "镜头超限",
                "actual_seconds": 12.25,
                "maximum_seconds": 12,
                "difference_seconds": 0.25,
            },
            "fps": {
                "status": "not_configured",
                "message": "未配置目标帧率",
                "actual": 24,
            },
            "subtitle_stream": {
                "status": "pass",
                "message": "无独立字幕轨道",
            },
            "background_music": {
                "status": "not_checked",
                "message": "无法确认是否存在 BGM",
            },
            "burned_in_subtitles": {
                "status": "not_checked",
                "message": "无法确认是否存在内嵌字幕",
            },
            "dialogue_content": {
                "status": "not_applicable",
                "message": "项目允许对白，本项不适用",
            },
            "audio_activity": {
                "status": "informational",
                "message": "音频活动比例 41.86%",
            },
        }
        compliance_summary = {"overall_status": "fail"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="shot",
        )

        counts = report["counts"]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(counts["error_count"], 2)
        self.assertEqual(counts["warning_count"], 3)
        self.assertEqual(counts["info_count"], 1)
        self.assertEqual(counts["pass_count"], 1)
        self.assertEqual(counts["target_met_count"], 0)
        self.assertEqual(counts["not_applicable_count"], 1)
        self.assertEqual(counts["unclassified_count"], 0)
        self.assertEqual(counts["total_items"], 6)
        self.assertEqual(counts["total_check_count"], 8)

        severities = [item["severity"] for item in report["items"]]
        self.assertEqual(severities.count("error"), 2)
        self.assertEqual(severities.count("warning"), 3)
        self.assertEqual(severities.count("info"), 1)

        # headline 至少应体现 error 数量
        self.assertIn("2", report["headline"])

    def test_at_target_in_episode(self):
        """整集时长恰好达到目标时，进入 target_met_count，而非 pass_count。"""

        checks = {
            "duration": {
                "status": "at_target",
                "message": "整集时长与目标一致",
                "actual_seconds": 45.0,
                "target_seconds": 45,
                "difference_seconds": 0,
            },
        }
        compliance_summary = {"overall_status": "pass"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="episode",
        )

        counts = report["counts"]

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(counts["target_met_count"], 1)
        self.assertEqual(counts["pass_count"], 0)
        self.assertEqual(counts["error_count"], 0)
        self.assertEqual(counts["warning_count"], 0)
        self.assertEqual(counts["info_count"], 0)
        self.assertEqual(counts["total_items"], 0)
        self.assertEqual(counts["total_check_count"], 1)

        passed_statuses = [
            item["status"] for item in report["passed_items"]
        ]
        self.assertIn("at_target", passed_statuses)

    def test_above_target_is_warning(self):
        """整集时长高于目标：warning，不是 error。"""

        checks = {
            "duration": {
                "status": "above_target",
                "message": "超过目标时长",
                "actual_seconds": 50.0,
                "target_seconds": 45,
                "difference_seconds": 5,
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="episode",
        )

        counts = report["counts"]

        self.assertEqual(report["overall_status"], "needs_review")
        self.assertEqual(counts["warning_count"], 1)
        self.assertEqual(counts["error_count"], 0)
        self.assertEqual(counts["total_items"], 1)
        self.assertEqual(counts["total_check_count"], 1)

    def test_below_target_is_warning(self):
        """整集时长低于目标：warning，不是 error。"""

        checks = {
            "duration": {
                "status": "below_target",
                "message": "低于目标时长",
                "actual_seconds": 40.0,
                "target_seconds": 45,
                "difference_seconds": -5,
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="episode",
        )

        counts = report["counts"]

        self.assertEqual(counts["warning_count"], 1)
        self.assertEqual(counts["error_count"], 0)

    def test_unknown_status_goes_to_unclassified(self):
        """未知状态进入 unclassified，且不污染 total_items。"""

        checks = {
            "future_check": {
                "status": "some_new_state",
                "message": "未来新增状态",
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="shot",
        )

        counts = report["counts"]

        self.assertEqual(counts["unclassified_count"], 1)
        self.assertEqual(counts["error_count"], 0)
        self.assertEqual(counts["warning_count"], 0)
        self.assertEqual(counts["info_count"], 0)
        self.assertEqual(counts["total_items"], 0)
        self.assertEqual(counts["total_check_count"], 1)
        self.assertEqual(len(report["unclassified_items"]), 1)

    def test_overall_status_default_when_missing(self):
        """compliance_summary 未给 overall_status 时，缺省 needs_review。"""

        report = _build_video_issue_report(
            checks={},
            compliance_summary={},
            video_scope="shot",
        )

        self.assertEqual(report["overall_status"], "needs_review")
        self.assertEqual(report["counts"]["total_items"], 0)
        self.assertEqual(report["counts"]["total_check_count"], 0)

    def test_shot_duration_fail_title_and_reason(self):
        """单镜头超限：验证 title 与 reason 定制输出。"""

        checks = {
            "duration": {
                "status": "fail",
                "message": "原始信息",
                "actual_seconds": 12.25,
                "maximum_seconds": 12,
                "difference_seconds": 0.25,
            },
        }
        compliance_summary = {"overall_status": "fail"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="shot",
        )

        self.assertEqual(len(report["items"]), 1)

        item = report["items"][0]

        self.assertEqual(item["title"], "单镜头时长超过限制")
        self.assertIn("12.25", item["reason"])
        self.assertIn("0.250", item["reason"])

    def test_episode_below_target_with_tolerance_recommendation(self):
        """episode 超出容差：recommendation 应提到已配置的允许误差。"""

        checks = {
            "duration": {
                "status": "below_target",
                "message": "整集偏短",
                "actual_seconds": 40.0,
                "target_seconds": 45,
                "difference_seconds": -5.0,
                "tolerance_seconds": 2,
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="episode",
        )

        self.assertEqual(len(report["items"]), 1)

        item = report["items"][0]

        self.assertEqual(item["check"], "duration")
        self.assertIn("2", item["recommendation"])
        self.assertIn("允许误差", item["recommendation"])
        self.assertNotIn(
            "没有规定允许误差",
            item["recommendation"],
        )

    def test_episode_below_target_without_tolerance_keeps_legacy_text(self):
        """episode 无 tolerance 字段：recommendation 保持旧文案。"""

        checks = {
            "duration": {
                "status": "below_target",
                "message": "整集偏短",
                "actual_seconds": 40.0,
                "target_seconds": 45,
                "difference_seconds": -5.0,
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="episode",
        )

        item = report["items"][0]

        self.assertIn(
            "没有规定允许误差",
            item["recommendation"],
        )

    def test_fps_fail_recommendation_asks_adjustment(self):
        """fps fail（已配置但实际不符）：建议应指导调整帧率，不是配置。"""

        checks = {
            "fps": {
                "status": "fail",
                "message": "视频帧率 30.0 fps 与项目要求 24 fps 不符",
                "actual": 30.0,
                "target": 24,
            },
        }
        compliance_summary = {"overall_status": "fail"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="shot",
        )

        self.assertEqual(len(report["items"]), 1)

        item = report["items"][0]

        self.assertEqual(item["severity"], "error")
        self.assertIn("24", item["recommendation"])
        self.assertNotIn(
            "在 project.json 中配置",
            item["recommendation"],
        )

    def test_fps_not_configured_recommendation_asks_config(self):
        """fps not_configured：建议应指导去配置 target_fps。"""

        checks = {
            "fps": {
                "status": "not_configured",
                "message": "项目配置中没有规定目标帧率",
                "actual": 24.0,
                "target": None,
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="shot",
        )

        item = report["items"][0]

        self.assertIn("target_fps", item["recommendation"])

    def test_fps_not_checked_recommendation_asks_recheck(self):
        """fps not_checked（目标已配置但视频无 fps 信息）：建议重新导出。"""

        checks = {
            "fps": {
                "status": "not_checked",
                "message": "视频没有可用的帧率信息",
                "actual": None,
                "target": 24,
            },
        }
        compliance_summary = {"overall_status": "needs_review"}

        report = _build_video_issue_report(
            checks=checks,
            compliance_summary=compliance_summary,
            video_scope="shot",
        )

        item = report["items"][0]

        self.assertIn("重新导出", item["recommendation"])        

if __name__ == "__main__":
    unittest.main()