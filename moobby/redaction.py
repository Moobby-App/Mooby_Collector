"""Central redaction and output helpers for secrets and credential-bearing text."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


_secrets: tuple[str, ...] = ()
_BEARER = re.compile(r"(?i)(\bBearer\s+)[^\s,;]+")
_AUTH = re.compile(r"(?i)(\bAuthorization\s*[:=]\s*)(?:Bearer\s+)?[^\s,;]+")
_COOKIE = re.compile(r"(?i)(\b(?:Set-Cookie|Cookie)\s*[:=]\s*)[^\r\n]+")
_API_KEY = re.compile(
    r"(?i)(\b(?:api[_-]?key|x-api-key|ORVIX_API_KEY)\s*[:=]\s*)(?:Bearer\s+)?[^\s,;]+"
)
_DATABASE_URI = re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql)://[^\s'\"<>]+")


def configure_secrets(values: tuple[str, ...] | list[str]) -> None:
    global _secrets
    _secrets = tuple(sorted({value for value in values if value}, key=len, reverse=True))


def redact(value: object) -> str:
    text = str(value)
    for secret in _secrets:
        text = text.replace(secret, "[REDACTED]")
    text = _DATABASE_URI.sub("[DATABASE_URL_REDACTED]", text)
    text = _AUTH.sub(r"\1[REDACTED]", text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _COOKIE.sub(r"\1[REDACTED]", text)
    text = _API_KEY.sub(r"\1[REDACTED]", text)
    return text


def safe_print(value: object = "") -> None:
    print(redact(value))


def database_hint(database_url: str | None) -> str:
    """Return a short target hint without credentials or the full database URI."""
    if not database_url:
        return "not configured"
    try:
        parsed = urlsplit(database_url)
        host = parsed.hostname or "unknown host"
        username = parsed.username or ""
        project_ref = username.partition(".")[2] if "." in username else ""
        if project_ref:
            ref_hint = project_ref[:3] + "…" + project_ref[-2:] if len(project_ref) > 5 else "***"
            return f"host={host}; project_ref={ref_hint}"
        return f"host={host}; database target masked"
    except ValueError:
        return "database target masked"
