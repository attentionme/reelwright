import unittest

from app import _format_request_error


class _FakeAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class TestFormatRequestError(unittest.TestCase):

    def _provider(
        self,
        display_name="DeepSeek",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
    ):
        return {
            "display_name": display_name,
            "base_url": base_url,
            "model": model,
        }

    def test_401_mentions_display_name(self):
        exc = _FakeAPIError("unauthorized", status_code=401)
        msg = _format_request_error(exc, self._provider())
        self.assertIn("401", msg)
        self.assertIn("DeepSeek", msg)

    def test_403(self):
        exc = _FakeAPIError("forbidden", status_code=403)
        msg = _format_request_error(exc, self._provider())
        self.assertIn("403", msg)

    def test_404_mentions_base_url_and_model(self):
        exc = _FakeAPIError("not found", status_code=404)
        msg = _format_request_error(
            exc,
            self._provider(
                display_name="豆包",
                base_url="https://ark.example.com",
                model="doubao-seed",
            ),
        )
        self.assertIn("404", msg)
        self.assertIn("https://ark.example.com", msg)
        self.assertIn("doubao-seed", msg)

    def test_429(self):
        exc = _FakeAPIError("rate limit", status_code=429)
        msg = _format_request_error(exc, self._provider())
        self.assertIn("429", msg)

    def test_500(self):
        exc = _FakeAPIError("internal error", status_code=500)
        msg = _format_request_error(exc, self._provider())
        self.assertIn("500", msg)

    def test_timeout(self):
        exc = TimeoutError("Connection timed out")
        msg = _format_request_error(exc, self._provider())
        self.assertIn("无法在限定时间内连接到", msg)

    def test_connection_error(self):
        exc = ConnectionError("Connection refused")
        msg = _format_request_error(exc, self._provider())
        self.assertIn("无法连接到", msg)

    def test_generic_error(self):
        exc = ValueError("some other error")
        msg = _format_request_error(exc, self._provider())
        self.assertIn("请求失败", msg)
        self.assertIn("ValueError", msg)

    def test_response_status_code_fallback(self):
        class _Resp:
            status_code = 401

        exc = _FakeAPIError("unauthorized")
        exc.response = _Resp()
        msg = _format_request_error(exc, self._provider())
        self.assertIn("401", msg)


if __name__ == "__main__":
    unittest.main()