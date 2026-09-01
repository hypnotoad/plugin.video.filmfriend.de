# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""Version-tolerant selection of Filmfriend sign-in providers."""


def select_supported_provider(sign_in_methods):
    """Return ``(type, kind, provider)`` or ``None`` when unsupported.

    API v11/v12 identified integrated external providers with
    ``providerKind=OpenId``. API v17/v18 removed that field and now exposes
    ``preferIntegratedAuthentication=true`` for the same flow.
    """
    for candidate in sign_in_methods.get("external", []) or []:
        if (candidate.get("providerKind") == "OpenId"
                or candidate.get("preferIntegratedAuthentication") is True):
            provider = candidate.get("provider")
            if provider:
                return "external", "OpenId", provider

    for supported_kind in (None, "Ip"):
        for candidate in sign_in_methods.get("delegated", []) or []:
            if candidate.get("providerKind") == supported_kind:
                provider = candidate.get("provider")
                if provider:
                    return "delegated", supported_kind, provider
    return None
