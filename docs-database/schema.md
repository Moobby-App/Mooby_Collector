# Database inventory and Stage 1 schema draft

## Purpose

This document accompanies two review artifacts: a read-only R0 inventory script and a numbered DDL proposal for the Collection, Processing, and Archive groups. Both migrations are drafts only. They have not been applied, and no live database was inspected for this stage.

## Inputs, outputs, and dependencies

`scripts/db_inventory.py` loads `DATABASE_URL` through the existing `moobby.config` module, uses the shared redaction/output helper, and prints a text report to stdout. It forces TLS, requests a five-second connection timeout, starts transactions with PostgreSQL `default_transaction_read_only=on`, confirms that setting with a `SELECT`, and then issues catalog/`SELECT` queries only. It writes no report files. It inventories schemas, estimated table row counts, foreign keys, views, functions, roles and memberships, schema/table grants, RLS flags, and policies. Approximate row estimates come from `pg_class.reltuples`; they are not exact counts.

The script depends on the project’s pinned `psycopg[binary]` dependency and the existing configuration/redaction modules. It prints a masked target hint and never prints the URI. Failures are routed through the shared redactor. This script was not run against any database because network access is unavailable and explicitly out of scope.

### Inventory configuration and failure modes

The only inventory setting is `DATABASE_URL`, supplied through the existing project-root `.env` or process environment; no secret values belong in this document. A missing setting, missing `psycopg`, connection/query error, insufficient catalog privileges, or server that does not confirm a read-only transaction produces a redacted error and non-zero exit. A connection failure does not imply anything about the real database contents.

The migrations are plain PostgreSQL SQL drafts. They assume the target is a Supabase PostgreSQL database with the `anon` and `authenticated` roles. That assumption must be checked during R0 before anyone applies migration 0002. Neither migration is an application tool, and neither was executed.

## Proposed ERD

```mermaid
erDiagram
    sources ||--o{ collection_runs : scopes_profile_run
    discovered_authors o|--o{ raw_contents : authored
    collection_runs ||--o{ content_observations : records
    raw_contents ||--o{ raw_snapshots : captured_as
    raw_contents ||--o{ content_observations : observed
    raw_snapshots ||--o{ content_observations : identifies_snapshot
    raw_snapshots ||--o{ processing_jobs : processed_by
    processing_jobs ||--o{ llm_attempts : attempted
    collection_runs ||--o| run_receipts : archived_as
    processing_jobs ||--o{ export_items : included_in
    export_batches ||--o{ export_items : contains
    schema_migrations {
        int version PK
        text name
        text checksum_sha256
        timestamptz applied_at
    }
    sources {
        uuid source_id PK
        text platform
        text account_handle
        bool is_active
    }
    discovered_authors {
        uuid author_id PK
        text platform
        text external_author_id UK
        text account_handle
    }
    collection_runs {
        uuid run_id PK
        text collector_version
        text method
        text status
        jsonb coverage
        timestamptz started_at
        timestamptz finished_at
    }
    raw_contents {
        uuid content_id PK
        text platform
        text external_id UK
        uuid author_id FK
    }
    raw_snapshots {
        uuid snapshot_id PK
        uuid content_id FK
        text capture_hash
        text raw_text
        text published_at_original
        timestamptz published_at
        text time_quality
    }
    content_observations {
        uuid observation_id PK
        uuid run_id FK
        uuid content_id FK
        uuid snapshot_id FK
        timestamptz observed_at
    }
    processing_jobs {
        uuid job_id PK
        uuid snapshot_id FK
        text pipeline_version
        text status
        timestamptz lease_expires_at
        int attempt_count
    }
    llm_attempts {
        uuid llm_attempt_id PK
        uuid job_id FK
        int attempt_number
        text request_csv
        text response_csv
        bigint input_tokens
        bigint output_tokens
        bool is_success
    }
    processed_fingerprints {
        uuid fingerprint_id PK
        text fingerprint_kind
        text fingerprint_hash
    }
    run_receipts {
        uuid run_id PK_FK
        text batch_digest
        bool archived
    }
    export_batches {
        uuid batch_id PK
        text status
        int schema_version
        jsonb manifest
    }
    export_items {
        uuid export_item_id PK
        uuid batch_id FK
        uuid job_id FK
        text item_status
    }
```

The composite foreign key on `content_observations(snapshot_id, content_id)` references the same pair in `raw_snapshots`. This prevents attaching a snapshot of one post to an observation for another post.

## Tables and responsibilities

### Collection (`collection`)

