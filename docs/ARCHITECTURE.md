# Architecture and compatibility review

This review covers the complete `plugin.video.filmfriend.de` 1.3.0 source
snapshot and the reliability changes released through 1.4.1 of the independent
fork. The target is Kodi 21
Omega on LibreELEC with Python 3. The menu layout and navigation model are
deliberately unchanged.

The current package is an independent, macsobeck-maintained fork of
Ingo-FP-Angel's add-on. It was created to implement the authentication changes
required by Stadtbibliothek Stuttgart immediately. Historical attribution does
not create an update or maintenance relationship with the former repository.

## 1. Baseline architecture (1.3.0)

The add-on is a small router/parser design:

1. `default.py` subclasses the bundled `libmediathek4` compatibility layer. It
   maps Kodi query-string modes to menu, search, listing, and playback methods.
2. `resources/lib/jsonparser.py` combines Filmfriend HTTP calls, access-token
   refresh, response parsing, Kodi notifications, and creation of the media
   dictionary consumed by `libmediathek4`.
3. `resources/lib/login.py` owns the library picker and three sign-in variants.
   It also scrapes HTML for external OpenID providers.
4. `resources/lib/login_eduid.py` implements the SWITCH edu-ID/SLSKey
   Shibboleth sequence.
5. `resources/lib/external/libmediathek4.py` renders directories and turns the
   media dictionary into a Kodi `ListItem`.
6. `resources/settings.xml` is both user configuration and the token store.

There is no service process. Every directory action or playback action starts a
new Kodi Python plug-in process. Consequently, two actions can read and refresh
the same token pair concurrently.

## 2. Authentication flows

### Library and provider discovery

The picker first selects one of seven countries. Each country maps to a fixed
tenant-group/library-list UUID. It requests:

`GET https://api.tenant-group.frontend.vod.filmwerte.de/v7/{libraryListId}/sign-in`

The chosen tenant supplies its ID, display name, and web domain. Provider
discovery then requests:

`GET https://api.tenant.frontend.vod.filmwerte.de/v18/{tenant}/sign-in`

The first supported provider is selected in this fixed order:

1. `external` with `providerKind=OpenId`
2. `delegated` with no provider kind
3. `delegated` with `providerKind=Ip`

### Delegated password or IP grant

For a normal delegated provider, Kodi collects username and password and sends
an OAuth password grant to `/connect/token`. The IP provider uses the same grant
without prompting for credentials. Both request the `offline_access` scope so
Filmfriend can return a refresh token.

1.3.1 routes this request through `OAuthClient.password_grant()`. Passwords are
passed directly as form fields, never interpolated into diagnostics. The
password dialog hides input. The password is not persisted.

### External OpenID form flow

The add-on opens `/connect/authorize` with an authorization-code response type,
the selected provider, `offline_access`, and the tenant completion URL. It
follows redirects, scrapes the first HTML form action, submits the library
credentials, scrapes and submits the consent form, extracts `code` from the
final redirect, and exchanges it at `/connect/token`.

This is intentionally not redesigned in 1.3.1. The token exchange now uses the
testable OAuth client, all calls have finite connect/read timeouts, and logs
contain only stage, status, and redacted URL information.

### SWITCH edu-ID / SLSKey

When the authorization redirect points at edu-ID, the add-on drives the
Shibboleth form sequence:

`local-storage probe -> username -> password -> TOTP -> auto-submit/callback`

It extracts the authorization code and exchanges it using the same OAuth
client. 1.3.0 logged password character ordinals, the encoded password form
segment, form HTML, and callback material. 1.3.1 removes all of those
credential-bearing diagnostics.

## 3. Token persistence and migration

### Existing 1.3.0 persistence

Kodi add-on settings store:

- library metadata: `country`, `domain`, `tenant`, `library`
- sign-in metadata: `username`, `provider`, `provider_type`
- session material: `access_token`, `refresh_token`

The password setting is read for historical compatibility but is not declared
or written, so the add-on does not persist the password. Kodi stores the other
values in the add-on profile settings file. This is cleartext-at-rest storage;
LibreELEC has no generally available per-add-on OS credential vault.

### 1.3.1 migration

Migration is non-destructive and runs before token use:

- an existing library with no country is assigned `de`, matching the
  pre-1.0.10 Germany-only behavior;
- an existing provider with no `provider_type` is marked `legacy`; provider
  type is not required by the refresh grant;
- `token_expires_at` is inferred from the existing JWT when possible;
- `auth_schema_version=2` marks completion.

All old setting IDs remain valid. Existing access and refresh tokens are never
cleared by migration. A manual login is needed only when refresh metadata is
actually missing or Filmfriend rejects the stored refresh token.

Token pairs are still stored in Kodi settings for an in-place upgrade. A
rotated refresh token is written before the new access token. This order leaves
a recoverable session if Kodi or the device stops between writes.

## 4. Filmfriend API calls

