# SPDX-License-Identifier: GPL-2.0-only

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.legacy_settings import (  # noqa: E402
    MIGRATION_MARKER,
    migrate_legacy_settings,
)
from tests.helpers import FakeSettings  # noqa: E402


class Logger:
    def __init__(self):
        self.events = []

    def info(self, event, **fields):
        self.events.append((event, fields))


class LegacySettingsTests(unittest.TestCase):
    def test_migrates_tokens_without_overwriting_current_values(self):
        current = FakeSettings({"library": "Current library"})
        legacy = FakeSettings({
            "library": "Former library",
            "tenant": "tenant-id",
            "provider": "provider-id",
            "access_token": "secret-access",
            "refresh_token": "secret-refresh",
        })
        logger = Logger()

        self.assertTrue(migrate_legacy_settings(current, legacy, logger))

        self.assertEqual("Current library", current.get("library"))
        self.assertEqual("tenant-id", current.get("tenant"))
        self.assertEqual("secret-access", current.get("access_token"))
        self.assertEqual("secret-refresh", current.get("refresh_token"))
        self.assertEqual("true", current.get(MIGRATION_MARKER))
        self.assertNotIn("secret-access", repr(logger.events))
        self.assertNotIn("secret-refresh", repr(logger.events))

    def test_migration_runs_only_once(self):
        current = FakeSettings()
        legacy = FakeSettings({"tenant": "first"})

        self.assertTrue(migrate_legacy_settings(current, legacy))
        legacy.set("tenant", "second")
        self.assertFalse(migrate_legacy_settings(current, legacy))
        self.assertEqual("first", current.get("tenant"))


if __name__ == "__main__":
    unittest.main()