| Table | Responsibility and enforced shape |
|---|---|
| `schema_migrations` | Positive integer version, unique migration name, optional SHA-256 checksum, and application time. Gives later preflight a version source. |
| `sources` | Monitored profile registry. A check restricts it to `x:commuterline`; the migration seeds that row. Search-discovered author accounts are not inserted here. |
| `discovered_authors` | Separate X author registry keyed by external author ID. Search results can point to it without becoming monitored profile sources. |
| `collection_runs` | Run UUID, collector version, profile/search method, status including `auth_required`, optional profile source, coverage JSON, error/skip counts, start/end times, and stop reason. A check pairs `profile` with a profile source and `search` with no profile source. |
| `raw_contents` | Stable post identity keyed by `(platform, external_id)`, with optional author reference and first/last-seen times. This is not a `raw_posts` duplicate. |
| `raw_snapshots` | Captured payload/version keyed by content and capture hash. Keeps literal `published_at_original` alongside parsed `published_at`, plus time, text, and media quality flags. |
| `content_observations` | Run-to-content observation with exactly one observation per `(run_id, content_id)`. Its composite snapshot/content FK enforces ownership consistency. |

### Processing (`processing`)

| Table | Responsibility and enforced shape |
|---|---|
| `processing_jobs` | One job per `(snapshot_id, pipeline_version)`, with queued/processing/succeeded/skipped/failed status, lease, attempt count, filter result, skip reason, and timestamps. A processing job must have a lease; a skipped job must have a reason. |
| `llm_attempts` | Append-oriented attempt detail: model and prompt/contract versions, request/response CSV, HTTP/finish data, nullable token counts, duration, error, and validation result. The partial unique index permits only one `is_success` row per job. Token counts have no default and remain NULL when unknown. |

### Archive (`archive`)

| Table | Responsibility and enforced shape |
|---|---|
| `processed_fingerprints` | Unique typed SHA-256 hashes only; contains no post text. Supports post-identity and snapshot fingerprint kinds. |
| `run_receipts` | One receipt per collection run, with batch digest and archived marker/time. The primary key prevents a second receipt row for the same UUID; the uploader must compare digests and reject a mismatch. |
| `export_batches` | Stable batch ID, schema version, manifest metadata/checksum/count, status, timestamps, and last error. Status check allows only `prepared`, `exported`, `verified`, `purge_pending`, and `purged`. |
| `export_items` | Frozen batch membership by processing job and record hash, with the same lifecycle status values. Duplicate job membership in one batch is rejected. |

All represented timestamps use `timestamptz`. The publication timestamp’s original text is retained because an invalid timestamp cannot always be represented as a timestamp value. Token counts are nullable and never default to zero.

## Database-level invariants

- Post identity (`raw_contents`), each captured version (`raw_snapshots`), and run observations are separate entities; there is no `raw_posts` table.
- The only profile source permitted by the draft is `x:commuterline`; search-discovered authors use a different table.
- Uniqueness prevents duplicate post identity, snapshot hash for a post, run/post observation, pipeline job, LLM attempt number, fingerprint, receipt UUID, and batch/job export membership.
- The composite observation foreign key prevents a snapshot belonging to post A from being linked to post B.
- Status checks constrain run, job, validation, and export status values. The partial unique index prevents two accepted successful LLM results for one job.
- A run receipt’s UUID is unique. A second plain INSERT for the same UUID is rejected. The runtime role receives no UPDATE privilege on `batch_digest`, so it cannot overwrite the digest through an update; application code must compare the existing digest on retry and reject mismatches.
- Foreign keys use restrictive deletion behavior by default; there are no cascades and runtime has no DELETE grant.
- Migration 0002 enables RLS on every table created by 0001, revokes schema and table privileges from `PUBLIC`, `anon`, and `authenticated`, grants the runtime role only table/column operations needed by the proposed runner, and creates runtime-only policies. No DDL, role-management, or DELETE permission is granted.

## Runtime grants and RLS rationale

`moobby_runtime` is a LOGIN role with no password clause in the file and with superuser, database creation, role creation, replication, and RLS bypass disabled. Set its password out of band after inspecting the target and confirming the role does not already exist. The role receives schema usage and explicit table grants; update privileges are column-limited where practical. `sources`, migration tracking, raw capture records, LLM attempts, and fingerprints are read/insert-only for the runtime where updates are unnecessary.

