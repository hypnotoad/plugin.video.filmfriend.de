# -*- coding: utf-8 -*-
import html
import re
import urllib.parse

import xbmcaddon
import xbmcgui

import resources.lib.external.libmediathek4utils as lm4utils
from resources.lib.auth import OAuthError
from resources.lib.kodi_runtime import build_logger

__addon__ = xbmcaddon.Addon()
__addonid__ = __addon__.getAddonInfo('id')
_logger = build_logger(__addon__)

# ===========================================
# SWITCH edu-ID / SLSKey (PURA) login helpers
# ===========================================
# edu-ID is a Shibboleth-based OIDC identity provider at login.eduid.ch.
# The login is a fixed sequence of plain HTML form POSTs with no JavaScript, no CSRF token and no PKCE.
# The only state carried between steps is the session cookie plus the "execution=e1sN" counter, followed automatically by requests:
#
#   e1s1 local-storage probe -> e1s2 username -> e1s3 password ->
#   e1s4 TOTP (2FA) -> e1s5 auto-submit form -> /connect/callback ->
#   .../sign-in/completed?code=... -> /connect/token (authorization_code)
#
# Because the token response includes a refresh_token under offline_access, the
# TOTP only has to be entered once per login; refreshes are headless afterwards.

def _eduid_hidden_inputs(pageHtml):
    """Return {name: value} for every <input> on the page (value '' if absent).
    Values are HTML-unescaped so entity-encoded fields resolve correctly."""
    fields = {}
    for tag in re.findall(r'<input\b[^>]*>', pageHtml, re.I):
        name = re.search(r'name="([^"]*)"', tag)
        if not name:
            continue
        val = re.search(r'value="([^"]*)"', tag)
        fields[name.group(1)] = (html.unescape(val.group(1)) if val else '')
    return fields


def _eduid_form_action(pageHtml, default):
    """Return the (HTML-unescaped) action of the first <form>, or `default`."""
    m = re.search(r'<form\b[^>]*\baction="([^"]*)"', pageHtml, re.I)
    return html.unescape(m.group(1)) if m else default


def _eduid_submit_field(pageHtml, default='_eventId_submit'):
    """edu-ID forms submit via a button named e.g. _eventId_submit or
    _eventId_proceed. Read the real one from the page instead of guessing."""
    m = re.search(r'<button[^>]*\bname="(_eventId_[A-Za-z]+)"', pageHtml, re.I)
    if m:
        return m.group(1)
    m = re.search(r'<input[^>]*\bname="(_eventId_[A-Za-z]+)"', pageHtml, re.I)
    return m.group(1) if m else default


