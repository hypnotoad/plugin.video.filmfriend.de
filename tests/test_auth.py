# SPDX-License-Identifier: GPL-2.0-only

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.auth import (  # noqa: E402
    AuthenticationService,
    AuthenticationError,
    FileRefreshLock,
    LoginExpired,
    OAuthError,
    SettingsMigrator,
    jwt_expiry,
)
from tests.helpers import FakeLock, FakeSettings, jwt  # noqa: E402


class OAuth:
    def __init__(self, result=None, error=None, callback=None):
        self.result = result
        self.error = error
        self.callback = callback
        self.calls = []

    def refresh(self, refresh_token, provider):
        self.calls.append((refresh_token, provider))
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return self.result


class AuthenticationTests(unittest.TestCase):
    def test_decodes_urlsafe_jwt_expiry_without_crypto_dependency(self):
        token = jwt(123456789, marker="-_")
        self.assertEqual(123456789, jwt_expiry(token))
        self.assertIsNone(jwt_expiry("not-a-jwt"))

    def test_legacy_settings_migrate_without_clearing_tokens(self):
        values = {
            "library": "Example",
            "provider": "provider-id",
            "access_token": jwt(2000),
            "refresh_token": "legacy-refresh",
        }
        settings = FakeSettings(values)

        changed = SettingsMigrator(settings).migrate()

        self.assertTrue(changed)
        self.assertEqual("de", settings.get("country"))
        self.assertEqual("legacy", settings.get("provider_type"))
        self.assertEqual("legacy-refresh", settings.get("refresh_token"))
        self.assertEqual("2", settings.get("auth_schema_version"))
        self.assertEqual("2000", settings.get("token_expires_at"))

    def test_refreshes_early_and_persists_rotated_refresh_first(self):
        settings = FakeSettings({
            "auth_schema_version": "2",
            "access_token": jwt(1010, "old"),
            "refresh_token": "refresh-old",
            "provider": "provider",
            "token_expires_at": "1010",
        })
        oauth = OAuth(result={
            "access_token": jwt(2000, "new"),
            "refresh_token": "refresh-new",
            "expires_in": 1000,
        })
        auth = AuthenticationService(
            settings, oauth, FakeLock(), clock=lambda: 1000, expiry_skew=60)

        token = auth.get_access_token()

        self.assertEqual(jwt(2000, "new"), token)
        self.assertEqual([("refresh-old", "provider")], oauth.calls)
        token_writes = [
            key for key, _ in settings.writes
            if key in ("access_token", "refresh_token")
        ]
        self.assertEqual(["refresh_token", "access_token"], token_writes)

    def test_keeps_refresh_token_when_server_does_not_rotate_it(self):
        settings = FakeSettings({
            "auth_schema_version": "2",
            "access_token": jwt(900),
            "refresh_token": "refresh-existing",
            "provider": "provider",
            "token_expires_at": "900",
        })
        oauth = OAuth(result={
            "access_token": jwt(2000),
            "expires_in": 1000,
        })
        auth = AuthenticationService(
            settings, oauth, FakeLock(), clock=lambda: 1000)

        auth.get_access_token()

        self.assertEqual("refresh-existing", settings.get("refresh_token"))

    def test_recovers_if_another_process_rotated_tokens(self):
        settings = FakeSettings({
            "auth_schema_version": "2",
            "access_token": jwt(900, "old"),
            "refresh_token": "refresh-old",
            "provider": "provider",
            "token_expires_at": "900",
        })
        new_access = jwt(2000, "other-process")

        def concurrent_write():
            settings.set("refresh_token", "refresh-new")
            settings.set("access_token", new_access)
            settings.set("token_expires_at", "2000")

        oauth = OAuth(
            error=OAuthError("invalid_grant", 400),
            callback=concurrent_write,
        )
        auth = AuthenticationService(
            settings, oauth, FakeLock(), clock=lambda: 1000)

        self.assertEqual(new_access, auth.get_access_token())

    def test_rejected_refresh_token_is_reported_as_expired(self):
        settings = FakeSettings({
            "auth_schema_version": "2",
            "access_token": jwt(900),
            "refresh_token": "refresh-old",
            "provider": "provider",
            "token_expires_at": "900",
        })
        oauth = OAuth(error=OAuthError("invalid_grant", 400))
        auth = AuthenticationService(
            settings, oauth, FakeLock(), clock=lambda: 1000)

        with self.assertRaises(LoginExpired):
            auth.get_access_token()

    def test_file_refresh_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "refresh.lock")
            first = FileRefreshLock(path, wait_seconds=0)
            with first:
                with self.assertRaises(AuthenticationError):
                    with FileRefreshLock(path, wait_seconds=0):
                        pass
            with FileRefreshLock(path, wait_seconds=0):
                self.assertTrue(Path(path).exists())
            self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
