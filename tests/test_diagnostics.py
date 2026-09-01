# SPDX-License-Identifier: GPL-2.0-only

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.diagnostics import StructuredLogger  # noqa: E402


class DiagnosticsTests(unittest.TestCase):
    def test_structured_logger_redacts_credentials_tokens_and_auth_codes(self):
        output = []
        logger = StructuredLogger(
            lambda message, level: output.append((message, level)),
            clock=lambda: 100,
        )
        token = "abcdefgh.ijklmnop.qrstuvwx"

        logger.debug(
            "test.event",
            password="super-secret",
            refresh_token="refresh-secret",
            headers={"Authorization": f"Bearer {token}"},
            url="https://example.test/callback?code=auth-secret&state=ok",
            form="j_password=encoded-secret&safe=yes",
        )

        raw, level = output[0]
        record = json.loads(raw)
        self.assertEqual("debug", level)
        self.assertEqual("<redacted>", record["password"])
        self.assertEqual("<redacted>", record["refresh_token"])
        self.assertNotIn("super-secret", raw)
        self.assertNotIn("refresh-secret", raw)
        self.assertNotIn("encoded-secret", raw)
        self.assertNotIn("auth-secret", raw)
        self.assertNotIn(token, raw)
        self.assertIn("state=ok", record["url"])


if __name__ == "__main__":
    unittest.main()