| Purpose | Authentication | Endpoint |
|---|---:|---|
| Country library list | No | tenant-group frontend `/v7/{list}/sign-in` |
| Tenant providers | No | tenant frontend `/v18/{tenant}/sign-in` |
| OAuth authorize | Browser-like session | tenant frontend `/connect/authorize` |
| Password, code, refresh grants | Form grant | tenant frontend `/connect/token` |
| Search/listing | No | tenant frontend `/v18/{tenant}/search` |
| Series seasons | No | tenant frontend `/v18/{tenant}/series/{id}/seasons` |
| Season episodes | No | tenant frontend `/v18/{tenant}/seasons/{id}/episodes` |
| Genres | No | tenant frontend `/v18/{tenant}/genres` |
| Watchlist | Bearer | tenant frontend `/v18/{tenant}/watchlist` |
| Movie details | Bearer | tenant frontend `/v18/{tenant}/movies/{id}` |
| Episode details fallback | Bearer | tenant frontend `/v18/{tenant}/episodes/{id}` |
| Playback URI | Bearer | corresponding movie/episode `/{id}/uri` |

The old `parseMain()` navigation endpoint is dead code; the main menu is built
locally.

In 1.3.1, `FilmfriendApi` owns these calls. Authenticated requests obtain a
usable token from `AuthenticationService`. If Filmfriend returns 401, the
client forces one refresh and retries the original request once. A second 401
stops; it never enters an infinite retry loop.

1.3.2 retained the legacy public search path and added a bearer fallback. The
subsequent LibreELEC log proved that this assumption was wrong: refresh
succeeded, the rotated token was persisted, and the legacy search service still
returned 401. The error was therefore a retired catalogue contract, not an
expired login.

1.3.3 uses the same tenant API v18 as the current Filmfriend web client.
`FilmfriendApi` translates the existing menu query strings to v18 names
(`Video` to `Movie` or `Episode`, plural facet names to singular names, and
legacy category/genre/order parameters to their current equivalents). It maps
series and season navigation onto the dedicated child-resource endpoints and
wraps their arrays in the response shape already consumed by the Kodi parser.
The menu and routing UI remain unchanged.

Search and genres are deliberately anonymous, matching Filmfriend's public web
catalogue. Their failures now produce a generic API error and never trigger a
token refresh or “Login expired.” Watchlist, details, playback URI, and license
operations remain authenticated and retain the single refresh-and-retry rule.

## 5. Why “Login expired” recurred, and the fixes

1.3.0 only refreshed when its local, unverified JWT-expiry parser considered
the token expired. It did not refresh when Filmfriend invalidated a token early
or returned 401. The parser also used standard Base64 instead of URL-safe JWT
Base64 and had no clock-skew window.

More importantly, Kodi can run simultaneous plug-in processes. Two processes
could read the same expired access/refresh pair. If Filmfriend rotates refresh
tokens, the first refresh succeeds and the second submits the now-invalid old
refresh token, producing the misleading recurring expiry notification.

1.3.1 fixes this with:

- URL-safe JWT expiry decoding without `pyjwt`/`cryptography`;
- a 60-second refresh skew;
- an atomic profile-file lock around refresh;
- a second settings read after acquiring that lock;
- refresh-token rotation-safe persistence;
- recovery if another process has already persisted a newer valid pair;
- one forced refresh-and-retry after an authenticated 401;
- retention of the current refresh token if a valid response does not rotate it.

The 1.3.2 LibreELEC trace established a second, independent cause. It recorded
`auth.token_request_succeeded`, `auth.refresh_succeeded` with refresh-token
rotation, and then another 401 from only
`api.vod.filmwerte.de/api/v1/.../search`. The API layer classified that second
401 as `LoginExpired`, even though authentication had just succeeded.

1.3.3 removes the retired search service from the request path. Public
catalogue calls cannot ask for or refresh a token, while authenticated v18 calls
still refresh once on 401. If a refreshed token is rejected twice by an
authenticated endpoint, the exception now carries only that endpoint for
structured host/path diagnostics; it never carries a token or credentials.

## 6. Widevine playback flow

1. Kodi invokes `playVideo` with the Filmfriend video ID.
2. The API client checks movie details, then falls back to episode details on
   404, and rejects media whose state is not `Active`.
3. The authenticated `/{id}/uri` response supplies `mpegDash` and
   `widevineLicenseServerUri`.
4. `libmediathek4` creates an off-screen `ListItem` with the MPD URL, DASH MIME
   type, disabled content lookup, and `inputstream.adaptive`.
5. For Kodi 21, the item receives only
   `inputstream.adaptive.drm_legacy`, containing Widevine, the license URL, and
   an encoded octet-stream content type.
6. Kodi resolves the item and InputStream Adaptive obtains the license and
   passes decrypted samples to Kodi.

