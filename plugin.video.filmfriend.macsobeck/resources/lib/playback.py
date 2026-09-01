# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""Kodi 21 InputStream Adaptive property construction."""

import urllib.parse


def widevine_properties(license_url):
    headers = urllib.parse.urlencode({
        "Content-Type": "application/octet-stream",
    })
    return {
        # Kodi 21 / inputstream.adaptive 21.5+ simple DRM interface. Do not
        # combine this with license_type/license_key: ISA rejects mixed DRM
        # configuration before initializing the encrypted stream.
        "inputstream.adaptive.drm_legacy":
            f"com.widevine.alpha|{license_url}|{headers}",
    }
