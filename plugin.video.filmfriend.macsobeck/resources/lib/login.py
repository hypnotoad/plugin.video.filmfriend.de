# -*- coding: utf-8 -*-
import re
import urllib.parse

import requests
import xbmcaddon
import xbmcgui

import resources.lib.external.libmediathek4utils as lm4utils
from resources.lib.api import ApiError
from resources.lib.auth import OAuthError
from resources.lib.kodi_runtime import build_runtime
from resources.lib.login_providers import select_supported_provider
from resources.lib.login_eduid import signInEduId

__addon__ = xbmcaddon.Addon()
__addonid__ = __addon__.getAddonInfo('id')
_settings, _logger, _oauth, _authentication, _api = build_runtime()

apiBase = 'https://api.tenant.frontend.vod.filmwerte.de'
client = 'filmwerte-vod-frontend'

commonHeaders = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36',
    'Upgrade-Insecure-Requests': '1',
    "Accept": 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'de, en;q=0.8, *;q=0.5',
}

countries = [
    { "code": "at", "displayName": lm4utils.getTranslation(30032), "libraryListId": "8bd3757f-bb3f-4ffe-9543-3424497ef47d" },
    { "code": "be", "displayName": lm4utils.getTranslation(30037), "libraryListId": "4a77619f-0d4a-48ad-bf45-5bb606d78be3" },
    { "code": "de", "displayName": lm4utils.getTranslation(30033), "libraryListId": "fba2f8b5-6a3a-4da3-b555-21613a88d3ef" },
    { "code": "ch", "displayName": lm4utils.getTranslation(30034), "libraryListId": "b9b657d4-48c4-4827-a257-d1b0b44a278a" },
    { "code": "fr", "displayName": lm4utils.getTranslation(30035), "libraryListId": "8737e70b-fc96-4512-900d-5983294a41dc" },
    { "code": "li", "displayName": lm4utils.getTranslation(30036), "libraryListId": "98c45053-c03a-4a40-9840-a97441ad3413" },
    { "code": "lu", "displayName": lm4utils.getTranslation(30038), "libraryListId": "84976d73-3277-452f-9d82-c89967118f7f" },
]