def signInEduId(session, response, domain, username, password, oauth_client):
    """
    Drive the SWITCH edu-ID / SLSKey (PURA) Shibboleth login to completion.

    `session`  : the requests.Session already used for /connect/authorize
    `response` : the page we landed on after following the authorize redirects
                 (expected to be the first Shibboleth step, execution=e1s1)
    `domain`   : the tenant domain, e.g. 'bcufribourg.filmfriend.ch'
    `username` / `password` : edu-ID credentials already collected by pick()

    Returns the token dict {access_token, token_type, expires_in, refresh_token}
    on success, or None on failure (after showing an error dialog).
    """
    # Match the proven standalone flow exactly: pass only a Referer header per
    # POST and let requests handle Content-Type/encoding. Extra headers (Origin,
    # Sec-Fetch-*, hardcoded Content-Type) are what diverged from the working
    # script, so we drop them.

    # --- e1s1: local-storage probe. Claim success with an empty value so the
    #     IdP proceeds without a real browser. If edu-ID ever tightens this,
    #     the known fallback is to instead post shib_idp_ls_supported=false.
    fields = _eduid_hidden_inputs(response.text)
    for k in list(fields):
        if k.startswith('shib_idp_ls_success'):
            fields[k] = 'true'
    fields.setdefault('_eventId_proceed', '')
    target = urllib.parse.urljoin(response.url, _eduid_form_action(response.text, response.url))
    _logger.debug("login.eduid_step_submit", step="local_storage", url=target)
    response = session.post(
        target,
        headers={'Referer': response.url},
        data=fields,
        timeout=(5, 30),
    )
    _logger.debug(
        "login.eduid_step_complete",
        step="local_storage",
        status=response.status_code,
        url=response.url,
    )

    if 'e1s2' not in response.url:
        _logger.warning("login.eduid_unexpected_step", expected="username")
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
        return None

    # --- e1s2: username. Post the minimal field set, exactly like the
    #     reference flow (extra scraped hidden fields cause the IdP to reject).
    submitField = _eduid_submit_field(response.text)
    fields = {'j_username': username, submitField: ''}
    target = urllib.parse.urljoin(response.url, _eduid_form_action(response.text, response.url))
    _logger.debug("login.eduid_step_submit", step="username", url=target)
    response = session.post(
        target,
        headers={'Referer': response.url},
        data=fields,
        timeout=(5, 30),
    )
    _logger.debug(
        "login.eduid_step_complete",
        step="username",
        status=response.status_code,
        url=response.url,
    )

    if 'e1s3' not in response.url:
        # unknown account / username rejected
        _logger.warning("login.eduid_unexpected_step", expected="password")
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30508))
        return None

    # --- e1s3: password. Minimal field set (j_username + j_password + submit),
    #     matching the reference flow. Scraping/echoing extra hidden fields here
    #     makes edu-ID reject the password, so we keep it lean.
    submitField = _eduid_submit_field(response.text)
    fields = {'j_username': username, 'j_password': password, submitField: ''}
    target = urllib.parse.urljoin(response.url, _eduid_form_action(response.text, response.url))
    _logger.debug("login.eduid_step_submit", step="password", url=target)
    response = session.post(
        target,
        headers={'Referer': response.url},
        data=fields,
        timeout=(5, 30),
    )
    _logger.debug(
        "login.eduid_step_complete",
        step="password",
        status=response.status_code,
        url=response.url,
    )

    # edu-ID advances the execution counter even when it re-renders the
    # password form with an error, so the URL alone is not a reliable success
    # signal. Treat a page that still contains a j_password field as a rejected
    # password rather than a reached-OTP state.
    stillPassword = ('name="j_password"' in response.text or "name='j_password'" in response.text)
    hasOtp = ('name="j_otp"' in response.text or "name='j_otp'" in response.text)
    if stillPassword and not hasOtp:
        _logger.warning("login.eduid_credentials_rejected")
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30508))
        return None
    if not hasOtp:
        _logger.warning("login.eduid_unexpected_step", expected="otp")
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
        return None

    # --- e1s4: TOTP / 2FA. Ask only now, so a wrong password never burns a code.
    otp = xbmcgui.Dialog().input(lm4utils.getTranslation(30520))
    if otp == '':
        lm4utils.displayMsg(lm4utils.getTranslation(30521), lm4utils.getTranslation(30522))
        return None
    # --- e1s4: OTP. Minimal field set, matching the reference flow.
    submitField = _eduid_submit_field(response.text)
    fields = {'j_otp': otp.strip(), submitField: ''}
    target = urllib.parse.urljoin(response.url, _eduid_form_action(response.text, response.url))
    _logger.debug("login.eduid_step_submit", step="otp", url=target)
    response = session.post(
        target,
        headers={'Referer': response.url},
        data=fields,
        timeout=(5, 30),
    )
    _logger.debug(
        "login.eduid_step_complete",
        step="otp",
        status=response.status_code,
        url=response.url,
    )

    # --- After TOTP: edu-ID returns an auto-submitting form (the browser would
    #     run document.forms[0].submit()). It may be an execution=e1s5
    #     local-storage probe, or a direct self-submitting POST to
    #     /connect/callback carrying the code. Re-post whatever form we get,
    #     a few hops, until a ?code= appears in the URL.
    code = None
    for _ in range(4):
        code = urllib.parse.parse_qs(urllib.parse.urlparse(response.url).query).get('code', [None])[0]
        if code:
            break
        m = re.search(r'<form\b[^>]*\baction="([^"]*)"', response.text, re.I)
        if not m:
            break
        target = urllib.parse.urljoin(response.url, html.unescape(m.group(1)))
        fields = _eduid_hidden_inputs(response.text)
        for k in list(fields):
            if k.startswith('shib_idp_ls_success'):
                fields[k] = 'true'
        fields.setdefault('_eventId_proceed', '')
        _logger.debug("login.eduid_step_submit", step="callback", url=target)
        response = session.post(
            target,
            headers={'Referer': response.url},
            data=fields,
            timeout=(5, 30),
        )
        _logger.debug(
            "login.eduid_step_complete",
            step="callback",
            status=response.status_code,
            url=response.url,
        )

    if not code:
        # no code -> wrong/expired TOTP, or the IdP returned an error page
        _logger.warning(
            "login.eduid_authorization_code_missing",
            status=response.status_code,
        )
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30508))
        return None

    _logger.info("login.eduid_authorization_code_obtained")

    # --- Token exchange (authorization_code grant, public client, no secret).
    # NOTE: redirect_uri here MUST match the one sent to /connect/authorize.
    try:
        j = oauth_client.exchange_code(
            code,
            f'https://{domain}/de/sign-in/completed',
            session=session,
        )
    except OAuthError as error:
        _logger.warning(
            "login.eduid_token_exchange_failed",
            error=error.error,
            status=error.status_code,
        )
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
        return None

    if not j.get('access_token') or not j.get('refresh_token'):
        _logger.warning("login.eduid_token_response_incomplete")
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
        return None

    _logger.info("login.eduid_succeeded")
    return j
