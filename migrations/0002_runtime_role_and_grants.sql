-- DRAFT ONLY: inspect the R0 inventory and target project before applying.
-- No password is stored here. Set a strong password out of band after review.
-- Purge requires DELETE or a separately controlled procedure and a separate decision.

CREATE ROLE moobby_runtime
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;

-- RLS does not replace SQL privileges. Remove API-facing role privileges and
-- schema visibility. Confirm the project's Supabase Data API exposed-schema
-- configuration separately; current Supabase behavior/configuration is UNVERIFIED.
REVOKE ALL ON SCHEMA collection, processing, archive FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA collection, processing, archive
    FROM PUBLIC, anon, authenticated;

GRANT USAGE ON SCHEMA collection, processing, archive TO moobby_runtime;

GRANT SELECT ON collection.schema_migrations TO moobby_runtime;
GRANT SELECT ON collection.sources TO moobby_runtime;
GRANT SELECT, INSERT ON collection.discovered_authors TO moobby_runtime;
GRANT UPDATE (account_handle, display_name, last_seen_at)
    ON collection.discovered_authors TO moobby_runtime;

GRANT SELECT, INSERT ON collection.collection_runs TO moobby_runtime;
GRANT UPDATE (status, coverage, error_count, skip_count, finished_at, stop_reason)
    ON collection.collection_runs TO moobby_runtime;
GRANT SELECT, INSERT ON collection.raw_contents TO moobby_runtime;
GRANT UPDATE (author_id, last_seen_at) ON collection.raw_contents TO moobby_runtime;
GRANT SELECT, INSERT ON collection.raw_snapshots TO moobby_runtime;
GRANT SELECT, INSERT ON collection.content_observations TO moobby_runtime;

GRANT SELECT, INSERT ON processing.processing_jobs TO moobby_runtime;
GRANT UPDATE (status, lease_expires_at, attempt_count, filter_result, skip_reason,
              last_error, started_at, finished_at, updated_at)
    ON processing.processing_jobs TO moobby_runtime;
GRANT SELECT, INSERT ON processing.llm_attempts TO moobby_runtime;

GRANT SELECT, INSERT ON archive.processed_fingerprints TO moobby_runtime;
GRANT SELECT, INSERT ON archive.run_receipts TO moobby_runtime;
GRANT UPDATE (archived, archived_at) ON archive.run_receipts TO moobby_runtime;
GRANT SELECT, INSERT ON archive.export_batches TO moobby_runtime;
GRANT UPDATE (status, manifest, record_count, manifest_sha256, exported_at,
              verified_at, purge_pending_at, purged_at, last_error)
    ON archive.export_batches TO moobby_runtime;
GRANT SELECT, INSERT ON archive.export_items TO moobby_runtime;
GRANT UPDATE (item_status, record_sha256) ON archive.export_items TO moobby_runtime;

-- Each application table has an explicit runtime policy. No policy is granted
-- to anon/authenticated; their schema/table privileges were revoked above.
ALTER TABLE collection.schema_migrations ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_read ON collection.schema_migrations
    FOR SELECT TO moobby_runtime USING (true);

ALTER TABLE collection.sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_read ON collection.sources
    FOR SELECT TO moobby_runtime USING (true);

ALTER TABLE collection.discovered_authors ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON collection.discovered_authors
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE collection.collection_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON collection.collection_runs
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE collection.raw_contents ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON collection.raw_contents
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE collection.raw_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON collection.raw_snapshots
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE collection.content_observations ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON collection.content_observations
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE processing.processing_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON processing.processing_jobs
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE processing.llm_attempts ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON processing.llm_attempts
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE archive.processed_fingerprints ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON archive.processed_fingerprints
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE archive.run_receipts ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON archive.run_receipts
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE archive.export_batches ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON archive.export_batches
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

ALTER TABLE archive.export_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY runtime_all ON archive.export_items
    FOR ALL TO moobby_runtime USING (true) WITH CHECK (true);

INSERT INTO collection.schema_migrations (version, name)
VALUES (2, '0002_runtime_role_and_grants');
