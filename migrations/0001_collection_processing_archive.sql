-- DRAFT ONLY: review and adapt after R0 inventory. Never apply blindly.
-- Scope: Collection, Processing, Archive; no Transit or Operations schema.
-- Run as one transaction through a reviewed migration process.

CREATE SCHEMA collection;
CREATE SCHEMA processing;
CREATE SCHEMA archive;

CREATE TABLE collection.schema_migrations (
    version integer PRIMARY KEY CHECK (version > 0),
    name text NOT NULL UNIQUE,
    checksum_sha256 text NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- This registry is deliberately limited to the one monitored profile.
CREATE TABLE collection.sources (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform text NOT NULL CHECK (platform = 'x'),
    account_handle text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sources_only_commuterline CHECK (account_handle = 'commuterline'),
    CONSTRAINT sources_platform_handle_unique UNIQUE (platform, account_handle)
);

-- Search-discovered authors live outside the monitored-profile registry.
CREATE TABLE collection.discovered_authors (
    author_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform text NOT NULL CHECK (platform = 'x'),
    external_author_id text NOT NULL,
    account_handle text,
    display_name text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT discovered_authors_platform_id_unique UNIQUE (platform, external_author_id)
);

CREATE TABLE collection.collection_runs (
    run_id uuid PRIMARY KEY,
    collector_version text NOT NULL,
    method text NOT NULL CHECK (method IN ('profile', 'search')),
    collection_mode text NOT NULL CHECK (collection_mode IN ('live', 'historical')),
    profile_source_id uuid REFERENCES collection.sources(source_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed', 'auth_required')),
    coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_count integer NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    skip_count integer NOT NULL DEFAULT 0 CHECK (skip_count >= 0),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    stop_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT collection_run_method_source_match CHECK (
        (method = 'profile' AND profile_source_id IS NOT NULL)
        OR (method = 'search' AND profile_source_id IS NULL)
    ),
    CONSTRAINT collection_run_finish_after_start CHECK (
        finished_at IS NULL OR finished_at >= started_at
    )
);

CREATE TABLE collection.raw_contents (
    content_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform text NOT NULL CHECK (platform = 'x'),
    external_id text NOT NULL,
    author_id uuid REFERENCES collection.discovered_authors(author_id) ON DELETE RESTRICT,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT raw_contents_platform_external_id_unique UNIQUE (platform, external_id),
    CONSTRAINT raw_contents_seen_order CHECK (last_seen_at >= first_seen_at)
);

CREATE TABLE collection.raw_snapshots (
    snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id uuid NOT NULL REFERENCES collection.raw_contents(content_id) ON DELETE RESTRICT,
    capture_hash text NOT NULL CHECK (capture_hash ~ '^[0-9a-f]{64}$'),
    raw_text text,
    published_at_original text,
    published_at timestamptz,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    time_quality text NOT NULL CHECK (
        time_quality IN ('valid', 'missing', 'invalid', 'time_mismatch', 'unknown')
    ),
    text_quality text NOT NULL CHECK (
        text_quality IN ('complete', 'truncated', 'ui_mixed', 'unknown')
    ),
    media_quality text NOT NULL CHECK (
        media_quality IN ('available', 'unavailable', 'not_checked', 'unknown')
    ),
    media_metadata jsonb NOT NULL DEFAULT '[]'::jsonb,
    payload_purged_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT raw_snapshots_content_capture_unique UNIQUE (content_id, capture_hash),
    CONSTRAINT raw_snapshots_id_content_unique UNIQUE (snapshot_id, content_id),
    CONSTRAINT raw_snapshots_timestamp_quality CHECK (
        (time_quality = 'valid' AND published_at IS NOT NULL)
        OR (time_quality = 'time_mismatch' AND published_at IS NOT NULL)
        OR (time_quality IN ('missing', 'invalid', 'unknown') AND published_at IS NULL)
    ),
    CONSTRAINT raw_snapshots_payload_purge_consistent CHECK (
        (payload_purged_at IS NULL AND raw_text IS NOT NULL)
        OR (payload_purged_at IS NOT NULL AND raw_text IS NULL AND media_metadata = '[]'::jsonb)
    )
);
COMMENT ON COLUMN collection.raw_snapshots.payload_purged_at IS
    'Set by a separately authorized retention operation only after verified export and reference checks; row/hash metadata remains for deduplication.';

CREATE TABLE collection.content_observations (
    observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES collection.collection_runs(run_id) ON DELETE RESTRICT,
    content_id uuid NOT NULL REFERENCES collection.raw_contents(content_id) ON DELETE RESTRICT,
    snapshot_id uuid NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT content_observations_run_content_unique UNIQUE (run_id, content_id),
    CONSTRAINT content_observations_snapshot_content_fk
        FOREIGN KEY (snapshot_id, content_id)
        REFERENCES collection.raw_snapshots(snapshot_id, content_id)
        ON DELETE RESTRICT
);

CREATE TABLE processing.processing_jobs (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id uuid NOT NULL REFERENCES collection.raw_snapshots(snapshot_id) ON DELETE RESTRICT,
    pipeline_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'processing', 'succeeded', 'skipped', 'failed')),
    lease_expires_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    filter_result text CHECK (filter_result IN ('relevant', 'irrelevant', 'not_evaluated')),
    skip_reason text,
    last_error text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT processing_jobs_snapshot_pipeline_unique UNIQUE (snapshot_id, pipeline_version),
    CONSTRAINT processing_jobs_processing_has_lease CHECK (
        status <> 'processing' OR lease_expires_at IS NOT NULL
    ),
    CONSTRAINT processing_jobs_skipped_has_reason CHECK (
        status <> 'skipped' OR skip_reason IS NOT NULL
    ),
    CONSTRAINT processing_jobs_finish_after_start CHECK (
        started_at IS NULL OR finished_at IS NULL OR finished_at >= started_at
    )
);

