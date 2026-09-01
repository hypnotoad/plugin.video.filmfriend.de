# Filmfriend for Kodi - macsobeck local fork

This is an independent maintenance fork of Ingo-FP-Angel's
`plugin.video.filmfriend.de`. It was created so that authentication changes
required by Stadtbibliothek Stuttgart could be handled immediately, without
waiting for another upstream release. The fork is maintained by macsobeck and
uses a separate add-on ID and release path.

## General information

A plugin for KODI to play shows and movies from the filmfriend streaming portal for public libraries in several European countries.

You need an account with a public library in order to access this service.

Supported countries are Germany, Austria, Switzerland, Liechtenstein, Belgium, Luxembourg, and France.

Available languages for the user interface are German and English.

## Install the add-on

This independent fork is distributed only as a local ZIP. Its add-on ID is
`plugin.video.filmfriend.macsobeck`, so repositories containing
`plugin.video.filmfriend.de` cannot update or replace it.

Source code and releases are published at
https://github.com/macsobeck/plugin.video.filmfriend.macsobeck.

Install the ZIP locally, start it once to migrate existing settings from
`plugin.video.filmfriend.de`, verify playback, and then disable or uninstall the
former add-on. Do not uninstall the former add-on before the first start if you
want its settings and tokens migrated automatically.

## Using the addon

Make sure you've installed the Widevine CDM library (e.g. from the settings of the "InputStream Helper" addon).

Before playing videos or accessing your personal watchlist, please use the "Login" function in the settings of this addon.

## History and licensing

This add-on is free for everyone to use for any purpose, study, modify, and
share under the GNU General Public License version 2 only (`GPL-2.0-only`). If
you distribute it or a modified version, you must keep it under that license
and make the corresponding source code available. See `LICENSE-NOTICE.md` for
a plain-language summary and `LICENSE.txt` for the controlling license text.

Maintained by macsobeck as an independent GPL-2.0-only fork of the add-on by
Ingo-FP-Angel. This fork was created to respond immediately to the provider
changes affecting Stadtbibliothek Stuttgart. The earlier community add-on was
itself forked from v1.0.0 of
https://github.com/xbmc/repo-plugins/tree/matrix/plugin.video.filmfriend by
sarbes. Historical attribution is retained; it does not imply active ownership
or an update relationship.

## Development

The architecture, authentication/token lifecycle, Filmfriend endpoints,
Widevine playback path, migration behavior, and Kodi 21/LibreELEC risks are
documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

The API, authentication, diagnostics, and playback-property tests run without
Kodi:

```sh
python3 -m unittest discover -s tests -v
```
