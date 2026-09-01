# SPDX-License-Identifier: GPL-2.0-only

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))


class ListItem:
    def __init__(self, path="", **kwargs):
        self.path = path
        self.properties = {}
        self.mime_type = None
        self.content_lookup = None

    def setProperty(self, key, value):
        self.properties[key] = value

    def setMimeType(self, value):
        self.mime_type = value

    def setContentLookup(self, value):
        self.content_lookup = value


sys.modules.setdefault("xbmcaddon", types.ModuleType("xbmcaddon"))
xbmcgui = sys.modules.setdefault("xbmcgui", types.ModuleType("xbmcgui"))
xbmcgui.ListItem = ListItem
sys.modules.setdefault("xbmcplugin", types.ModuleType("xbmcplugin"))

from resources.lib.external.libmediathek4 import lm4  # noqa: E402


class KodiPlaybackTests(unittest.TestCase):
    def test_drm_properties_come_from_selected_item_not_last_loop_item(self):
        instance = object.__new__(lm4)
        item, url = instance._chooseBitrate([
            {
                "stream": "DASH",
                "url": "https://media.example.test/manifest.mpd",
                "widevine_license_url": "https://license.example.test/wv",
            },
            {
                "stream": "unsupported",
                "url": "https://media.example.test/not-selected",
            },
        ])

        self.assertEqual("https://media.example.test/manifest.mpd", url)
        self.assertIn(
            "inputstream.adaptive.drm_legacy", item.properties)
        self.assertNotIn(
            "inputstream.adaptive.license_type", item.properties)
        self.assertNotIn(
            "inputstream.adaptive.license_key", item.properties)
        self.assertEqual("application/dash+xml", item.mime_type)
        self.assertFalse(item.content_lookup)


if __name__ == "__main__":
    unittest.main()
