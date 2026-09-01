# SPDX-License-Identifier: GPL-2.0-only

import base64
import json


def jwt(expiry, marker="token"):
    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode({'exp': expiry, 'm': marker})}.signature"


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.writes = []

    def get(self, key):
        return self.values.get(key, "")

    def set(self, key, value):
        value = str(value)
        self.values[key] = value
        self.writes.append((key, value))
        return True


class FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class Response:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body
