# Database inventory and schema review record

## Current status

The schema in migrations 0001 and 0002 was installed on the confirmed Supabase target on 2026-10-22 after explicit owner authorization of the exact two file hashes. Post-install verification is recorded in [final-migration-readiness.md](final-migration-readiness.md). The owner still needs to configure the runtime password/URI and validate a runtime login before Stage 5 is fully complete.

## Purpose

This document explains the read-only R0 inventory and the numbered DDL for the Collection, Processing, and Archive groups. The migrations are no longer drafts: the owner-authorized installation and read-only post-checks are recorded in [inventory-results.md](inventory-results.md). Historical inventory counts remain snapshots from before installation.

## Inputs, outputs, and dependencies

`scripts/db_inventory.py` loads `DATABASE_URL` through the existing `moobby.config` module, uses the shared redaction/output helper, and prints a text report to stdout. It forces TLS, requests a five-second connection timeout, sets psycopg read-only mode before beginning the transaction, confirms that setting with a `SELECT`, and then issues catalog/`SELECT` queries only. It writes no report files. It inventories schemas, estimated table row counts, all table constraints and foreign keys, views, functions, roles and memberships, schema/table grants, RLS flags, and policies. Approximate row estimates come from `pg_class.reltuples`; they are not exact counts.

The script depends on the project’s pinned `psycopg[binary]` dependency and the existing configuration/redaction modules. It prints a masked target hint and never prints the URI. Failures are routed through the shared redactor. The script connected to the configured Supabase target, verified read-only mode, and completed the catalog queries. It did not perform any write operation.

### Inventory configuration and failure modes

The only inventory setting is `DATABASE_URL`, supplied through the existing project-root `.env` or process environment; no secret values belong in this document. A missing setting, missing `psycopg`, connection/query error, insufficient catalog privileges, or server that does not confirm a read-only transaction produces a redacted error and non-zero exit. A connection failure does not imply anything about the real database contents.

The migration files are plain PostgreSQL SQL. The read-only pre-install R0 inventory confirmed the target had `anon` and `authenticated` roles and no Moobby schema/role collisions. The files passed local PostgreSQL rehearsal and were later installed remotely under the exact owner authorization documented in the Stage 5 installation record. Neither migration is an application tool.

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
        text collection_mode
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
        text raw_text nullable_after_purge
        timestamptz payload_purged_at
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
        text request_csv nullable_after_purge
        text response_csv nullable_after_purge
        timestamptz payload_purged_at
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
| `schema_migrations` | Positive integer version, unique migration name, required SHA-256 checksum, and application time. Gives later preflight a version source. |
| `sources` | Monitored profile registry. A check restricts it to `x:commuterline`; the migration seeds that row. Search-discovered author accounts are not inserted here. |
| `discovered_authors` | Separate X author registry keyed by external author ID. Search results can point to it without becoming monitored profile sources. |
| `collection_runs` | Run UUID, collector version, `profile`/`search` method, separate `live`/`historical` mode, status including `partial` and `auth_required`, optional profile source, coverage JSON, error/skip counts, start/end times, and stop reason. A check pairs `profile` with a profile source and `search` with no profile source. |
| `raw_contents` | Stable post identity keyed by `(platform, external_id)`, with optional author reference and first/last-seen times. This is not a `raw_posts` duplicate. |
| `raw_snapshots` | Captured payload/version keyed by content and capture hash. Keeps literal `published_at_original` alongside parsed `published_at`, plus time, text, and media quality flags. Text/media payload fields become nullable only after separately authorized verified-export retention processing. |
| `content_observations` | Run-to-content observation with exactly one observation per `(run_id, content_id)`. Its composite snapshot/content FK enforces ownership consistency. |

### Processing (`processing`)

| Table | Responsibility and enforced shape |
|---|---|
| `processing_jobs` | One job per `(snapshot_id, pipeline_version)`, with queued/processing/succeeded/skipped/failed status, lease, attempt count, filter result, skip reason, and timestamps. A processing job must have a lease; a skipped job must have a reason. |
| `llm_attempts` | Append-oriented attempt detail: model and prompt/contract versions, request/response CSV, HTTP/finish data, nullable token counts, duration, error, and validation result. The partial unique index permits only one `is_success` row per job. Token counts have no default and remain NULL when unknown. CSV payload columns can be nulled after separately authorized verified-export retention processing. |

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
- A run receipt’s UUID is unique. A second plain INSERT for the same UUID is rejected. The runtime role receives no UPDATE privilege on `batch_digest`, so it cannot overwrite the digest through an update. An insert conflict still needs application transaction logic to compare the existing digest and reject mismatch.
- Foreign keys use restrictive deletion behavior by default; there are no cascades and runtime has no DELETE grant.
- Migration 0002 enables RLS on every table created by 0001, revokes schema and table privileges from `PUBLIC`, `anon`, and `authenticated`, grants the runtime role only table/column operations needed by the proposed runner, and creates runtime-only policies. No DDL, role-management, or DELETE permission is granted.

