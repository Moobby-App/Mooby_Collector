from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_1 = (ROOT / "migrations/0001_collection_processing_archive.sql").read_text()
MIGRATION_2 = (ROOT / "migrations/0002_runtime_role_and_grants.sql").read_text()


def test_draft_preserves_raw_identity_snapshot_observation_relationship():
    assert "UNIQUE (platform, external_id)" in MIGRATION_1
    assert "UNIQUE (content_id, capture_hash)" in MIGRATION_1
    assert re.search(
        r"FOREIGN KEY\s*\(snapshot_id, content_id\).*?"
        r"REFERENCES collection\.raw_snapshots\(snapshot_id, content_id\)",
        MIGRATION_1,
        re.S,
    )
    assert "CREATE TABLE collection.raw_posts" not in MIGRATION_1


def test_draft_keeps_tokens_nullable_and_limits_success_per_job():
    assert "input_tokens bigint CHECK (input_tokens IS NULL OR input_tokens >= 0)" in MIGRATION_1
    assert "output_tokens bigint CHECK (output_tokens IS NULL OR output_tokens >= 0)" in MIGRATION_1
    assert "llm_attempts_one_success_per_job" in MIGRATION_1
    assert "WHERE is_success" in MIGRATION_1


def test_draft_supports_purge_metadata_and_export_lifecycle():
    assert "payload_purged_at timestamptz" in MIGRATION_1
    for status in ("prepared", "exported", "verified", "purge_pending", "purged"):
        assert status in MIGRATION_1
    assert "CREATE SCHEMA transit" not in MIGRATION_1
    assert "CREATE SCHEMA operations" not in MIGRATION_1
    assert "GRANT DELETE" not in MIGRATION_2.upper()
    assert "REVOKE DELETE" not in MIGRATION_2.upper()
