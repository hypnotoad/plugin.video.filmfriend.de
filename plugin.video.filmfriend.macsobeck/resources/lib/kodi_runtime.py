# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""Kodi-specific adapters for the testable Filmfriend services."""

import os

import requests
import xbmc
import xbmcaddon
import xbmcvfs

from resources.lib.api import FilmfriendApi
from resources.lib.auth import AuthenticationService, FileRefreshLock, OAuthClient
from resources.lib.diagnostics import StructuredLogger
from resources.lib.legacy_settings import (
    LEGACY_ADDON_ID,
    migrate_legacy_settings,
)


class KodiSettings:
    def __init__(self, addon=None):
        self._addon = addon or xbmcaddon.Addon()

    def get(self, key):
        return self._addon.getSetting(key)

    def set(self, key, value):
        return self._addon.setSetting(key, str(value))


def build_logger(addon=None):
    addon = addon or xbmcaddon.Addon()
    levels = {
        "debug": xbmc.LOGDEBUG,
        "info": xbmc.LOGINFO,
        "warning": xbmc.LOGWARNING,
        "error": xbmc.LOGERROR,
    }

    def sink(message, level):
        xbmc.log(message, levels.get(level, xbmc.LOGDEBUG))

    return StructuredLogger(sink, addon.getAddonInfo("id"))


def build_runtime(language="en"):
    addon = xbmcaddon.Addon()
    settings = KodiSettings(addon)
    logger = build_logger(addon)
    if addon.getAddonInfo("id") != LEGACY_ADDON_ID:
        try:
            legacy_addon = xbmcaddon.Addon(id=LEGACY_ADDON_ID)
        except (RuntimeError, SystemError):
            legacy_addon = None
        if legacy_addon is not None:
            migrate_legacy_settings(
                settings, KodiSettings(legacy_addon), logger=logger)
    profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
    os.makedirs(profile, exist_ok=True)
    refresh_lock = FileRefreshLock(os.path.join(profile, "auth-refresh.lock"))
    oauth = OAuthClient(requests.Session(), logger=logger)
    authentication = AuthenticationService(
        settings, oauth, refresh_lock, logger=logger)
    api = FilmfriendApi(
        requests.Session(),
        authentication,
        settings,
        logger=logger,
        language=language,
    )
    return settings, logger, oauth, authentication, api