## Runtime grants and RLS rationale

`moobby_runtime` is a LOGIN role with no password clause in the file and with superuser, database creation, role creation, replication, and RLS bypass disabled. Set its password out of band after inspecting the target and confirming the role does not already exist. The role receives schema usage and explicit table grants; update privileges are column-limited where practical. `sources`, migration tracking, raw capture records, LLM attempts, and fingerprints are read/insert-only for the runtime where updates are unnecessary.

RLS policies allow the single runtime role to access its pipeline tables. They do not grant access to `anon` or `authenticated`; schema/table revokes block those roles at the SQL privilege layer as well. The owner reported the Dashboard exposed-schema list as exactly `graphql_public`, `public`, excluding all three Moobby schemas. This is owner-confirmed but was not independently read from a connected Dashboard. RLS/grants in this draft do not configure that project setting, so reconfirm it before execution.

This draft does not include sequence grants because UUID defaults use PostgreSQL `gen_random_uuid()` and no sequence-backed columns are proposed. Future tables need explicit grants and RLS policies; no default privileges are installed.

## Acceptance criteria coverage

- **AC-03:** Local PostgreSQL 17.11 and 18.4 rehearsals verified runtime SELECT/INSERT under RLS and denial of DDL, role management, payload UPDATE, and DELETE; `anon`/`authenticated` were denied table access. Live Supabase role behavior remains untested.
- **AC-05:** Unique keys cover post/snapshot/observation/job/fingerprint/export deduplication. Receipt UUID is unique and the digest is not updateable by runtime. Correct digest comparison on retry is still an application responsibility and needs a later uploader test.
- **AC-06:** Receipts and fingerprints are separate from payload tables and can remain as archive records. Retry recognition after raw payload purge is not implemented or tested. Current restrictive FKs keep payload-bearing rows and their audit graph in place. This draft proposes payload redaction by setting the raw text/media metadata and CSV request/response columns to NULL only after verified export; row identifiers, hashes, labels/metadata, receipts, and fingerprints remain. The retention operation needs a separately authorized implementation and dependency checks.

## Decisions guided by SPEC and proposals requiring review

The following choices use explicit guidance in SPEC §4, §5, §7.2, §9, §10.3–10.4, §11, §12.1, and AC-03/05/06. “Proposed” means suitable for review, not approved where the SPEC does not lock the detail.

