#!/usr/bin/env python3
"""Read-only PostgreSQL inventory for R0. This script never writes files."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from moobby.config import load_config  # noqa: E402
from moobby.redaction import configure_secrets, database_hint, safe_print  # noqa: E402


NON_SYSTEM_SCHEMAS_SQL = """
SELECT nspname
FROM pg_catalog.pg_namespace
WHERE nspname <> 'information_schema'
  AND nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
ORDER BY nspname
"""

TABLES_SQL = """
SELECT n.nspname, c.relname, c.reltuples::bigint AS approximate_rows,
       CASE c.relkind WHEN 'p' THEN 'partitioned table' ELSE 'table' END AS kind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname
"""

FOREIGN_KEYS_SQL = """
SELECT ns.nspname, rel.relname, con.conname,
       pg_catalog.pg_get_constraintdef(con.oid, true) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS rel ON rel.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns ON ns.oid = rel.relnamespace
WHERE con.contype = 'f'
  AND ns.nspname <> 'information_schema'
  AND ns.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
ORDER BY ns.nspname, rel.relname, con.conname
"""

VIEWS_SQL = """
SELECT n.nspname, c.relname,
       CASE c.relkind WHEN 'm' THEN 'materialized view' ELSE 'view' END AS kind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
  AND c.relkind IN ('v', 'm')
ORDER BY n.nspname, c.relname
"""

FUNCTIONS_SQL = """
SELECT n.nspname, p.proname,
       pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
       pg_catalog.pg_get_function_result(p.oid) AS result,
       l.lanname AS language
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language AS l ON l.oid = p.prolang
WHERE n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
ORDER BY n.nspname, p.proname, arguments
"""

ROLES_SQL = """
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin,
       rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
ORDER BY rolname
"""

ROLE_MEMBERSHIPS_SQL = """
SELECT member_role.rolname AS member, granted_role.rolname AS granted_role,
       membership.admin_option
FROM pg_catalog.pg_auth_members AS membership
JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = membership.member
JOIN pg_catalog.pg_roles AS granted_role ON granted_role.oid = membership.roleid
ORDER BY member_role.rolname, granted_role.rolname
"""

SCHEMA_GRANTS_SQL = """
SELECT n.nspname,
       CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
            ELSE pg_catalog.pg_get_userbyid(acl.grantee) END AS grantee,
       pg_catalog.pg_get_userbyid(acl.grantor) AS grantor,
       acl.privilege_type, acl.is_grantable
FROM pg_catalog.pg_namespace AS n
CROSS JOIN LATERAL pg_catalog.aclexplode(
    COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
) AS acl
WHERE n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
ORDER BY n.nspname, grantee, acl.privilege_type
"""

TABLE_GRANTS_SQL = """
SELECT table_schema, table_name, grantee, privilege_type, is_grantable
FROM information_schema.table_privileges
WHERE table_schema <> 'information_schema'
  AND table_schema NOT LIKE 'pg\\_%' ESCAPE '\\'
ORDER BY table_schema, table_name, grantee, privilege_type
"""

RLS_SQL = """
SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname
"""

POLICIES_SQL = """
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_catalog.pg_policies
WHERE schemaname <> 'information_schema'
  AND schemaname NOT LIKE 'pg\\_%' ESCAPE '\\'
ORDER BY schemaname, tablename, policyname
"""


def fetch_all(cursor: Any, sql: str) -> list[tuple[Any, ...]]:
    cursor.execute(sql)
    return cursor.fetchall()


def render_section(title: str, headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    safe_print(f"\n## {title} ({len(rows)})")
    if not rows:
        safe_print("(none)")
        return
    safe_print(" | ".join(headers))
    for row in rows:
        safe_print(" | ".join("NULL" if item is None else str(item) for item in row))


def main() -> int:
    config = load_config(PROJECT_ROOT)
    configure_secrets(config.secret_values)
    safe_print("Moobby database inventory — read-only draft")
    safe_print(f"Target: {database_hint(config.database_url)}")
    if not config.database_url:
        safe_print("FAIL: DATABASE_URL is missing")
        return 2

    try:
        import psycopg
    except ImportError:
        safe_print("FAIL: required dependency 'psycopg' is not importable")
        return 2

    try:
        # The server starts each transaction read-only; this script issues SELECTs only.
        with psycopg.connect(
            config.database_url,
            sslmode="require",
            connect_timeout=5,
            options="-c default_transaction_read_only=on",
        ) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_setting('transaction_read_only')")
                    read_only = cursor.fetchone()[0]
                    if read_only != "on":
                        safe_print("FAIL: server did not confirm a read-only transaction")
                        return 1

                    sections = (
                        ("Non-system schemas", ("schema",), fetch_all(cursor, NON_SYSTEM_SCHEMAS_SQL)),
                        ("Tables (approximate row estimates)", ("schema", "table", "approx_rows", "kind"), fetch_all(cursor, TABLES_SQL)),
                        ("Foreign keys", ("schema", "table", "constraint", "definition"), fetch_all(cursor, FOREIGN_KEYS_SQL)),
                        ("Views", ("schema", "view", "kind"), fetch_all(cursor, VIEWS_SQL)),
                        ("Functions", ("schema", "function", "arguments", "result", "language"), fetch_all(cursor, FUNCTIONS_SQL)),
                        ("Roles", ("role", "superuser", "create_db", "create_role", "login", "replication", "bypass_rls"), fetch_all(cursor, ROLES_SQL)),
                        ("Role memberships", ("member", "granted_role", "admin_option"), fetch_all(cursor, ROLE_MEMBERSHIPS_SQL)),
                        ("Non-system schema grants", ("schema", "grantee", "grantor", "privilege", "grantable"), fetch_all(cursor, SCHEMA_GRANTS_SQL)),
                        ("Non-system table grants", ("schema", "table", "grantee", "privilege", "grantable"), fetch_all(cursor, TABLE_GRANTS_SQL)),
                        ("Row-level security", ("schema", "table", "rls_enabled", "rls_forced"), fetch_all(cursor, RLS_SQL)),
                        ("Policies", ("schema", "table", "policy", "permissive", "roles", "command", "using", "with_check"), fetch_all(cursor, POLICIES_SQL)),
                    )
                    safe_print("Transaction: read-only confirmed")
                    for title, headers, rows in sections:
                        render_section(title, headers, rows)
        return 0
    except Exception as exc:
        safe_print(f"FAIL: inventory query failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
