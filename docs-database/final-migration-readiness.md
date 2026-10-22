# Final migration readiness and Stage 5 approval package

## Status

**Approval package prepared; live installation is not authorized.** No live migration, reset, purge, role/grant/policy change, or managed-schema modification was performed. PostgreSQL 17.11 rehearsal passed. The Supabase CLI logical dump was restored to an isolated Supabase CLI stack on PostgreSQL 17.11 with exact counts matching for all 31 included relations. Its five dump/manifest files were copied to a persistent FileVault-encrypted local APFS volume outside the repository and temporary directories; all destination hashes match and the source copy remains intact. See [backup-restore-verification.md](backup-restore-verification.md) for the scope and limitations.

The backup is **not a whole-project recovery point**. Eight inventoried managed relations (247 rows, all in three platform migration-history tables) are absent from its data dump; the role file does not recreate the 30-role/24-membership catalog. Provider and Data API settings, Storage object bytes, and other dashboard configuration are not included. None of these omitted objects were altered. The current application-scoped recovery objective is limited to Moobby’s presently absent schemas and role; it does not depend on restoring platform objects. A fresh backup and rehearsal of the agreed scope remain mandatory before installation.

## Read-only managed-object review

On 2026-10-22, a TLS connection to the previously confirmed masked target was opened with `connect_timeout=5`; the server reported PostgreSQL 17.11 and `transaction_read_only=on` before catalog SELECTs. The query found eight non-internal triggers in managed schemas: one on `realtime.subscription`, five on `storage.buckets`, and two on `storage.objects`. Their trigger functions are in the corresponding `realtime`/`storage` schemas. The catalog showed zero visible policies. Five extensions were installed: `pg_stat_statements` 1.11, `pgcrypto` 1.3, `plpgsql` 1.0, `supabase_vault` 0.3.1, and `uuid-ossp` 1.1. No public relations or public functions were listed. No `collection`, `processing`, or `archive` namespace and no `moobby_runtime` role or membership were present.

These are catalog observations only. The eight triggers are retained exactly as found; this inspection does not determine whether each is stock or owner-customized. Data API exposed schemas and provider-level settings remain unverified and require Dashboard review. Managed migration rows and role definitions were not replayed or changed. Reconcile them by keeping them outside this Moobby-only proposal and acknowledging the partial backup scope; any platform-level recovery is a separate owner decision.

## PostgreSQL rehearsal and automated tests

Both numbered migrations and the integration harness were run in isolated PostgreSQL 17.11 and 18.4 clusters. PostgreSQL 17.11 used a temporary data directory and Unix socket with TCP disabled. Results matched on both versions: 13 tables, two ledger rows, seed row, constraints/FKs/indexes, runtime role flags, grants/RLS behavior, receipt and export constraints, migration checksum drift rejection, and synthetic archive/restore tests.

The complete Python suite passed **20/20** with both `.venv/bin/python -m pytest -q` and `.venv/bin/pytest -q`. The first sandboxed database-test attempt could not create local PostgreSQL shared memory; the rerun with permission for disposable local clusters passed. No test contacted Supabase or Orvix. The real Supabase logical backup restore separately passed on local PostgreSQL 17.11: 31/31 included relation counts matched (all zero rows). It is not evidence that excluded platform state is recoverable.

## Application-scoped recovery objective

At the latest read-only inventory, Moobby schemas, tables, and runtime role were absent. The migration therefore has no existing Moobby rows to recover. Recovery objective for this installation proposal: **preserve all pre-existing Supabase data and objects unchanged; create no committed partial version of either migration; if a transaction fails, roll that migration transaction back; after a successful commit, preserve the failed state for diagnosis and require an explicitly reviewed corrective migration.** No numeric recovery-time objective is claimed.

This objective covers only the new `collection`, `processing`, and `archive` objects and the proposed `moobby_runtime` role. It excludes all Supabase-managed schemas, the existing role graph, provider/API configuration, Storage bytes, and the eight omitted relation datasets. Because the scripts are additive but not self-reversing, dropping newly created schemas or a role is a destructive action requiring separate approval. The local backup is a partial platform dump and is not the rollback mechanism for Moobby objects that do not yet exist.

## Exact migration files and proposed effects

Recompute these hashes immediately before any approved execution and stop on any mismatch:

| Order | File | SHA-256 | Proposed effect |
|---:|---|---|---|
| 1 | `migrations/0001_collection_processing_archive.sql` | `9305b2ed84db9b9184cea0569b6ea9aafd80f38817dc84757ddac22f19b65737` | Create schemas `collection`, `processing`, `archive`; create `collection.schema_migrations` and 12 domain tables; constraints, indexes, FKs, comments; seed only `x:commuterline`. |
| 2 | `migrations/0002_runtime_role_and_grants.sql` | `24494ed9f98d8be3a849711959974ba4624a7f4e518f3fb53f7e6304c8701d30` | Create `moobby_runtime` without a password; revoke `PUBLIC`, `anon`, and `authenticated` on the three new schemas/tables; grant explicit runtime access; enable RLS and add runtime policies to all 13 tables. |

The exact 13 tables, grants/RLS, transactional ledger procedure, validation, and recovery steps are in [stage5-installation-proposal.md](stage5-installation-proposal.md). No `public`, `auth`, `storage`, `realtime`, or other Supabase-managed object is in scope. No DELETE grant or purge path is proposed.

## Decisions and blockers before approval

SPEC-backed choices are fixed in the draft: only `x:commuterline` is the monitored profile (§4); author identity is separate from profile sources (§4/§9); raw post identity, capture snapshot, and collection observation remain separate (§5/§9); LLM request and response content use CSV (§10.4); payloads qualify for retention only after verified export and hashes/receipts remain (§4/§12); human review must not overwrite original LLM labels (§12); and purge is not enabled (§12.2). No Transit or Operations tables are included.

Owner decisions remain for implementation details not fixed in SPEC:

- accept or revise `discovered_authors` keyed by stable external author ID, with mutable handle/display name;
- accept run method (`profile`/`search`), collection mode (`live`/`historical`), `partial` semantics, and stop-reason vocabulary;
- confirm request/response CSV and raw payload retention through verified export and approve a separate future retention process;
- accept one job per snapshot/pipeline version, append-only numbered attempts, and at most one successful attempt; job/attempt consistency remains application-enforced;
- accept same-UUID/same-digest idempotency and reject same-UUID/different-digest in uploader logic;
- decide whether export transitions, immutable membership, and checksum/count checks need database triggers or remain application-enforced;
- select migration owner and out-of-band password procedure for the new runtime role;
- confirm future JSONL exports retain original LLM labels and separate human review labels;
- accept that current recovery evidence excludes the platform state listed above, or arrange a separate platform-level recovery plan.

Deployment blockers are: confirm the exact exposed-schema list in Supabase Dashboard and ensure all three application schemas stay unexposed; accept the remaining DDL assumptions; arrange the runtime password out of band; take and rehearse a fresh backup immediately before installation; rerun target/object/role/membership/grant checks immediately before execution; and provide separate explicit approval for the exact target and hashes. The role dump is incomplete and must not be replayed; the eight omitted platform relations must not be manually restored by these migrations.

## Approval boundary

The complete proposal is reviewable in [stage5-installation-proposal.md](stage5-installation-proposal.md). This report does not execute SQL. The next authorized step, if approved, is only the separately scoped live installation described there; any reset, drop, purge, managed-object restore, or remote access-control change requires its own explicit approval.
