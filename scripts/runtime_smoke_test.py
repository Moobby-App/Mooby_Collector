#!/usr/bin/env python3
"""Verify the restricted live role with a rolled-back disposable fixture."""

from __future__ import annotations

from pathlib import Path
import secrets
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from moobby.config import load_config  # noqa: E402
from moobby.redaction import configure_secrets, database_hint, safe_print  # noqa: E402

EXPECTED_HOST = "aws-0-ap-northeast-1.pooler.supabase.com"
EXPECTED_TARGET = "host=aws-0-ap-northeast-1.pooler.supabase.com; project_ref=vgy…ug"
EXPECTED_ROLE = "moobby_runtime"


def _expect_permission_denied(cursor, label: str, sql: str, params=None) -> bool:
    """Run a forbidden operation inside a savepoint and undo if it succeeds."""
    cursor.execute("SAVEPOINT moobby_permission_probe")
    try:
        cursor.execute(sql, params)
    except Exception as exc:
        import psycopg

        cursor.execute("ROLLBACK TO SAVEPOINT moobby_permission_probe")
        cursor.execute("RELEASE SAVEPOINT moobby_permission_probe")
        if isinstance(exc, psycopg.errors.InsufficientPrivilege):
            safe_print(f"{label}: denied as expected")
            return True
        raise
    else:
        cursor.execute("ROLLBACK TO SAVEPOINT moobby_permission_probe")
        cursor.execute("RELEASE SAVEPOINT moobby_permission_probe")
        safe_print(f"{label}: unexpectedly permitted (probe rolled back)")
        return False


def main() -> int:
    config = load_config(PROJECT_ROOT)
    configure_secrets(config.secret_values)
    if not config.database_url:
        safe_print("FAIL: DATABASE_URL is missing")
        return 2
    target = database_hint(config.database_url)
    if EXPECTED_HOST not in target or target != EXPECTED_TARGET:
        safe_print(f"FAIL: target mismatch ({target})")
        return 2

    try:
        import psycopg

        with psycopg.connect(
            config.database_url,
            sslmode="require",
            connect_timeout=5,
        ) as connection:
            if not connection.pgconn.ssl_in_use:
                safe_print("FAIL: client TLS is not active")
                return 1

            # All fixture writes stay in this transaction. Explicit rollback in
            # finally prevents persistent test rows even when a probe fails.
            passed = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT current_user, current_database(), current_setting('server_version'), "
                        "current_setting('transaction_read_only')"
                    )
                    user, database, version, read_only = cursor.fetchone()
                    if user != EXPECTED_ROLE or read_only != "off":
                        safe_print("FAIL: connection identity or transaction mode is unexpected")
                        return 1
                    cursor.execute(
                        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                        "rolreplication, rolbypassrls, rolinherit "
                        "FROM pg_roles WHERE rolname = current_user"
                    )
                    role_flags = cursor.fetchone()
                    if role_flags != (True, False, False, False, False, False, False):
                        safe_print("FAIL: runtime role attributes differ from the reviewed restricted profile")
                        return 1
                    cursor.execute(
                        "SELECT count(*) FROM pg_auth_members m "
                        "JOIN pg_roles member ON member.oid=m.member "
                        "WHERE member.rolname=current_user"
                    )
                    if cursor.fetchone()[0] != 0:
                        safe_print("FAIL: runtime role has unexpected memberships")
                        return 1
                    cursor.execute(
                        "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
                    )
                    if cursor.fetchone()[0]:
                        safe_print("FAIL: runtime role can create database objects administratively")
                        return 1

                    cursor.execute(
                        "SELECT nspname, has_schema_privilege(current_user, oid, 'USAGE'), "
                        "has_schema_privilege(current_user, oid, 'CREATE') "
                        "FROM pg_namespace WHERE nspname IN ('collection','processing','archive') "
                        "ORDER BY nspname"
                    )
                    schema_access = cursor.fetchall()
                    if schema_access != [
                        ("archive", True, False),
                        ("collection", True, False),
                        ("processing", True, False),
                    ]:
                        safe_print("FAIL: schema privileges differ from the reviewed profile")
                        return 1

                    cursor.execute(
                        "SELECT version FROM collection.schema_migrations ORDER BY version"
                    )
                    versions = [row[0] for row in cursor.fetchall()]
                    cursor.execute(
                        "SELECT source_id FROM collection.sources "
                        "WHERE platform='x' AND account_handle='commuterline' AND is_active"
                    )
                    source_rows = cursor.fetchall()
                    if versions != [1, 2] or len(source_rows) != 1:
                        safe_print("FAIL: expected schema ledger or monitored source is unavailable")
                        return 1

                    fixture_external_id = "moobby-smoke-" + secrets.token_hex(12)
                    cursor.execute(
                        "INSERT INTO collection.discovered_authors "
                        "(platform, external_author_id, account_handle, display_name) "
                        "VALUES ('x', %s, 'moobby_smoke', 'temporary smoke fixture') "
                        "RETURNING author_id",
                        (fixture_external_id,),
                    )
                    fixture_author_id = cursor.fetchone()[0]
                    cursor.execute(
                        "UPDATE collection.discovered_authors "
                        "SET display_name=%s, last_seen_at=now() WHERE author_id=%s",
                        ("updated temporary smoke fixture", fixture_author_id),
                    )
                    if cursor.rowcount != 1:
                        safe_print("FAIL: permitted fixture update did not affect one row")
                        passed = False
                    else:
                        safe_print("permitted SELECT/INSERT/column UPDATE: PASS")

                    denied_ddl = _expect_permission_denied(
                        cursor,
                        "schema DDL",
                        "CREATE TABLE collection.moobby_smoke_forbidden_"
                        + secrets.token_hex(6)
                        + " (id integer)",
                    )
                    denied_delete = _expect_permission_denied(
                        cursor,
                        "DELETE",
                        "DELETE FROM collection.discovered_authors WHERE author_id = %s",
                        (fixture_author_id,),
                    )
                    passed = passed and denied_ddl and denied_delete

                safe_print(
                    f"identity=moobby_runtime; database={database}; PostgreSQL={version}; "
                    f"TLS=on; schemas=collection,processing,archive; ledger=1,2"
                )
            finally:
                connection.rollback()

            safe_print("fixture transaction: rolled back; no test rows retained")
            return 0 if passed else 1
    except Exception as exc:
        safe_print(f"FAIL: runtime smoke test failed ({type(exc).__name__})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
