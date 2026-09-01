# SPDX-License-Identifier: GPL-2.0-only

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "plugin.video.filmfriend.macsobeck"))

from resources.lib.api import (  # noqa: E402
    ApiError,
    FilmfriendApi,
    translate_legacy_search_params,
)
from resources.lib.auth import LoginExpired  # noqa: E402
from tests.helpers import FakeSettings, Response  # noqa: E402


class Authentication:
    def __init__(self):
        self.calls = []

    def get_access_token(self, force_refresh=False, rejected_token=None):
        self.calls.append((force_refresh, rejected_token))
        return "new-access" if force_refresh else "old-access"


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class ApiTests(unittest.TestCase):
    def test_authenticated_401_refreshes_and_retries_once(self):
        authentication = Authentication()
        session = Session([
            Response(401, {}),
            Response(200, {"results": []}),
        ])
        api = FilmfriendApi(
            session, authentication, FakeSettings({"tenant": "tenant"}))

        result = api.watchlist("?take=1")

        self.assertEqual({"results": []}, result)
        self.assertEqual(
            [(False, None), (True, "old-access")],
            authentication.calls,
        )
        self.assertEqual(
            "Bearer old-access",
            session.calls[0][2]["headers"]["Authorization"],
        )
        self.assertEqual(
            "Bearer new-access",
            session.calls[1][2]["headers"]["Authorization"],
        )

    def test_second_401_is_login_expired_without_retry_loop(self):
        authentication = Authentication()
        session = Session([Response(401, {}), Response(401, {})])
        api = FilmfriendApi(
            session, authentication, FakeSettings({"tenant": "tenant"}))

        with self.assertRaises(LoginExpired) as raised:
            api.watchlist("?take=1")

        self.assertEqual(2, len(session.calls))
        self.assertIn("/watchlist", raised.exception.endpoint)

    def test_v18_tenant_search_does_not_request_a_token(self):
        authentication = Authentication()
        session = Session([Response(200, {"results": []})])
        api = FilmfriendApi(
            session, authentication, FakeSettings({"tenant": "tenant"}))

        api.search(
            "?search=Berlin&facets=Genres&kinds=Video"
            "&videoKinds=Movie&orderBy=EnglishOrder&take=1")

        self.assertEqual([], authentication.calls)
        self.assertNotIn(
            "Authorization", session.calls[0][2]["headers"])
        self.assertIn(
            "/v18/tenant/search?", session.calls[0][1])
        self.assertIn("mode=All", session.calls[0][1])
        self.assertIn("facets=Genre", session.calls[0][1])
        self.assertIn("kinds=Movie", session.calls[0][1])
        self.assertIn("orderBy=Title", session.calls[0][1])
        self.assertNotIn("videoKinds", session.calls[0][1])

    def test_public_catalogue_401_is_not_misreported_as_login_expired(self):
        authentication = Authentication()
        session = Session([Response(401, {})])
        api = FilmfriendApi(
            session, authentication, FakeSettings({"tenant": "tenant"}))

        with self.assertRaises(ApiError) as raised:
            api.search("?take=1")

        self.assertNotIsInstance(raised.exception, LoginExpired)
        self.assertEqual([], authentication.calls)
        self.assertNotIn(
            "Authorization", session.calls[0][2]["headers"])

    def test_series_navigation_uses_v18_seasons_resource(self):
        session = Session([Response(200, [{"id": "season-id"}])])
        api = FilmfriendApi(
            session, Authentication(), FakeSettings({"tenant": "tenant"}))

        result = api.search("?kinds=Season&series=series-id")

        self.assertEqual(
            {"results": [{
                "kind": "Season",
                "season": {"id": "season-id"},
            }]},
            result,
        )
        self.assertIn(
            "/v18/tenant/series/series-id/seasons",
            session.calls[0][1],
        )

    def test_season_navigation_uses_v18_episodes_resource(self):
        session = Session([Response(200, [{"id": "episode-id"}])])
        api = FilmfriendApi(
            session, Authentication(), FakeSettings({"tenant": "tenant"}))

        result = api.search("?kinds=Video&season=season-id")

        self.assertEqual(
            {"results": [{
                "kind": "Episode",
                "episode": {"id": "episode-id"},
            }]},
            result,
        )
        self.assertIn(
            "/v18/tenant/seasons/season-id/episodes",
            session.calls[0][1],
        )

    def test_search_translation_preserves_repeated_filters(self):
        query = translate_legacy_search_params(
            "?facets=Categories&facets=AudioLanguages"
            "&kinds=Video&kinds=Series&videoKinds=Movie"
            "&categories=category&genres=genre")

        self.assertIn("facets=Category", query)
        self.assertIn("facets=AudioLanguage", query)
        self.assertIn("kinds=Movie", query)
        self.assertIn("kinds=Series", query)
        self.assertIn("categoryIds=category", query)
        self.assertIn("genreIds=genre", query)


if __name__ == "__main__":
    unittest.main()
