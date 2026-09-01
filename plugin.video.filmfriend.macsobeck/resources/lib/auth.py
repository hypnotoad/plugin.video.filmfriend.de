# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""Authentication and token lifecycle logic independent of Kodi UI modules."""

import base64
import json
import os
import time


TOKEN_URL = "https://api.tenant.frontend.vod.filmwerte.de/connect/token"
CLIENT_ID = "filmwerte-vod-frontend"
AUTH_SCHEMA_VERSION = 2


class AuthenticationError(RuntimeError):
    pass


class LoginRequired(AuthenticationError):
    pass


class LoginExpired(AuthenticationError):
    def __init__(self, message, endpoint=""):
        super().__init__(message)
        self.endpoint = endpoint


class OAuthError(AuthenticationError):
    def __init__(self, error="oauth_error", status_code=None):
        super().__init__(error)
        self.error = error
        self.status_code = status_code


def jwt_expiry(token):
    """Return an unverified JWT ``exp`` claim, or ``None`` for opaque/bad tokens."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        value = json.loads(decoded.decode("utf-8")).get("exp")
        return int(value) if value is not None else None
    except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


class SettingsMigrator:
    """Non-destructive migration of the settings used by releases <= 1.3.0."""

    def __init__(self, settings, logger=None):
        self._settings = settings
        self._logger = logger

    def migrate(self):
        raw_version = self._settings.get("auth_schema_version")
        try:
            version = int(raw_version or "0")
        except ValueError:
            version = 0
        if version >= AUTH_SCHEMA_VERSION:
            return False

        # v1.0.10 introduced country. Before then the add-on was DE-only.
        if self._settings.get("library") and not self._settings.get("country"):
            self._settings.set("country", "de")

        # v1.1.0 introduced provider_type, but refresh only requires provider.
        # Marking it avoids forcing an otherwise valid legacy session to log in.
        if (self._settings.get("provider")
                and not self._settings.get("provider_type")):
            self._settings.set("provider_type", "legacy")

        expiry = jwt_expiry(self._settings.get("access_token"))
        if expiry is not None:
            self._settings.set("token_expires_at", str(expiry))

        self._settings.set("auth_schema_version", str(AUTH_SCHEMA_VERSION))
        if self._logger:
            self._logger.info(
                "auth.settings_migrated",
                from_version=version,
                to_version=AUTH_SCHEMA_VERSION,
            )
        return True


class FileRefreshLock:
    """Cross-process refresh lock based on an atomic exclusive file create."""

    def __init__(self, path, wait_seconds=10.0, stale_seconds=30.0,
                 clock=None, sleep=None):
        self._path = path
        self._wait_seconds = wait_seconds
        self._stale_seconds = stale_seconds
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        self._owned = False

    def __enter__(self):
        started = self._clock()
        while True:
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode("ascii"))
                finally:
                    os.close(fd)
                self._owned = True
                return self
            except FileExistsError:
                try:
                    if self._clock() - os.path.getmtime(self._path) > self._stale_seconds:
                        os.unlink(self._path)
                        continue
                except FileNotFoundError:
                    continue
                if self._clock() - started >= self._wait_seconds:
                    raise AuthenticationError("timed out waiting for token refresh")
                self._sleep(0.05)

    def __exit__(self, exc_type, exc_value, traceback):
        if self._owned:
            try:
                os.unlink(self._path)
            except FileNotFoundError:
                pass
            self._owned = False


class OAuthClient:
    """Filmfriend OAuth grants with injected HTTP and logging dependencies."""

    def __init__(self, session, logger=None, token_url=TOKEN_URL,
                 timeout=(5, 30)):
        self._session = session
        self._logger = logger
        self._token_url = token_url
        self._timeout = timeout

    def _token_request(self, data, headers=None, session=None):
        if self._logger:
            self._logger.debug(
                "auth.token_request",
                grant_type=data.get("grant_type"),
                provider=data.get("provider", ""),
                url=self._token_url,
            )
        try:
            response = (session or self._session).post(
                self._token_url,
                data=data,
                headers=headers or {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self._timeout,
            )
        except Exception as error:
            if self._logger:
                self._logger.warning(
                    "auth.token_request_failed",
                    error="network_error",
                    error_type=error.__class__.__name__,
                )
            raise OAuthError("network_error") from error
        try:
            body = response.json()
        except (TypeError, ValueError):
            body = {}
        if response.status_code < 200 or response.status_code >= 300:
            error = body.get("error", f"http_{response.status_code}")
            if self._logger:
                self._logger.warning(
                    "auth.token_request_failed",
                    error=error,
                    status=response.status_code,
                )
            raise OAuthError(error, response.status_code)
        if body.get("error"):
            raise OAuthError(body["error"], response.status_code)
        if not body.get("access_token"):
            raise OAuthError("missing_access_token", response.status_code)
        if self._logger:
            self._logger.info(
                "auth.token_request_succeeded",
                grant_type=data.get("grant_type"),
                refresh_token_returned=bool(body.get("refresh_token")),
            )
        return body

    def refresh(self, refresh_token, provider):
        return self._token_request({
            "client_id": CLIENT_ID,
            "provider": provider,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "offline_access",
        })

    def password_grant(self, username, password, provider, headers=None):
        return self._token_request({
            "client_id": CLIENT_ID,
            "username": username,
            "password": password,
            "scope": "offline_access",
            "grant_type": "password",
            "provider": provider,
        }, headers=headers)

    def exchange_code(self, code, redirect_uri, headers=None, session=None):
        return self._token_request({
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }, headers=headers, session=session)


class AuthenticationService:
    """Own token migration, expiry checks, refresh rotation, and persistence."""

    def __init__(self, settings, oauth_client, refresh_lock, logger=None,
                 clock=None, expiry_skew=60):
        self._settings = settings
        self._oauth = oauth_client
        self._refresh_lock = refresh_lock
        self._logger = logger
        self._clock = clock or time.time
        self._expiry_skew = expiry_skew
        self._migrator = SettingsMigrator(settings, logger)

    def migrate_settings(self):
        return self._migrator.migrate()

    def _expiry(self, token):
        stored = self._settings.get("token_expires_at")
        try:
            stored_value = int(stored) if stored else None
        except ValueError:
            stored_value = None
        return jwt_expiry(token) or stored_value

    def _usable(self, token):
        if not token:
            return False
        expiry = self._expiry(token)
        return expiry is not None and expiry > self._clock() + self._expiry_skew

    def store_token_response(self, response, previous_refresh_token=""):
        access_token = response.get("access_token")
        if not access_token:
            raise OAuthError("missing_access_token")
        refresh_token = response.get("refresh_token") or previous_refresh_token

        # Persist a rotated refresh token first. If Kodi is stopped between the
        # two writes, the next process can still recover using the new token.
        if refresh_token:
            self._settings.set("refresh_token", refresh_token)
        self._settings.set("access_token", access_token)

        expires_at = jwt_expiry(access_token)
        if expires_at is None and response.get("expires_in") is not None:
            try:
                expires_at = int(self._clock()) + int(response["expires_in"])
            except (TypeError, ValueError):
                expires_at = None
        if expires_at is not None:
            self._settings.set("token_expires_at", str(expires_at))
        self._settings.set("auth_schema_version", str(AUTH_SCHEMA_VERSION))

    def get_access_token(self, force_refresh=False, rejected_token=None):
        self.migrate_settings()
        token = self._settings.get("access_token")
        if not force_refresh and self._usable(token):
            return token
        if not token and not self._settings.get("refresh_token"):
            raise LoginRequired("no access or refresh token")

        with self._refresh_lock:
            # Another Kodi plug-in process may have refreshed while this one
            # waited. Always re-read the persisted pair after taking the lock.
            current = self._settings.get("access_token")
            if rejected_token and current and current != rejected_token:
                if self._usable(current):
                    return current
            elif not force_refresh and self._usable(current):
                return current

            refresh_token = self._settings.get("refresh_token")
            provider = self._settings.get("provider")
            if not refresh_token:
                raise LoginRequired("refresh token missing")
            if not provider:
                raise LoginRequired("provider missing")

            if self._logger:
                self._logger.info(
                    "auth.refresh_started",
                    reason="http_401" if force_refresh else "token_expiry",
                )
            try:
                response = self._oauth.refresh(refresh_token, provider)
            except OAuthError as error:
                # A concurrently started process may have rotated the refresh
                # token just before this process acquired its filesystem lock.
                latest_refresh = self._settings.get("refresh_token")
                latest_access = self._settings.get("access_token")
                if (latest_refresh and latest_refresh != refresh_token
                        and self._usable(latest_access)):
                    if self._logger:
                        self._logger.info("auth.refresh_race_recovered")
                    return latest_access
                if error.error in (
                        "invalid_grant", "InvalidGrant", "invalid_token",
                        "InvalidToken", "InvalidCredentials",
                        "invalid_refresh_token"):
                    raise LoginExpired("refresh token rejected") from error
                raise AuthenticationError("token refresh failed") from error

            self.store_token_response(response, refresh_token)
            if self._logger:
                self._logger.info(
                    "auth.refresh_succeeded",
                    refresh_rotated=bool(
                        response.get("refresh_token")
                        and response.get("refresh_token") != refresh_token),
                )
            return response["access_token"]
