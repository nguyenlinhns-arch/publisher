from __future__ import annotations

import unittest

from mxh_publisher.logging_utils import redact_text


class RedactionTests(unittest.TestCase):
    def test_redacts_tokens_and_authorization(self) -> None:
        text = "access_token=abc123 Authorization: Bearer secret-value cookie=session"
        redacted = redact_text(text)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("secret-value", redacted)
        self.assertNotIn("session", redacted)
        self.assertIn("REDACTED", redacted)


if __name__ == "__main__":
    unittest.main()