CREATE TABLE processing.llm_attempts (
    llm_attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES processing.processing_jobs(job_id) ON DELETE RESTRICT,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    model text NOT NULL,
    prompt_version text NOT NULL,
    contract_version text NOT NULL,
    request_csv text,
    response_csv text,
    http_status smallint CHECK (http_status BETWEEN 100 AND 599),
    finish_reason text,
    input_tokens bigint CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens bigint CHECK (output_tokens IS NULL OR output_tokens >= 0),
    reasoning_tokens bigint CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
    duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error text,
    validation_result text NOT NULL CHECK (
        validation_result IN ('not_run', 'pending', 'valid', 'invalid', 'error')
    ),
    is_success boolean NOT NULL DEFAULT false,
    payload_purged_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT llm_attempts_job_attempt_unique UNIQUE (job_id, attempt_number),
    CONSTRAINT llm_attempts_success_is_valid CHECK (NOT is_success OR validation_result = 'valid'),
    CONSTRAINT llm_attempts_payload_purge_consistent CHECK (
        payload_purged_at IS NULL OR (request_csv IS NULL AND response_csv IS NULL)
    ),
    CONSTRAINT llm_attempts_request_present_before_purge CHECK (
        payload_purged_at IS NOT NULL OR request_csv IS NOT NULL
    )
);
COMMENT ON COLUMN processing.llm_attempts.payload_purged_at IS
    'Set only by a separately authorized retention operation after verified export; attempt metadata remains while request/response CSV payloads are nulled.';

-- At most one accepted successful result per processing job.
CREATE UNIQUE INDEX llm_attempts_one_success_per_job
    ON processing.llm_attempts(job_id)
    WHERE is_success;

CREATE TABLE archive.processed_fingerprints (
    fingerprint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint_kind text NOT NULL CHECK (fingerprint_kind IN ('post_identity', 'snapshot')),
    algorithm text NOT NULL DEFAULT 'sha256' CHECK (algorithm = 'sha256'),
    fingerprint_hash text NOT NULL CHECK (fingerprint_hash ~ '^[0-9a-f]{64}$'),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT processed_fingerprints_kind_hash_unique UNIQUE (fingerprint_kind, fingerprint_hash)
);

CREATE TABLE archive.run_receipts (
    run_id uuid PRIMARY KEY REFERENCES collection.collection_runs(run_id) ON DELETE RESTRICT,
    batch_digest text NOT NULL CHECK (batch_digest ~ '^[0-9a-f]{64}$'),
    archived boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT run_receipt_archive_time_consistent CHECK (
        (archived = false AND archived_at IS NULL)
        OR (archived = true AND archived_at IS NOT NULL)
    )
);
COMMENT ON TABLE archive.run_receipts IS
    'The run_id primary key rejects a second receipt row; uploader must compare batch_digest and reject same UUID with a different digest.';

CREATE TABLE archive.export_batches (
    batch_id uuid PRIMARY KEY,
    status text NOT NULL CHECK (
        status IN ('prepared', 'exported', 'verified', 'purge_pending', 'purged')
    ),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    manifest jsonb,
    record_count bigint CHECK (record_count IS NULL OR record_count >= 0),
    manifest_sha256 text CHECK (
        manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    exported_at timestamptz,
    verified_at timestamptz,
    purge_pending_at timestamptz,
    purged_at timestamptz,
    last_error text,
    CONSTRAINT export_batch_state_timestamps CHECK (
        (status = 'prepared' OR exported_at IS NOT NULL)
        AND (status IN ('prepared', 'exported') OR verified_at IS NOT NULL)
        AND (status NOT IN ('purge_pending', 'purged') OR purge_pending_at IS NOT NULL)
        AND (status <> 'purged' OR purged_at IS NOT NULL)
    )
);

CREATE TABLE archive.export_items (
    export_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id uuid NOT NULL REFERENCES archive.export_batches(batch_id) ON DELETE RESTRICT,
    job_id uuid NOT NULL REFERENCES processing.processing_jobs(job_id) ON DELETE RESTRICT,
    item_status text NOT NULL CHECK (
        item_status IN ('prepared', 'exported', 'verified', 'purge_pending', 'purged')
    ),
    record_sha256 text CHECK (record_sha256 IS NULL OR record_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT export_items_batch_job_unique UNIQUE (batch_id, job_id)
);

-- Seed only the locked monitored profile. Search-discovered authors are not sources.
INSERT INTO collection.sources (platform, account_handle)
VALUES ('x', 'commuterline');

-- The migration operator records this version and the SHA-256 of this exact file
-- in the same transaction as this DDL. See docs-database/schema-installation.md.
