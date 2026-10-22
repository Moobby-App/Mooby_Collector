"""Isolated PostgreSQL integration tests for the SQL migration drafts.

The fixture starts a temporary Unix-socket-only cluster. It never reads .env or
DATABASE_URL and skips when PostgreSQL server binaries are unavailable.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import json
import os

import psycopg
from psycopg import sql
import pytest

from moobby.migration_ledger import (
    MigrationDriftError,
    MigrationFile,
    pending_migrations,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILES = [
    MigrationFile(1, "0001_collection_processing_archive", ROOT / "migrations/0001_collection_processing_archive.sql"),
    MigrationFile(2, "0002_runtime_role_and_grants", ROOT / "migrations/0002_runtime_role_and_grants.sql"),
]


def _pg_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(Path("/opt/homebrew/opt").glob(f"postgresql*/bin/{name}"))
    return str(candidates[-1]) if candidates else None


def _relation_counts(conn):
    tables = [
        (schema, table)
        for schema, table in conn.execute(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname IN ('collection','processing','archive') "
            "ORDER BY schemaname, tablename"
        ).fetchall()
    ]
    counts = {}
    for schema, table in tables:
        # Names are read from PostgreSQL's catalogs, then quoted as identifiers.
        counts[f"{schema}.{table}"] = conn.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        ).fetchone()[0]
    return counts


@pytest.fixture(scope="module")
def rehearsal_db():
    initdb = _pg_tool("initdb")
    pg_ctl = _pg_tool("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("PostgreSQL initdb/pg_ctl are not installed")

    temp_root = Path(tempfile.mkdtemp(prefix="moobby-pg-rehearsal-", ))
    data_dir = temp_root / "data"
    socket_dir = temp_root / "socket"
    socket_dir.mkdir(mode=0o700)
    try:
        subprocess.run(
            [initdb, "-D", str(data_dir), "-U", "postgres", "--no-locale", "-E", "UTF8", "--auth-local=trust", "--auth-host=reject"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [pg_ctl, "-D", str(data_dir), "-l", str(temp_root / "postgres.log"), "-o",
             f"-F -c listen_addresses='' -c unix_socket_directories='{socket_dir}' -c unix_socket_permissions=0700", "start"],
            check=True,
            capture_output=True,
            text=True,
        )
        with psycopg.connect(dbname="postgres", user="postgres", host=str(socket_dir), autocommit=True) as conn:
            conn.execute("CREATE ROLE anon NOLOGIN")
            conn.execute("CREATE ROLE authenticated NOLOGIN")
            for migration in MIGRATION_FILES:
                with conn.transaction():
                    conn.execute(migration.path.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT INTO collection.schema_migrations (version, name, checksum_sha256) VALUES (%s, %s, %s)",
                        (migration.version, migration.name, migration.checksum_sha256),
                    )
            yield conn, socket_dir
    finally:
        subprocess.run([pg_ctl, "-D", str(data_dir), "-m", "fast", "stop"], capture_output=True, text=True)
        shutil.rmtree(socket_dir, ignore_errors=True)
        shutil.rmtree(temp_root, ignore_errors=True)


def _reject(conn, error_type, sql, params=None):
    with pytest.raises(error_type):
        with conn.transaction():
            conn.execute(sql, params)


def test_rehearsal_migrations_constraints_grants_and_rls(rehearsal_db):
    admin, socket_dir = rehearsal_db
    version = admin.execute("SHOW server_version").fetchone()[0]
    assert version
    expected_version = os.environ.get("MOOBBY_EXPECT_PG_VERSION")
    if expected_version:
        assert version.startswith(expected_version), (
            f"temporary PostgreSQL server is {version}; expected {expected_version}"
        )
    assert admin.execute("SELECT count(*) FROM collection.schema_migrations").fetchone()[0] == 2
    assert admin.execute("SELECT count(*) FROM collection.sources WHERE platform='x' AND account_handle='commuterline'").fetchone()[0] == 1

    runtime_flags = admin.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolinherit FROM pg_roles WHERE rolname='moobby_runtime'"
    ).fetchone()
    assert runtime_flags == (False, False, False, False, False)
    assert admin.execute("SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname='moobby_runtime'").fetchone()[0] == 0
    assert admin.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('collection','processing','archive') AND c.relkind IN ('r','p') AND NOT c.relrowsecurity").fetchone()[0] == 0
    assert admin.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('collection','processing','archive') AND c.relkind IN ('r','p')").fetchone()[0] == 13
    assert admin.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_roles r ON r.oid=c.relowner "
        "WHERE n.nspname IN ('collection','processing','archive') AND c.relkind IN ('r','p') AND r.rolname='postgres'"
    ).fetchone()[0] == 13
    assert admin.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_roles r ON r.oid=c.relowner "
        "WHERE n.nspname IN ('collection','processing','archive') AND c.relkind IN ('r','p') AND r.rolname='moobby_runtime'"
    ).fetchone()[0] == 0
    assert admin.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='processing' AND indexname='llm_attempts_one_success_per_job'").fetchone()[0].endswith("WHERE is_success")

    run_id = uuid.uuid4()
    source_id = admin.execute("SELECT source_id FROM collection.sources WHERE account_handle='commuterline'").fetchone()[0]
    now = admin.execute("SELECT now()").fetchone()[0]
    admin.execute(
        "INSERT INTO collection.collection_runs (run_id, collector_version, method, collection_mode, profile_source_id, status, started_at) VALUES (%s,'test','profile','live',%s,'running',%s)",
        (run_id, source_id, now),
    )
    content_id = admin.execute(
        "INSERT INTO collection.raw_contents (platform, external_id) VALUES ('x','fixture-1') RETURNING content_id"
    ).fetchone()[0]
    snapshot_id = admin.execute(
        "INSERT INTO collection.raw_snapshots (content_id,capture_hash,raw_text,time_quality,text_quality,media_quality) VALUES (%s,%s,'fixture','missing','complete','not_checked') RETURNING snapshot_id",
        (content_id, "a" * 64),
    ).fetchone()[0]
    admin.execute(
        "INSERT INTO collection.content_observations (run_id,content_id,snapshot_id) VALUES (%s,%s,%s)",
        (run_id, content_id, snapshot_id),
    )
    _reject(admin, psycopg.errors.UniqueViolation,
            "INSERT INTO collection.raw_contents (platform,external_id) VALUES ('x','fixture-1')")
    other_content_id = admin.execute(
        "INSERT INTO collection.raw_contents (platform,external_id) VALUES ('x','fixture-2') RETURNING content_id"
    ).fetchone()[0]
    _reject(admin, psycopg.errors.ForeignKeyViolation,
            "INSERT INTO collection.content_observations (run_id,content_id,snapshot_id) VALUES (%s,%s,%s)",
            (run_id, other_content_id, snapshot_id))

    job_id = admin.execute(
        "INSERT INTO processing.processing_jobs (snapshot_id,pipeline_version,status) VALUES (%s,'v1','queued') RETURNING job_id",
        (snapshot_id,),
    ).fetchone()[0]
    _reject(admin, psycopg.errors.UniqueViolation,
            "INSERT INTO processing.processing_jobs (snapshot_id,pipeline_version,status) VALUES (%s,'v1','queued')",
            (snapshot_id,))
    _reject(admin, psycopg.errors.CheckViolation,
            "INSERT INTO processing.processing_jobs (snapshot_id,pipeline_version,status) VALUES (%s,'v2','processing')",
            (snapshot_id,))
    admin.execute(
        "INSERT INTO processing.llm_attempts (job_id,attempt_number,model,prompt_version,contract_version,request_csv,validation_result,input_tokens,output_tokens,is_success) VALUES (%s,1,'test','p1','c1','csv','valid',NULL,NULL,true)",
        (job_id,),
    )
    _reject(admin, psycopg.errors.UniqueViolation,
            "INSERT INTO processing.llm_attempts (job_id,attempt_number,model,prompt_version,contract_version,request_csv,validation_result,is_success) VALUES (%s,2,'test','p1','c1','csv','valid',true)",
            (job_id,))
    assert admin.execute("SELECT input_tokens,output_tokens FROM processing.llm_attempts WHERE job_id=%s", (job_id,)).fetchone() == (None, None)

    admin.execute("INSERT INTO archive.run_receipts (run_id,batch_digest) VALUES (%s,%s)", (run_id, "b" * 64))
    _reject(admin, psycopg.errors.UniqueViolation,
            "INSERT INTO archive.run_receipts (run_id,batch_digest) VALUES (%s,%s)", (run_id, "c" * 64))
    _reject(admin, psycopg.errors.CheckViolation,
            "INSERT INTO archive.export_batches (batch_id,status,schema_version) VALUES (%s,'verified',1)", (uuid.uuid4(),))
    batch_id = uuid.uuid4()
    admin.execute("INSERT INTO archive.export_batches (batch_id,status,schema_version) VALUES (%s,'prepared',1)", (batch_id,))
    admin.execute("INSERT INTO archive.export_items (batch_id,job_id,item_status) VALUES (%s,%s,'prepared')", (batch_id,job_id))
    _reject(admin, psycopg.errors.UniqueViolation,
            "INSERT INTO archive.export_items (batch_id,job_id,item_status) VALUES (%s,%s,'prepared')", (batch_id,job_id))
    _reject(admin, psycopg.errors.CheckViolation,
            "UPDATE archive.export_batches SET status='purged' WHERE batch_id=%s", (batch_id,))

    with psycopg.connect(dbname="postgres", user="moobby_runtime", host=str(socket_dir), autocommit=True) as runtime:
        assert runtime.execute("SELECT count(*) FROM collection.sources").fetchone()[0] == 1
        runtime.execute("INSERT INTO collection.discovered_authors (platform,external_author_id) VALUES ('x','runtime-fixture')")
        assert runtime.execute("SELECT count(*) FROM collection.discovered_authors WHERE external_author_id='runtime-fixture'").fetchone()[0] == 1
        _reject(runtime, psycopg.errors.InsufficientPrivilege,
                "UPDATE collection.raw_snapshots SET raw_text='changed' WHERE snapshot_id=%s", (snapshot_id,))
        _reject(runtime, psycopg.errors.InsufficientPrivilege,
                "DELETE FROM collection.raw_snapshots WHERE snapshot_id=%s", (snapshot_id,))
        _reject(runtime, psycopg.errors.InsufficientPrivilege,
                "CREATE TABLE collection.not_allowed(id integer)")
        _reject(runtime, psycopg.errors.InsufficientPrivilege,
                "CREATE ROLE not_allowed")

    for api_role in ("anon", "authenticated"):
        with admin.transaction():
            admin.execute(f"SET LOCAL ROLE {api_role}")
            _reject(admin, psycopg.errors.InsufficientPrivilege, "SELECT * FROM collection.sources")
            admin.execute("RESET ROLE")


def test_migration_ledger_rejects_changed_files_and_duplicate_versions(rehearsal_db, tmp_path):
    admin, _ = rehearsal_db
    files = MIGRATION_FILES
    rows = {
        version: (name, checksum)
        for version, name, checksum in admin.execute(
            "SELECT version,name,checksum_sha256 FROM collection.schema_migrations ORDER BY version"
        ).fetchall()
    }
    assert pending_migrations(files, rows) == []

    drift_path = tmp_path / "changed.sql"
    drift_path.write_text(files[0].path.read_text(encoding="utf-8") + "-- changed\n", encoding="utf-8")
    drifted = [MigrationFile(1, files[0].name, drift_path), files[1]]
    with pytest.raises(MigrationDriftError, match="checksum"):
        pending_migrations(drifted, rows)
    with pytest.raises(MigrationDriftError, match="name"):
        pending_migrations(files, {1: ("renamed", rows[1][1]), 2: rows[2]})
    with pytest.raises(MigrationDriftError, match="checksum"):
        pending_migrations(files, {1: (rows[1][0], None), 2: rows[2]})
    with pytest.raises(MigrationDriftError, match="unknown"):
        pending_migrations(files, {**rows, 99: ("orphan", sha256(b"orphan").hexdigest())})
    with pytest.raises(MigrationDriftError, match="ordered prefix"):
        pending_migrations(files, {2: rows[2]})

    with pytest.raises(psycopg.errors.NotNullViolation):
        with admin.transaction():
            admin.execute("INSERT INTO collection.schema_migrations (version,name) VALUES (3,'no-checksum')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        with admin.transaction():
            admin.execute(
                "INSERT INTO collection.schema_migrations (version,name,checksum_sha256) VALUES (1,'0001_collection_processing_archive',%s)",
                (sha256(b"wrong file").hexdigest(),),
            )


def test_rehearsal_custom_dump_manifest_and_isolated_restore(rehearsal_db, tmp_path):
    admin, socket_dir = rehearsal_db
    pg_dump = _pg_tool("pg_dump")
    pg_restore = _pg_tool("pg_restore")
    if not pg_dump or not pg_restore:
        pytest.skip("PostgreSQL pg_dump/pg_restore are not installed")

    dump_path = tmp_path / "moobby-fixture.dump"
    list_path = tmp_path / "archive-list.txt"
    manifest_path = tmp_path / "manifest.json"
    env = {**os.environ, "PGHOST": str(socket_dir), "PGUSER": "postgres"}
    subprocess.run(
        [pg_dump, "--dbname=postgres", "--format=custom",
         "--schema=collection", "--schema=processing", "--schema=archive",
         f"--file={dump_path}"],
        env=env, check=True, capture_output=True, text=True,
    )
    archive_listing = subprocess.run(
        [pg_restore, "--list", str(dump_path)],
        check=True, capture_output=True, text=True,
    ).stdout
    list_path.write_text(archive_listing, encoding="utf-8")
    assert "TABLE collection schema_migrations postgres" in archive_listing
    assert "TABLE archive export_batches postgres" in archive_listing

    before_counts = _relation_counts(admin)
    manifest = {
        "scope": ["collection", "processing", "archive"],
        "source_server_version": admin.execute("SHOW server_version").fetchone()[0],
        "file": dump_path.name,
        "bytes": dump_path.stat().st_size,
        "sha256": sha256(dump_path.read_bytes()).hexdigest(),
        "counts": before_counts,
        "archive_list_sha256": sha256(archive_listing.encode("utf-8")).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
    verified = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert verified["bytes"] == dump_path.stat().st_size
    assert verified["sha256"] == sha256(dump_path.read_bytes()).hexdigest()
    assert verified["archive_list_sha256"] == sha256(list_path.read_bytes()).hexdigest()

    restore_db = "moobby_restore_" + uuid.uuid4().hex[:12]
    admin.execute(f'CREATE DATABASE "{restore_db}"')
    try:
        subprocess.run(
            [pg_restore, f"--dbname={restore_db}", "--exit-on-error", "--single-transaction", str(dump_path)],
            env=env, check=True, capture_output=True, text=True,
        )
        with psycopg.connect(dbname=restore_db, user="postgres", host=str(socket_dir)) as restored:
            assert _relation_counts(restored) == before_counts
            assert restored.execute(
                "SELECT count(*) FROM collection.schema_migrations"
            ).fetchone()[0] == 2
            assert restored.execute(
                "SELECT count(*) FROM collection.sources WHERE platform='x' AND account_handle='commuterline'"
            ).fetchone()[0] == 1
            assert restored.execute(
                "SELECT count(*) FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid=c.connamespace "
                "WHERE n.nspname IN ('collection','processing','archive') AND c.contype='f' AND NOT c.convalidated"
            ).fetchone()[0] == 0
    finally:
        admin.execute(f'DROP DATABASE "{restore_db}" WITH (FORCE)')


def test_runtime_role_name_collision_stops_without_modifying_existing_role(rehearsal_db):
    admin, socket_dir = rehearsal_db
    collision_db = "moobby_collision_" + uuid.uuid4().hex[:12]
    before = admin.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolinherit "
        "FROM pg_roles WHERE rolname='moobby_runtime'"
    ).fetchone()
    admin.execute(f'CREATE DATABASE "{collision_db}"')
    try:
        with psycopg.connect(dbname=collision_db, user="postgres", host=str(socket_dir), autocommit=True) as collision:
            with collision.transaction():
                collision.execute(MIGRATION_FILES[0].path.read_text(encoding="utf-8"))
                collision.execute(
                    "INSERT INTO collection.schema_migrations (version,name,checksum_sha256) VALUES (%s,%s,%s)",
                    (1, MIGRATION_FILES[0].name, MIGRATION_FILES[0].checksum_sha256),
                )
            with pytest.raises(psycopg.errors.DuplicateObject, match="moobby_runtime"):
                with collision.transaction():
                    collision.execute(MIGRATION_FILES[1].path.read_text(encoding="utf-8"))
            assert collision.execute(
                "SELECT count(*) FROM pg_policies WHERE schemaname IN ('collection','processing','archive')"
            ).fetchone()[0] == 0
        after = admin.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolinherit "
            "FROM pg_roles WHERE rolname='moobby_runtime'"
        ).fetchone()
        assert after == before
    finally:
        admin.execute(f'DROP DATABASE "{collision_db}" WITH (FORCE)')
