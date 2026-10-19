import unittest

from app import (
    DEFAULT_CONFIG,
    _resolve_provider_config,
)


class TestResolveProviderConfig(unittest.TestCase):

    def test_provider_exists_with_full_config(self):
        config = {
            "active_provider": "doubao",
            "providers": {
                "doubao": {
                    "display_name": "豆包",
                    "base_url": "https://ark.example.com",
                    "default_model": "doubao-seed",
                    "models": ["doubao-seed"],
                    "api_key": "sk-doubao",
                },
            },
        }
        result = _resolve_provider_config(config, "doubao")
        self.assertEqual(result["name"], "doubao")
        self.assertEqual(result["display_name"], "豆包")
        self.assertEqual(result["base_url"], "https://ark.example.com")
        self.assertEqual(result["model"], "doubao-seed")
        self.assertEqual(result["api_key"], "sk-doubao")
        self.assertTrue(result["configured"])

    def test_explicit_provider_name_takes_priority(self):
        config = {
            "active_provider": "deepseek",
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "default_model": "deepseek-flash",
                    "models": ["deepseek-flash"],
                    "display_name": "DeepSeek",
                    "api_key": "",
                },
                "doubao": {
                    "base_url": "https://ark.example.com",
                    "default_model": "doubao-seed",
                    "models": ["doubao-seed"],
                    "display_name": "豆包",
                    "api_key": "",
                },
            },
        }
        result = _resolve_provider_config(config, "doubao")
        self.assertEqual(result["name"], "doubao")
        self.assertEqual(result["base_url"], "https://ark.example.com")

    def test_falls_back_to_active_provider(self):
        config = {
            "active_provider": "doubao",
            "providers": {
                "doubao": {
                    "base_url": "https://ark.example.com",
                    "default_model": "doubao-seed",
                    "models": ["doubao-seed"],
                    "display_name": "豆包",
                    "api_key": "",
                },
            },
        }
        result = _resolve_provider_config(config, None)
        self.assertEqual(result["name"], "doubao")

    def test_unknown_provider_falls_back_to_deepseek(self):
        config = {
            "active_provider": "unknown_provider",
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "default_model": "deepseek-flash",
                    "models": ["deepseek-flash"],
                    "display_name": "DeepSeek",
                    "api_key": "",
                },
            },
        }
        result = _resolve_provider_config(config, None)
        self.assertEqual(result["name"], "deepseek")
        self.assertTrue(result["configured"])

    def test_missing_default_model_falls_back_to_models_first(self):
        config = {
            "active_provider": "custom",
            "providers": {
                "custom": {
                    "base_url": "https://custom.example.com",
                    "models": ["model-a", "model-b"],
                    "display_name": "自定义",
                    "api_key": "",
                },
            },
        }
        result = _resolve_provider_config(config, "custom")
        self.assertEqual(result["model"], "model-a")
        self.assertTrue(result["configured"])

    def test_legacy_model_field_compat(self):
        config = {
            "active_provider": "deepseek",
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "model": "deepseek-flash",
                    "api_key": "sk-old",
                },
            },
        }
        result = _resolve_provider_config(config, "deepseek")
        self.assertEqual(result["model"], "deepseek-flash")
        self.assertEqual(result["api_key"], "sk-old")

    def test_missing_base_url_custom_provider_not_configured(self):
        config = {
            "active_provider": "custom",
            "providers": {
                "custom": {
                    "default_model": "model-x",
                    "models": ["model-x"],
                    "display_name": "自定义",
                    "api_key": "",
                },
            },
        }
        result = _resolve_provider_config(config, "custom")
        self.assertFalse(result["configured"])

    def test_missing_model_custom_provider_not_configured(self):
        config = {
            "active_provider": "custom",
            "providers": {
                "custom": {
                    "base_url": "https://custom.example.com",
                    "display_name": "自定义",
                    "api_key": "",
                },
            },
        }
        result = _resolve_provider_config(config, "custom")
        self.assertFalse(result["configured"])

    def test_empty_api_key_does_not_raise(self):
        config = {
            "active_provider": "deepseek",
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "default_model": "deepseek-flash",
                    "models": ["deepseek-flash"],
                    "display_name": "DeepSeek",
                },
            },
        }
        result = _resolve_provider_config(config, "deepseek")
        self.assertEqual(result["api_key"], "")

    def test_non_dict_config_falls_back(self):
        result = _resolve_provider_config(None, None)
        self.assertEqual(result["name"], "deepseek")
        self.assertTrue(result["configured"])

    def test_non_dict_providers_falls_back(self):
        result = _resolve_provider_config({"providers": "invalid"}, None)
        self.assertEqual(result["name"], "deepseek")
        self.assertTrue(result["configured"])

    def test_default_config_has_all_providers(self):
        expected = {
            "deepseek", "doubao", "qwen", "kimi",
            "zhipu", "openai", "claude",
        }
        self.assertEqual(set(DEFAULT_CONFIG["providers"].keys()), expected)


if __name__ == "__main__":
    unittest.main()