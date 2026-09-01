# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
"""Small structured logger with mandatory credential redaction."""

import json
import re
import time
import urllib.parse


_SECRET_KEYS = {
    "access_token",
    "authorization",
    "code",
    "cookie",
    "j_otp",
    "j_password",
    "otp",
    "password",
    "refresh_token",
    "samlresponse",
    "set_cookie",
}
_FORM_SECRET_RE = re.compile(
    r"(?i)(access_token|authorization|code|cookie|j_otp|j_password|otp|"
    r"password|refresh_token|samlresponse)=([^&\s]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_RE = re.compile(
    r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)


def _is_secret_key(key):
    normalized = str(key).lower().replace("-", "_")
    return normalized in _SECRET_KEYS or normalized.endswith("_token")


def redact_url(value):
    """Remove sensitive query values while retaining useful endpoint context."""
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https"):
            return value
        query = []
        for key, item_value in urllib.parse.parse_qsl(
                parsed.query, keep_blank_values=True):
            query.append((key, "<redacted>" if _is_secret_key(key) else item_value))
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path,
             urllib.parse.urlencode(query), ""))
    except (TypeError, ValueError):
        return value


def redact(value, key=None):
    """Recursively redact fields that could contain authentication material."""
    if key is not None and _is_secret_key(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = redact_url(value)
        value = _BEARER_RE.sub("Bearer <redacted>", value)
        value = _FORM_SECRET_RE.sub(lambda m: f"{m.group(1)}=<redacted>", value)
        return _JWT_RE.sub("<redacted-token>", value)
    return value


class StructuredLogger:
    """Emit one JSON object per Kodi log line.

    The sink is injected so this class can be unit-tested without importing
    Kodi. A sink receives ``(message, level)``.
    """

    def __init__(self, sink, addon_id="plugin.video.filmfriend.macsobeck",
                 clock=None):
        self._sink = sink
        self._addon_id = addon_id
        self._clock = clock or time.time

    def _write(self, level, event, **fields):
        record = {
            "addon": self._addon_id,
            "event": str(event),
            "level": level,
            "ts": int(self._clock()),
        }
        record.update(redact(fields))
        self._sink(json.dumps(record, sort_keys=True, separators=(",", ":")), level)

    def debug(self, event, **fields):
        self._write("debug", event, **fields)

    def info(self, event, **fields):
        self._write("info", event, **fields)

    def warning(self, event, **fields):
        self._write("warning", event, **fields)

    def error(self, event, **fields):
        self._write("error", event, **fields)