| Topic | Draft choice | Basis / tradeoff / remaining decision |
|---|---|---|
| Author identity | `discovered_authors` is separate from profile `sources`; external X author ID is the stable uniqueness key, handle/display name are mutable metadata. Raw content links to author optionally. | Matches §4 that search authors are not profile sources and keeps post identity separate. Confirm X external IDs are captured; unknown IDs remain NULL and need review/dedup policy. The profile source seed is only `x:commuterline`; it does not guess an X numeric ID. |
| Run method and mode | `method`: `profile` or `search`; independent `collection_mode`: `live` or `historical`. Status: `running`, `succeeded`, `partial`, `failed`, `auth_required`. | `profile`/`search` follows §6; separate mode distinguishes the historical dataset without inventing a method. `partial` and exact status semantics are proposals. Confirm the status vocabulary and stop-reason vocabulary before uploader implementation. |
| CSV payloads | Keep Orvix request/response CSV in `llm_attempts` until export verification; payload purge then NULLs both CSV columns and `raw_text`/media payload metadata while retaining row metadata and hashes. | §10.4 requires CSV reproducibility; §12.1 allows payload retention after verified export and keeps manifest/receipts. Purge is a separate, owner-authorized retention operation; decide protected local export archive policy and exactly what counts as payload. |
| Processing jobs | Exactly one row per `(snapshot_id, pipeline_version)`, attempts increment on the job, LLM calls append numbered `llm_attempts`, and a partial unique index permits at most one successful attempt. | Supports §9 idempotence/retry and one accepted success. It cannot prove that the job’s final status agrees with the successful attempt; application transaction logic must enforce that. |
| Receipt retries | `run_id` is the receipt primary key and `batch_digest` is immutable for runtime. On conflict, uploader compares digest: same digest is idempotent, different digest is rejected. | AC-05/06. Unique key alone rejects all duplicate INSERTs and cannot distinguish same versus different digest; comparison belongs in uploader transaction code and must be tested. |
| Export lifecycle | Batch and item statuses allow §12.1 values and state-required timestamps. | Draft checks required timestamps but does not enforce monotonic transitions, frozen membership, exact manifest checksum/count, or purge eligibility. Those require app transactions or reviewed triggers; choose after implementation design. |
| Purge dependencies | Retain all rows and replace payload values with NULL after verified export; no DELETE is granted. Fingerprints/receipts remain. | Preserves identity and audit refs without unsafe cascading deletes. Transit/review references do not exist yet. Define dependency query/authorization, local copy retention, and a separate purge role/procedure before implementing purge. |
| Runtime role/grants | `moobby_runtime` has explicit table and column grants, RLS policies, no DDL/role-management/DELETE, and no password in SQL. | AC-03 and §7.2. Inventory shows Supabase roles including `anon`/`authenticated`, but no `moobby_runtime`. Before applying, verify role collision/membership and inherited rights. Set password out of band. |
| Data API exposure | Draft revokes SQL schema/table access from `PUBLIC`, `anon`, and `authenticated`, but does not configure API exposed schemas. | Owner reported the exact Dashboard list as `graphql_public`, `public`, which excludes the Moobby schemas. This is not independently verified from a Dashboard session; reconfirm before execution. |
| Migration tracking | `collection.schema_migrations` stores version, name, required SHA-256, and application time; the checksum is computed from the exact migration file by the migration operator. | Supports later version preflight. The inventory found no `supabase_migrations` schema; Supabase-managed migration-like tables exist but were not read. A tested helper rejects unknown versions, name drift, missing checksums, and checksum drift before a caller executes SQL. The migration SQL drafts themselves are not idempotent; the operator must check history, apply a pending file, and record its checksum in the same transaction. |
| Human review labels | No review table is added in this stage; export is expected to carry both `llm_label` and optional `review_label` in JSONL when the later review model exists. | §2/§12 require review labels not to overwrite original LLM labels. The relevant review/candidate entities are deferred by this stage’s Collection/Processing/Archive scope. A later schema change must model review history and connect it to the exported record. |

## Assumptions and limitations

- The inventory on 22 October 2026 listed the managed schemas and objects recorded in [inventory-results.md](inventory-results.md); approximate row estimates are not exact counts. No Moobby schemas or public application tables were listed at that inspection.
- The draft assumes PostgreSQL support for partial indexes, RLS, `gen_random_uuid()`, and the Supabase `anon`/`authenticated` roles. The earlier R0 inventory confirmed those roles and `extensions.gen_random_uuid()`. Both draft migrations and the synthetic backup/restore harness passed on local PostgreSQL 17.11 and 18.4.
- Both migrations passed disposable local PostgreSQL rehearsals before the separately approved live installation. The R0 counts in this section remain a pre-install snapshot; current objects and post-install checks are recorded in [inventory-results.md](inventory-results.md).
- Supabase Data API exposure settings are not visible through PostgreSQL inventory. The owner reported the current list as `graphql_public`, `public`; reconfirm it immediately before execution.
- Current payload redaction retains database rows. Purge eligibility and blocked references are not enforced by this draft; do not run a purge based on status alone.
- Cross-row/application behavior remains outside ordinary CHECK constraints: receipt digest comparison, retry reuse after purge, final job success consistency, forward export transitions, checksum verification, membership freeze, review history, and purge dependency checks.

## Commands and test status

The inventory can be run manually from the repository root after the owner has supplied a project `.env` and installed dependencies:

```sh
python scripts/db_inventory.py
```

The automated pytest suite includes mocked read-only inventory checks, static schema invariants, and isolated PostgreSQL migration/grant/RLS/backup-restore tests. The refreshed live inventory completed with read-only mode confirmed (see [inventory-results.md](inventory-results.md)); the 2026-10-22 follow-up also inspected managed triggers, policies, extensions, and name collisions without writes. It did not test live write privileges. PostgreSQL 17.11 and 18.4 parsed and executed both drafts in isolated local clusters. The Supabase CLI logical dump restored to an isolated Supabase stack on PostgreSQL 17.11 with matching exact counts for all 31 included relations, but omitted eight catalog relations and does not provide whole-project recovery. The verified bundle is copied to a local FileVault-encrypted APFS destination; the source remains untouched. See [backup-restore-verification.md](backup-restore-verification.md), [schema-installation.md](schema-installation.md), and [final-migration-readiness.md](final-migration-readiness.md) for scope and blockers.
