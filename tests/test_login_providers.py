# SPDX-License-Identifier: GPL-2.0-only

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.login_providers import select_supported_provider  # noqa: E402


class LoginProviderTests(unittest.TestCase):
    def test_selects_current_stuttgart_integrated_external_provider(self):
        methods = {
            "local": None,
            "delegated": [],
            "external": [{
                "provider": "stuttgart-provider",
                "preferIntegratedAuthentication": True,
                "displayName": None,
                "information": None,
            }],
        }

        self.assertEqual(
            ("external", "OpenId", "stuttgart-provider"),
            select_supported_provider(methods),
        )

    def test_keeps_v11_openid_and_delegated_ip_compatibility(self):
        self.assertEqual(
            ("external", "OpenId", "old-openid"),
            select_supported_provider({
                "external": [{
                    "provider": "old-openid",
                    "providerKind": "OpenId",
                }],
            }),
        )
        self.assertEqual(
            ("delegated", "Ip", "ip-provider"),
            select_supported_provider({
                "external": [],
                "delegated": [{
                    "provider": "ip-provider",
                    "providerKind": "Ip",
                }],
            }),
        )

    def test_rejects_unknown_external_flow(self):
        self.assertIsNone(select_supported_provider({
            "external": [{
                "provider": "unknown",
                "preferIntegratedAuthentication": False,
            }],
            "delegated": [],
        }))


if __name__ == "__main__":
    unittest.main()
