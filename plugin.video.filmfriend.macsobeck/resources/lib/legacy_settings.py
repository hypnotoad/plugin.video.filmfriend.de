# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""One-time settings migration from the former add-on identity."""


LEGACY_ADDON_ID = "plugin.video.filmfriend.de"
MIGRATION_MARKER = "legacy_addon_migrated"

# Passwords are deliberately absent. The former add-on did not declare or
# persist a password setting, and this migration must not introduce one.
MIGRATED_SETTING_IDS = (
    "country",
    "domain",
    "tenant",
    "library",
    "username",
    "provider",
    "provider_type",
    "access_token",
    "refresh_token",
    "auth_schema_version",
    "token_expires_at",
    "language",
)


def migrate_legacy_settings(current, legacy, logger=None):
    """Copy non-empty legacy values into empty settings exactly once."""
    if current.get(MIGRATION_MARKER):
        return False

    copied = 0
    for setting_id in MIGRATED_SETTING_IDS:
        if current.get(setting_id):
            continue
        value = legacy.get(setting_id)
        if value:
            current.set(setting_id, value)
            copied += 1

    current.set(MIGRATION_MARKER, "true")
    if logger:
        logger.info(
            "settings.legacy_addon_migrated",
            copied_count=copied,
            source_addon=LEGACY_ADDON_ID,
        )
    return True
