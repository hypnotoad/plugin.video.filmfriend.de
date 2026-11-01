# SPDX-License-Identifier: GPL-2.0-only

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.catalog import release_date_metadata  # noqa: E402


class CatalogMetadataTests(unittest.TestCase):
    def test_iso_release_date_is_translated_to_kodi_metadata(self):
        self.assertEqual(
            {
                "year": "2026",
                "premiered": "2026-11-01",
                "aired": "2026-11-01",
            },
            release_date_metadata("2026-11-01T12:34:56Z"),
        )

    def test_null_release_date_is_ignored(self):
        self.assertEqual({}, release_date_metadata(None))

    def test_empty_or_malformed_release_date_is_ignored(self):
        for value in ("", "   ", "unknown"):
            with self.subTest(value=value):
                self.assertEqual({}, release_date_metadata(value))


if __name__ == "__main__":
    unittest.main()
