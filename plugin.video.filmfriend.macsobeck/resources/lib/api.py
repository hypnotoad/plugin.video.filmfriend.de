# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""Unit-testable Filmfriend HTTP API client."""

import urllib.parse

from resources.lib.auth import LoginExpired


TENANT_GROUP_API_BASE = "https://api.tenant-group.frontend.vod.filmwerte.de/v7"
TENANT_API_BASE = "https://api.tenant.frontend.vod.filmwerte.de/v18"

_FACET_NAMES = {
    "Categories": "Category",
    "Genres": "Genre",
    "GameSituations": "GameSituation",
    "AudioLanguages": "AudioLanguage",
    "AudioDescriptionLanguages": "AudioDescriptionLanguage",
    "SubtitleLanguages": "SubtitleLanguage",
    "ClosedCaptionLanguages": "ClosedCaptionLanguage",
}

_ORDER_NAMES = {
    "EnglishName": "Title",
    "EnglishOrder": "Title",
    "FrenchName": "Title",
    "GermanName": "Title",
    "ItalianName": "Title",
    "MonthlyImpressionScore": "ImpressionScore",
}


def translate_legacy_search_params(params):
    """Translate the pre-v18 Kodi query contract to Filmfriend API v18."""
    pairs = urllib.parse.parse_qsl(
        (params or "").lstrip("?"), keep_blank_values=False)
    values = {}
    for key, value in pairs:
        values.setdefault(key, []).append(value)

    translated = []
    if values.get("search"):
        translated.append(("mode", "All"))

    for key, value in pairs:
        if key == "facets":
            if value == "VideoKind":
                continue
            translated.append(("facets", _FACET_NAMES.get(value, value)))
        elif key in ("kinds", "videoKinds"):
            continue
        elif key == "categories":
            translated.append(("categoryIds", value))
        elif key == "genres":
            translated.append(("genreIds", value))
        elif key == "orderBy":
            translated.append(("orderBy", _ORDER_NAMES.get(value, value)))
        elif key in ("languageIsoCode", "series", "season"):
            continue
        else:
            translated.append((key, value))

    video_kinds = values.get("videoKinds", [])
    kinds = []
    for kind in values.get("kinds", []):
        if kind == "Video":
            mapped = "Movie" if "Movie" in video_kinds else "Episode"
        else:
            mapped = kind
        if mapped not in kinds:
            kinds.append(mapped)
    translated.extend(("kinds", kind) for kind in kinds)
    query = urllib.parse.urlencode(translated, doseq=True)
    return f"?{query}" if query else ""


class ApiError(RuntimeError):
    def __init__(self, status_code, endpoint):
        super().__init__(f"Filmfriend API request failed ({status_code})")
        self.status_code = status_code
        self.endpoint = endpoint


class NotFound(ApiError):
    pass


class FilmfriendApi:
    """Filmfriend endpoints with one authenticated 401 refresh-and-retry."""

    def __init__(self, session, authentication, settings, logger=None,
                 language="en", timeout=(5, 30)):
        self._session = session
        self._authentication = authentication
        self._settings = settings
        self._logger = logger
        self._language = language
        self._timeout = timeout

    def _send(self, method, url, headers, kwargs):
        try:
            return self._session.request(
                method, url, headers=headers, timeout=self._timeout, **kwargs)
        except Exception as error:
            if self._logger:
                self._logger.warning(
                    "api.network_error",
                    error_type=error.__class__.__name__,
                    method=method,
                    url=url,
                )
            raise ApiError(None, url) from error

    def _request_json(self, method, url, authenticated=False, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Accept-Language"] = self._language
        rejected_token = None
        if authenticated:
            rejected_token = self._authentication.get_access_token()
            headers["Authorization"] = f"Bearer {rejected_token}"

        if self._logger:
            self._logger.debug(
                "api.request",
                authenticated=authenticated,
                method=method,
                url=url,
            )
        response = self._send(method, url, headers, kwargs)

        if authenticated and response.status_code == 401:
            if self._logger:
                self._logger.info("api.unauthorized_retry", url=url)
            token = self._authentication.get_access_token(
                force_refresh=True, rejected_token=rejected_token)
            retry_headers = dict(headers)
            retry_headers["Authorization"] = f"Bearer {token}"
            response = self._send(method, url, retry_headers, kwargs)
            if response.status_code == 401:
                raise LoginExpired(
                    "access token rejected after refresh", endpoint=url)

        if response.status_code == 404:
            raise NotFound(404, url)
        if response.status_code < 200 or response.status_code >= 300:
            raise ApiError(response.status_code, url)
        try:
            return response.json()
        except (TypeError, ValueError) as error:
            raise ApiError(response.status_code, url) from error

    def list_libraries(self, library_list_id):
        return self._request_json(
            "GET", f"{TENANT_GROUP_API_BASE}/{library_list_id}/sign-in")

    def sign_in_methods(self, tenant):
        return self._request_json(
            "GET", f"{TENANT_API_BASE}/{tenant}/sign-in")

    def search(self, params):
        tenant = self._settings.get("tenant")
        values = urllib.parse.parse_qs(
            (params or "").lstrip("?"), keep_blank_values=False)

        # v18 exposes seasons and episodes through their parent resources
        # rather than the legacy search filters. Keep the Kodi navigation
        # contract stable by adapting those arrays to search result objects.
        if values.get("kinds") == ["Season"] and values.get("series"):
            seasons = self._request_json(
                "GET",
                f"{TENANT_API_BASE}/{tenant}/series/"
                f"{urllib.parse.quote(values['series'][0], safe='')}/seasons",
            )
            return {
                "results": [
                    {"kind": "Season", "season": season}
                    for season in seasons
                ],
            }
        if values.get("kinds") == ["Video"] and values.get("season"):
            episodes = self._request_json(
                "GET",
                f"{TENANT_API_BASE}/{tenant}/seasons/"
                f"{urllib.parse.quote(values['season'][0], safe='')}/episodes",
            )
            return {
                "results": [
                    {"kind": "Episode", "episode": episode}
                    for episode in episodes
                ],
            }

        return self._request_json(
            "GET",
            f"{TENANT_API_BASE}/{tenant}/search"
            f"{translate_legacy_search_params(params)}",
        )

    def genres(self, tenant=None):
        tenant = tenant or self._settings.get("tenant")
        return self._request_json(
            "GET", f"{TENANT_API_BASE}/{tenant}/genres")

    def watchlist(self, params, tenant=None):
        tenant = tenant or self._settings.get("tenant")
        return self._request_json(
            "GET", f"{TENANT_API_BASE}/{tenant}/watchlist{params}",
            authenticated=True)

    def media_details(self, media_type, video_id, tenant=None):
        tenant = tenant or self._settings.get("tenant")
        return self._request_json(
            "GET",
            f"{TENANT_API_BASE}/{tenant}/{media_type}/{video_id}",
            authenticated=True,
        )

    def media_uri(self, media_type, video_id, tenant=None):
        tenant = tenant or self._settings.get("tenant")
        return self._request_json(
            "GET",
            f"{TENANT_API_BASE}/{tenant}/{media_type}/{video_id}/uri",
            authenticated=True,
        )