def pick():
    previousCountry = lm4utils.getSetting('country')
    previousLibrary = lm4utils.getSetting('library')
    _logger.debug(
        "login.picker_opened",
        has_previous_country=bool(previousCountry),
        has_previous_library=bool(previousLibrary),
    )
    # this only happens on first use after updating from v1.0.9 or earlier to v1.0.10 or later
    # up to v1.0.9 only Germany was supported and there was no country setting
    # so set country to de if it was empty but a library had already been selected
    if previousCountry == "" and not previousLibrary == "":
        previousCountry = "de"
        _logger.info("auth.legacy_country_defaulted", country="de")

    c = []
    cidx = -1
    for idx, country in enumerate(countries):
        c.append(xbmcgui.ListItem(country["displayName"]))
        if country["code"] == previousCountry:
            cidx = idx

    i = xbmcgui.Dialog().select(lm4utils.getTranslation(30031), c, preselect = cidx)

    if i == -1: # selection was canceled
        return

    country = countries[i]

    # get all supported libraries of the selected country
    try:
        j = _api.list_libraries(country["libraryListId"])
    except ApiError as error:
        _logger.error(
            "login.library_list_failed", status=error.status_code)
        lm4utils.displayMsg(
            lm4utils.getTranslation(30506),
            lm4utils.getTranslation(30507))
        return
    l = []
    cidx = -1
    for idx, item in enumerate(j['tenants']):
        l.append(xbmcgui.ListItem(f'{item["displayCategory"]} - {item["displayName"]}'))
        if item["displayName"] == previousLibrary:
            cidx = idx
            
    i = xbmcgui.Dialog().select(lm4utils.getTranslation(30010), l, preselect = cidx)
    if i == -1: # selection was canceled
        return

    domain = j['tenants'][int(i)]['clients']['web']['domain']
    tenant = j['tenants'][int(i)]['id']
    library = j['tenants'][int(i)]['displayName']
    _logger.info("login.library_selected", country=country["code"], tenant=tenant)

    # get information about the possible login providers of the selected library
    try:
        j = _api.sign_in_methods(tenant)
    except ApiError as error:
        _logger.error(
            "login.provider_discovery_failed", status=error.status_code)
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
        return

    selectedProvider = select_supported_provider(j)
    if selectedProvider is None:
        # no supported provider type was found -> show error
        lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30511))
        return
    providerType, providerKind, provider = selectedProvider

    if providerKind == 'OpenId':
        # ask for consent to grant access to the age rating during login
        ret = xbmcgui.Dialog().yesno(lm4utils.getTranslation(30514), lm4utils.getTranslation(30515),
                                     lm4utils.getTranslation(30516), lm4utils.getTranslation(30517))
        if not ret:
            return

    _logger.info(
        "login.provider_selected",
        provider_kind=providerKind,
        provider_type=providerType,
    )

    username = lm4utils.getSetting('username')
    password = lm4utils.getSetting('password')
    if not providerKind == "Ip":
        username = xbmcgui.Dialog().input(lm4utils.getTranslation(30500), defaultt=username)
        if username == '':
            lm4utils.displayMsg(lm4utils.getTranslation(30501), lm4utils.getTranslation(30502))
            return

        password = xbmcgui.Dialog().input(
            lm4utils.getTranslation(30503),
            defaultt=password,
            type=xbmcgui.INPUT_ALPHANUM,
            option=xbmcgui.ALPHANUM_HIDE_INPUT,
        )
        if password == '':
            lm4utils.displayMsg(lm4utils.getTranslation(30504), lm4utils.getTranslation(30505))
            return

    usernameEncoded = urllib.parse.quote_plus(username)
    passwordEncoded = urllib.parse.quote_plus(password)

    if providerType == 'delegated':
        # starting in v1.1.0 we switched from tenant specific client to general UI client
        # previous way stopped working after the Hamburg library switched their system and authentication
        headers = {
            **commonHeaders,
            "Content-Type": 'application/x-www-form-urlencoded',
        }
        try:
            j = _oauth.password_grant(
                username, password, provider, headers=headers)
        except OAuthError as error:
            j = {"error": error.error}
    else:
        session = requests.session()

        # VISIT API SIGN-IN PAGE
        authExternalUrl = f'{apiBase}/connect/authorize?client_id={client}&response_type=code&scope=offline_access&provider={provider}&redirect_uri=https://{domain}/de/sign-in/completed'
        headers = commonHeaders
        _logger.debug("login.external_authorize", url=authExternalUrl)
        response = session.get(
            authExternalUrl,
            headers=headers,
            allow_redirects=True,
            timeout=(5, 30),
        )
        loginFormUrl = response.url
        _logger.debug(
            "login.external_authorize_complete",
            status=response.status_code,
            url=loginFormUrl,
        )

        # check for SWITCH edu-ID libraries
        # those are redirected to login.eduid.ch, other "external" libraries to their own domain and '/oidcp/authorize'
        if 'eduid.ch' in response.url or 'execution=e1s' in response.url:
            # ---- SWITCH edu-ID / SLSKey (PURA) Shibboleth flow ----
            j = signInEduId(
                session, response, domain, username, password, _oauth)
            if j is None:
                return
        else:
            # LOGIN FORM
            parsedUrl = urllib.parse.urlparse(loginFormUrl)
            baseUrl = f'{parsedUrl.scheme}://{parsedUrl.hostname}'
            loginBaseUrl = f'{baseUrl}{parsedUrl.path}'
            _logger.debug("login.external_form_found", url=loginBaseUrl)

            # Find form action in <form action="MATCH" ...>
            match = re.search(r'<form[^>]*action="([^"]+)"', response.text)
            if match is None:
                _logger.warning("login.external_form_action_missing")
                lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
                return

            action_value = match.group(1)
            loginSubmitUrl = urllib.parse.urljoin(loginBaseUrl, action_value)

            formdata = f'L%23AUSW={usernameEncoded}&LPASSW={passwordEncoded}&LLOGIN=Anmelden'
            headers = {
                **commonHeaders,
                "Content-Type": 'application/x-www-form-urlencoded',
                'Origin': baseUrl,
                'Referer': loginFormUrl,
            }
            _logger.debug("login.external_credentials_submit", url=loginSubmitUrl)
            response = session.post(
                loginSubmitUrl,
                headers=headers,
                data=formdata,
                timeout=(5, 30),
            )
            _logger.debug(
                "login.external_credentials_complete",
                status=response.status_code,
                url=response.url,
            )

            ### TODO check for "Ausweisnummer unbekannt" or "Das angegebene Passwort ist falsch" for nice user info
            ### TODO finally stop if page after user/pass submission still contains e.g. the LPASSW form field
            ### TODO Error message is in <div class="hinweis fehler">...</div>

            # CONSENT FORM
            consentFormUrl = response.url
            parsedUrl = urllib.parse.urlparse(consentFormUrl)
            consentBaseUrl = f'{parsedUrl.scheme}://{parsedUrl.hostname}{parsedUrl.path}'
            _logger.debug("login.external_consent_found", url=consentBaseUrl)

            # Find form action in <form action="MATCH" ...>
            match = re.search(r'<form[^>]*action="([^"]+)"', response.text)
            if match is None:
                _logger.warning("login.external_consent_action_missing")
                lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
                return

            action_value = match.group(1)
            consentUrl = urllib.parse.urljoin(consentBaseUrl, action_value)

            formdata = 'CLOGIN=Zustimmen+und+fortfahren'
            headers = {
                **commonHeaders,
                "Content-Type": 'application/x-www-form-urlencoded',
                'Origin': baseUrl,
                'Referer': loginSubmitUrl,
            }
            _logger.debug("login.external_consent_submit", url=consentUrl)
            response = session.post(
                consentUrl,
                headers=headers,
                data=formdata,
                timeout=(5, 30),
            )
            _logger.debug(
                "login.external_consent_complete",
                status=response.status_code,
                url=response.url,
            )

            # GET BEARER TOKENS
            parsedUrl = urllib.parse.urlparse(response.url)
            completedUrl = f'{parsedUrl.scheme}://{parsedUrl.hostname}{parsedUrl.path}'
            # Extract 'code' from completion url query params
            code = urllib.parse.parse_qs(parsedUrl.query).get('code', [None])[0]
            if code is None:
                _logger.warning(
                    "login.external_authorization_code_missing",
                    url=response.url,
                )
                lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
                return

            headers = {
                **commonHeaders,
                "Content-Type": 'application/x-www-form-urlencoded',
                'Origin': baseUrl,
                'Referer': loginFormUrl,
            }
            try:
                j = _oauth.exchange_code(
                    code, completedUrl, headers=headers)
            except OAuthError as error:
                j = {"error": error.error}

    # common handling of the token response for every provider flow
    if 'error' in j:
        if j['error'] == 'InvalidCredentials':
            lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30508))
        elif j['error'] == 'Locked':
            lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30518))
        else:
            lm4utils.displayMsg(lm4utils.getTranslation(30506), lm4utils.getTranslation(30507))
        return

    lm4utils.setSetting('country', country["code"])
    lm4utils.setSetting('domain', domain)
    lm4utils.setSetting('tenant', tenant)
    lm4utils.setSetting('library', library)
    lm4utils.setSetting('username', username)
    lm4utils.setSetting('provider', provider)
    lm4utils.setSetting('provider_type', providerType)
    _authentication.store_token_response(j)
    _logger.info(
        "login.succeeded",
        provider_kind=providerKind,
        provider_type=providerType,
        tenant=tenant,
    )
