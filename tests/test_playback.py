# SPDX-License-Identifier: GPL-2.0-only

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.playback import widevine_properties  # noqa: E402


class PlaybackTests(unittest.TestCase):
    def test_kodi_21_widevine_properties_use_one_drm_interface(self):
        props = widevine_properties("https://license.example.test/wv")

        self.assertEqual(
            {"inputstream.adaptive.drm_legacy"},
            set(props),
        )
        self.assertIn(
            "com.widevine.alpha|https://license.example.test/wv|",
            props["inputstream.adaptive.drm_legacy"],
        )
        self.assertIn(
            "Content-Type=application%2Foctet-stream",
            props["inputstream.adaptive.drm_legacy"],
        )


if __name__ == "__main__":
    unittest.main()