RLS policies allow the single runtime role to access its pipeline tables. They do not grant access to `anon` or `authenticated`; schema/table revokes block those roles at the SQL privilege layer as well. The SQL comment requires the owner to inspect Supabase's exposed-schema/Data API configuration. Whether the target project exposes any of these schemas through its Data API is **UNVERIFIED**; RLS/grants in this draft are not evidence of that project setting.

This draft does not include sequence grants because UUID defaults use PostgreSQL `gen_random_uuid()` and no sequence-backed columns are proposed. Future tables need explicit grants and RLS policies; no default privileges are installed.

## Acceptance criteria coverage

- **AC-03:** The draft limits runtime grants, enables RLS, revokes `anon`/`authenticated`, and excludes DDL, role management, and DELETE. Actual read/write success and denied operations have not been tested; the role and target are not known.
- **AC-05:** Unique keys cover post/snapshot/observation/job/fingerprint/export deduplication. Receipt UUID is unique and the digest is not updateable by runtime. Correct digest comparison on retry is still an application responsibility and needs a later uploader test.
- **AC-06:** Receipts and fingerprints are separate from payload tables and can remain as archive records. Retry recognition after raw payload purge is not implemented or tested. Current restrictive FKs mean purge order/design needs review before any payload deletion is authorized.

## Open decisions

1. **Search author registry:** approve `discovered_authors` as the simplest normalized separation, or prefer author handle/ID fields attached directly to post identity. Decide whether the profile author is also entered into this registry.
2. **Stable author identity:** confirm X external author ID is available from the collector. If not, choose a fallback and deduplication policy for renamed/unknown accounts.
3. **Run methods/statuses:** confirm `profile` and `search` are sufficient method values, including how the historical dataset mode from §12.3 is represented. Confirm run status values and stop-reason vocabulary.
4. **Quality enums:** review `time_quality`, `text_quality`, and `media_quality` values. `time_mismatch` is represented even though §4 defers full diagnosis; the original timestamp string remains available.
5. **LLM attempt retention:** request/response CSV columns are non-null/retained in this draft for reproducibility. Decide whether payload purge should null these columns, delete attempts, or retain them in a separately protected export archive.
6. **Purge model:** decide how eligible raw snapshots and linked jobs/observations/attempts can be purged while retaining fingerprints and receipts. Current foreign keys are restrictive and runtime cannot delete. Any future purge privilege/procedure needs a separate review and decision.
7. **Receipt conflict contract:** choose the uploader transaction for same UUID/same digest idempotence and same UUID/different digest rejection. The schema uniqueness prevents a second receipt, but the comparison is not implemented in SQL.
8. **Export state transitions:** this draft constrains allowed status values but does not enforce forward-only transition order, immutable membership after export, or verified checksum/count consistency. Decide which guarantees belong in DB constraints/triggers versus application code.
9. **Runtime role target:** confirm `moobby_runtime` is unused or decide how to handle an existing role without changing it. Set its password out of band. Review role memberships and inherited grants during R0.
10. **Role inheritance:** inspect role memberships and inherited grants for `anon` and `authenticated`; direct revokes in 0002 do not erase privileges inherited through another role.
11. **Supabase Data API:** confirm whether `collection`, `processing`, or `archive` are in the target project's exposed schemas and remove them from exposure if needed. This is UNVERIFIED here.
12. **Migration tracking:** decide who owns/applies migrations and where checksums are calculated. The draft records version/name and leaves checksum NULL unless the migration process supplies it.

## Assumptions and limitations

- Supabase PostgreSQL supports the proposed standard catalog, RLS, partial indexes, and `gen_random_uuid()` behavior; verify server compatibility during R0/rehearsal.
- The schema names are available and do not contain another application's objects. R0 must verify that before any DDL is applied.
- The migration files are one-time drafts, not idempotent deploy scripts. Do not run them before inventory, target review, rehearsal, and explicit authorization.
- No actual database contents, roles, policies, grants, row counts, Supabase API exposure settings, or session setup are asserted here.
- Cross-row/application behavior remains outside ordinary CHECK constraints: digest comparison, retry reuse after purge, final job success consistency, export transition ordering, checksum verification, and purge dependency checks.

## Commands and test status

The inventory can be run manually from the repository root after the owner has supplied a project `.env` and installed dependencies:

```sh
python scripts/db_inventory.py
```

Static checks only: Python source was syntax-parsed and the diff was whitespace-checked. The inventory command was not run because the environment has no network access and must not connect to a database in this stage. The SQL was not applied or parsed by a live PostgreSQL server. A real PostgreSQL rehearsal and permission tests remain for later R0/R2 review.
