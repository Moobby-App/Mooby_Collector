"""Read-only local environment checks for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import sys

from moobby.config import Config
from moobby.redaction import database_hint, redact


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    reason: str


def run_preflight(config: Config) -> list[CheckResult]:
    checks = [_runtime_check()]
    checks.append(_configuration_check(config))
    checks.append(_database_check(config))
    checks.append(_session_check(config))
    checks.append(_orvix_check(config))
    return checks


def _runtime_check() -> CheckResult:
    version = sys.version_info
    dependency_errors: list[str] = []
    for module in ("dotenv", "psycopg"):
        try:
            __import__(module)
        except ImportError:
            dependency_errors.append(module)
    if version < (3, 10):
        return CheckResult("runtime", CheckStatus.FAIL, f"Python {version.major}.{version.minor} is unsupported; use Python 3.10 or newer")
    if dependency_errors:
        return CheckResult("runtime", CheckStatus.FAIL, "missing import(s): " + ", ".join(dependency_errors))
    return CheckResult("runtime", CheckStatus.PASS, f"Python {version.major}.{version.minor}; required imports available")


def _configuration_check(config: Config) -> CheckResult:
    missing = config.missing_keys
    if missing:
        return CheckResult("configuration", CheckStatus.FAIL, "missing required environment variable(s): " + ", ".join(missing))
    return CheckResult("configuration", CheckStatus.PASS, "required environment variables are set")


def _database_check(config: Config) -> CheckResult:
    if not config.database_url:
        return CheckResult("database", CheckStatus.WARN, "not checked; DATABASE_URL is missing")
    target = database_hint(config.database_url)
    try:
        import psycopg

        with psycopg.connect(
            config.database_url,
            sslmode="require",
            connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.execute("SELECT current_user")
                current_user = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = %s)",
                    ("collection",),
                )
                collection_exists = bool(cursor.fetchone()[0])
        detail = f"target {target}; connected as {redact(current_user)}; SELECT 1 passed"
        if collection_exists:
            return CheckResult("database", CheckStatus.PASS, detail + "; collection schema exists")
        return CheckResult("database", CheckStatus.WARN, detail + "; collection schema not initialized yet")
    except Exception as exc:
        return CheckResult("database", CheckStatus.FAIL, f"target {target}; connection/check failed: {redact(exc)}")


def _session_check(config: Config) -> CheckResult:
    path = config.x_session_path
    if path is None:
        return _auth_required("X_SESSION_PATH is missing")
    if not path.is_absolute():
        path = config.project_root / path
    try:
        metadata = path.stat()
        if not path.is_file() or metadata.st_size <= 0:
            return _auth_required("session file is missing or empty")
        with path.open("rb") as session_file:
            session_file.read(1)
        age_seconds = max(0, (datetime.now(timezone.utc).timestamp() - metadata.st_mtime))
        age_days = age_seconds / 86400
        return CheckResult("X session", CheckStatus.PASS, f"file is readable and non-empty; age {age_days:.1f} days")
    except (OSError, ValueError):
        return _auth_required("session file is missing or unusable")


def _auth_required(reason: str) -> CheckResult:
    return CheckResult(
        "X session",
        CheckStatus.WARN,
        f"auth_required: {reason}; log in manually once, then rerun preflight",
    )


def _orvix_check(config: Config) -> CheckResult:
    missing = [name for name, value in (("ORVIX_API_KEY", config.orvix_api_key), ("ORVIX_MODEL", config.orvix_model)) if not value]
    if missing:
        return CheckResult("Orvix", CheckStatus.FAIL, "missing environment variable(s): " + ", ".join(missing) + "; API not called")
    return CheckResult("Orvix", CheckStatus.PASS, "API key and model are set; API not called")
