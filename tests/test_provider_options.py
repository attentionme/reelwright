import unittest

from app import _provider_options


class TestProviderOptions(unittest.TestCase):

    def test_typical_config(self):
        config = {
            "active_provider": "doubao",
            "providers": {
                "deepseek": {"display_name": "DeepSeek"},
                "doubao": {"display_name": "豆包（火山方舟）"},
            },
        }
        choices, default = _provider_options(config)
        self.assertEqual(default, "doubao")
        names = [c[1] for c in choices]
        self.assertEqual(names, ["deepseek", "doubao"])
        self.assertEqual(choices[0], ("DeepSeek", "deepseek"))
        self.assertEqual(choices[1], ("豆包（火山方舟）", "doubao"))

    def test_deepseek_first_even_alphabetically_later(self):
        config = {
            "active_provider": "deepseek",
            "providers": {
                "zhipu": {"display_name": "智谱"},
                "deepseek": {"display_name": "DeepSeek"},
                "doubao": {"display_name": "豆包"},
            },
        }
        choices, _ = _provider_options(config)
        self.assertEqual(choices[0][1], "deepseek")

    def test_missing_display_name_falls_back_to_name(self):
        config = {
            "active_provider": "custom",
            "providers": {
                "custom": {"base_url": "https://x", "api_key": ""},
            },
        }
        choices, default = _provider_options(config)
        self.assertEqual(choices[0], ("custom", "custom"))
        self.assertEqual(default, "custom")

    def test_active_not_in_providers_falls_back_to_first(self):
        config = {
            "active_provider": "missing",
            "providers": {
                "deepseek": {"display_name": "DeepSeek"},
            },
        }
        _, default = _provider_options(config)
        self.assertEqual(default, "deepseek")

    def test_empty_providers_falls_back_to_default_config(self):
        choices, default = _provider_options({"providers": {}})
        self.assertTrue(choices)
        self.assertEqual(default, "deepseek")

    def test_non_dict_config_falls_back_to_default_config(self):
        choices, default = _provider_options(None)
        self.assertTrue(choices)
        self.assertEqual(default, "deepseek")

    def test_non_dict_providers_falls_back_to_default_config(self):
        choices, default = _provider_options({"providers": "bad"})
        self.assertTrue(choices)
        self.assertEqual(default, "deepseek")

    def test_non_dict_provider_entry(self):
        config = {
            "active_provider": "x",
            "providers": {
                "x": "invalid",
            },
        }
        choices, _ = _provider_options(config)
        self.assertEqual(choices, [("x", "x")])

    def test_non_string_name_skipped(self):
        config = {
            "active_provider": "deepseek",
            "providers": {
                "deepseek": {"display_name": "DeepSeek"},
                "": {"display_name": "Empty"},
            },
        }
        choices, _ = _provider_options(config)
        names = [c[1] for c in choices]
        self.assertNotIn("", names)
        self.assertIn("deepseek", names)


if __name__ == "__main__":
    unittest.main()