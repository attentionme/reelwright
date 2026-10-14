"""
最小回归测试：验证 _extract_history_lines 的格式兼容性。

覆盖点：
- Gradio 5.x 的 message block 格式（content 是 list of dict）
- 旧版字符串格式（content 是 str）
- 混合格式
- 空 history / None
- 非 dict 元素被跳过
- 未知 role 被跳过
- 空内容被跳过
- 超长 history 只保留最后 8 条
- 多 block content 用换行拼接
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import _extract_history_lines


class TestExtractHistoryLines(unittest.TestCase):

    def test_none_history(self):
        self.assertEqual(_extract_history_lines(None), [])

    def test_empty_history(self):
        self.assertEqual(_extract_history_lines([]), [])

    def test_gradio_5x_format(self):
        """Gradio 5.x：content 是 list of message blocks。"""

        history = [
            {
                "role": "user",
                "content": [{"text": "你好", "type": "text"}],
            },
            {
                "role": "assistant",
                "content": [{"text": "你好，有什么可以帮你？", "type": "text"}],
            },
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "用户：你好")
        self.assertEqual(lines[1], "助手：你好，有什么可以帮你？")

    def test_legacy_string_format(self):
        """旧版：content 是 str。"""

        history = [
            {"role": "user", "content": "老格式用户消息"},
            {"role": "assistant", "content": "老格式助手回复"},
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "用户：老格式用户消息")
        self.assertEqual(lines[1], "助手：老格式助手回复")

    def test_multi_block_content_joined_with_newline(self):
        """多 block content：应使用换行拼接。"""

        history = [
            {
                "role": "user",
                "content": [
                    {"text": "第一段", "type": "text"},
                    {"text": "第二段", "type": "text"},
                ],
            },
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "用户：第一段\n第二段")

    def test_non_dict_items_skipped(self):
        history = [
            "not a dict",
            42,
            {"role": "user", "content": "有效"},
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(lines, ["用户：有效"])

    def test_unknown_role_skipped(self):
        history = [
            {"role": "system", "content": "系统消息"},
            {"role": "user", "content": "用户消息"},
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(lines, ["用户：用户消息"])

    def test_empty_content_skipped(self):
        history = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": []},
            {"role": "user", "content": "非空"},
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(lines, ["用户：非空"])

    def test_non_string_content_skipped(self):
        history = [
            {"role": "user", "content": 123},
            {"role": "user", "content": None},
            {"role": "user", "content": "有效"},
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(lines, ["用户：有效"])

    def test_block_without_text_key_skipped(self):
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"text": "有效文本", "type": "text"},
                ],
            },
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(lines, ["用户：有效文本"])

    def test_only_last_8_items_kept(self):
        history = [
            {"role": "user", "content": f"消息{i}"}
            for i in range(12)
        ]

        lines = _extract_history_lines(history)

        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0], "用户：消息4")
        self.assertEqual(lines[-1], "用户：消息11")


if __name__ == "__main__":
    unittest.main()