Version 1.3.3 set both `drm_legacy` and the old
`license_type`/`license_key` pair. InputStream Adaptive treats those as two
alternative DRM configuration interfaces and rejects their mixed use before
Widevine initialization. Version 1.3.4 uses the documented Kodi 21.5+ simple
interface exclusively. The old pair remains only in the isolated compatibility
branch for legacy media dictionaries that do not provide
`widevine_license_url`; the two interfaces are never emitted together.

The prior bitrate selector accidentally read license information from the last
loop variable instead of the selected stream. 1.3.1 tracks the selected media
entry explicitly.

On LibreELEC, `inputstream.adaptive` is not the Widevine CDM itself. The CDM
must be installed separately (normally through InputStream Helper) and must
support the device architecture.

## 7. Kodi 21 / LibreELEC compatibility risks

- External and edu-ID login depend on provider HTML, form names, redirect
  shapes, and a hard-coded `/de/sign-in/completed` URI. Provider changes can
  break these flows independently of the JSON API.
- The edu-ID implementation assumes a short, JavaScript-free Shibboleth
  sequence and mandatory TOTP. Additional challenges are not supported.
- Tokens and usernames are cleartext in Kodi's add-on settings. Logs are now
  redacted, but profile filesystem access still implies token access.
- The Widevine CDM is proprietary and external to the add-on. CDM availability,
  CPU architecture, HDCP, secure-decoder requirements, and license policy can
  still prevent playback on a particular LibreELEC device.
- `inputstream.adaptive.manifest_type` is deprecated in Kodi 21 and removed in
  Kodi 22. It is retained for early Omega compatibility. A Kodi 22 port should
  remove it and adopt the Kodi 22 `inputstream.adaptive.drm` JSON property.
- The declared minimum InputStream Adaptive version is historical. Omega ships
  a matching 21.x binary; installing an old binary manually is unsupported.
- The bundled `libmediathek4` copy uses older `ListItem.setInfo` and deprecated
  `addStreamInfo` conventions. They still work on Omega but should be migrated
  to `InfoTagVideo` in a separate UI/metadata change.
- Filmfriend's tenant API is not published as a stable third-party contract.
  The v18 version is pinned and isolated in `api.py`; a future upstream version
  change may require another parameter or response adapter.
- There are no provider-owned API specifications or sandbox credentials in the
  repository. Unit tests validate request/token behavior, not live Filmfriend,
  library-provider HTML, DRM licensing, or video decoding.

## 8. Resulting internal boundaries

- `api.py`: Filmfriend endpoint and authenticated retry policy.
- `auth.py`: OAuth grants, migration, expiry, locking, token rotation, storage.
- `diagnostics.py`: structured JSON events and recursive secret redaction.
- `kodi_runtime.py`: Kodi settings/log/profile adapters and service wiring.
- `playback.py`: Kodi 21 Widevine property construction.
- `login*.py`: existing UI and provider-specific interactive flows.
- `jsonparser.py`: media-to-Kodi parsing using the API client.
- `libmediathek4.py`: unchanged navigation renderer plus corrected playback
  selection and Omega DRM properties.

The API and authentication layers have no imports from `xbmc`, `xbmcaddon`,
`xbmcgui`, or `xbmcvfs`, which makes them directly unit-testable on CPython 3.

## 10. Independent local fork identity

Version 1.4.0 changes the active add-on ID to
`plugin.video.filmfriend.macsobeck` and the provider to `macsobeck`. Kodi
repository updates are matched by add-on ID, so a repository release for the
former `plugin.video.filmfriend.de` cannot update or replace this fork.

On its first start, while the former add-on remains installed, the Kodi adapter
copies non-empty library, provider, token, and language settings into empty
settings of the new fork. Passwords are not copied or persisted. The migration
logs only the number of copied settings and the public source add-on ID, never
setting values. After successful migration and playback verification, the
former add-on can be disabled or uninstalled.

Filmfriend API v17/v18 no longer returns `providerKind=OpenId` for Stuttgart's
external provider. It returns `preferIntegratedAuthentication=true` instead.
Version 1.4.1 normalizes both forms to the existing integrated external OpenID
flow while retaining the delegated and IP provider fallbacks. Unknown
non-integrated external flows remain rejected rather than sending credentials
to an unimplemented endpoint.

## 9. Compatibility references

- [InputStream Adaptive: Integration](https://github.com/xbmc/inputstream.adaptive/wiki/Integration)
  documents the Kodi 21 `manifest_type` deprecation and ListItem properties.
- [InputStream Adaptive: Integration DRM](https://github.com/xbmc/inputstream.adaptive/wiki/Integration-DRM)
  documents Widevine requirements, the old Omega properties, and
  `inputstream.adaptive.drm_legacy` for Kodi 21.
- [Kodi Python ListItem API](https://xbmc.github.io/docs.kodi.tv/master/kodi-dev-kit/group__python__xbmcgui__listitem.html)
  documents `inputstream`, MIME type, content lookup, and metadata APIs.
