# SPDX-License-Identifier: GPL-2.0-only

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


class SettingsTests(unittest.TestCase):
    def test_hidden_auth_strings_allow_empty_defaults(self):
        root = Path(__file__).resolve().parents[1]
        tree = ET.parse(
            root / "plugin.video.filmfriend.macsobeck" / "resources" /
            "settings.xml")
        by_id = {
            setting.attrib["id"]: setting
            for setting in tree.findall(".//setting")
        }

        for setting_id in (
                "auth_schema_version", "token_expires_at",
                "legacy_addon_migrated"):
            setting = by_id[setting_id]
            self.assertEqual("string", setting.attrib["type"])
            self.assertEqual("false", setting.findtext("visible"))
            self.assertEqual(
                "true", setting.findtext("./constraints/allowempty"))

    def test_local_fork_has_independent_addon_id(self):
        root = Path(__file__).resolve().parents[1]
        addon = ET.parse(
            root / "plugin.video.filmfriend.macsobeck" /
            "addon.xml").getroot()
        settings = ET.parse(
            root / "plugin.video.filmfriend.macsobeck" / "resources" /
            "settings.xml")

        self.assertEqual(
            "plugin.video.filmfriend.macsobeck", addon.attrib["id"])
        self.assertEqual("1.4.1", addon.attrib["version"])
        self.assertEqual("macsobeck", addon.attrib["provider-name"])
        self.assertEqual(
            "https://github.com/macsobeck/plugin.video.filmfriend.macsobeck",
            addon.findtext(".//source"),
        )
        self.assertIsNone(addon.find(".//forum"))
        description = addon.findtext(
            ".//description[@lang='en_GB']", default="")
        self.assertIn("Ingo-FP-Angel", description)
        self.assertIn("Stadtbibliothek Stuttgart", description)
        self.assertEqual(
            "RunScript(plugin.video.filmfriend.macsobeck, libraryPicker)",
            settings.findtext(".//setting[@id='libraryPicker']/data"),
        )


if __name__ == "__main__":
    unittest.main()
