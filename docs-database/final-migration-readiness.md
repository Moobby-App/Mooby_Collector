# Final migration readiness and Stage 5 installation record

## Stage 5 live installation result (2026-10-22)

**The two approved migrations were applied to the confirmed target.** The owner explicitly authorized only versions 1 and 2 for `host=aws-0-ap-northeast-1.pooler.supabase.com; project_ref=vgy…ug`. The connection used client TLS (`sslmode=require` and libpq `ssl_in_use=True`), a five-second connect timeout, and PostgreSQL 17.11. An initial version-1 attempt rolled back completely because the server-side `pg_stat_ssl` view showed the pooler backend as non-TLS; client TLS was then verified directly and version 1 committed on a repeat. No objects from that attempt remained after rollback.

| Version | File | SHA-256 | Result |
|---:|---|---|---|
| 1 | `0001_collection_processing_archive.sql` | `9305b2ed84db9b9184cea0569b6ea9aafd80f38817dc84757ddac22f19b65737` | Committed with ledger row in the same transaction |
| 2 | `0002_runtime_role_and_grants.sql` | `24494ed9f98d8be3a849711959974ba4624a7f4e518f3fb53f7e6304c8701d30` | Committed with ledger row in the same transaction |

Post-install catalog validation found exactly the three intended schemas and 13 intended tables, exactly ledger versions 1 and 2 with the hashes above, and exactly one `x:commuterline` seed row. RLS was enabled on 13/13 tables with 13 policies. `anon` and `authenticated` had no schema or table privileges on these schemas. `moobby_runtime` has LOGIN and none of SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS, or INHERIT; it has no memberships, owns no application tables, and has no DELETE or schema CREATE privilege. No app triggers were created. The existing managed-schema inventory was not modified.

After the owner set the password interactively and configured local `.env`, `env -u DATABASE_URL ./.venv/bin/python main.py preflight` passed as `moobby_runtime`. The rollback-only live smoke test passed permitted SELECT/INSERT/column UPDATE and denied DDL/DELETE checks. A follow-up read-only runtime query confirmed client TLS, the expected grants/policies, and no leftover fixture data. No credential was requested, received, or printed. See [runtime-credentials-and-smoke-test.md](runtime-credentials-and-smoke-test.md) for evidence.

Both local test entry points passed after allowing the integration harness to create its disposable PostgreSQL cluster: `.venv/bin/python -m pytest -q` — **20 passed**; `.venv/bin/pytest -q` — **20 passed**. The first sandboxed run had 16 passed and 4 setup errors because the sandbox blocked PostgreSQL shared memory; the elevated reruns used only disposable local clusters.

The owner-confirmed Data API exposed schemas remain `graphql_public`, `public`; they exclude all three Moobby schemas. This was not independently read from a connected Dashboard. Export monotonicity, frozen membership, exact checksum/count matching, and purge dependency checks remain application-enforced future work as accepted by the owner; purge remains disabled. Do not proceed to Stage 6 until the runtime credential setup and runtime access validation are complete.

## Historical pre-installation readiness record

### Status when the pre-install approval package was prepared

**At that earlier point the approval package was prepared and live installation had not yet been authorized.** No migration or managed-schema modification had then been performed. PostgreSQL 17.11 rehearsal passed. The Supabase CLI logical dump was restored to an isolated Supabase CLI stack on PostgreSQL 17.11 with exact counts matching for all 31 included relations. Its five dump/manifest files were copied to a persistent FileVault-encrypted local APFS volume outside the repository and temporary directories; all destination hashes match and the source copy remains intact. See [backup-restore-verification.md](backup-restore-verification.md) for the scope and limitations. The later execution is recorded at the top of this document.

The backup is **not a whole-project recovery point**. Eight inventoried managed relations (247 rows, all in three platform migration-history tables) are absent from its data dump; the role file does not recreate the 30-role/24-membership catalog. Provider and Data API settings, Storage object bytes, and other dashboard configuration are not included. None of these omitted objects were altered. The current application-scoped recovery objective is limited to Moobby’s presently absent schemas and role; it does not depend on restoring platform objects. A fresh backup and rehearsal of the agreed scope remain mandatory before installation.

## Read-only managed-object review

On 2026-10-22, a TLS connection to the previously confirmed masked target was opened with `connect_timeout=5`; the server reported PostgreSQL 17.11 and `transaction_read_only=on` before catalog SELECTs. The query found eight non-internal triggers in managed schemas: one on `realtime.subscription`, five on `storage.buckets`, and two on `storage.objects`. Their trigger functions are in the corresponding `realtime`/`storage` schemas. The catalog showed zero visible policies. Five extensions were installed: `pg_stat_statements` 1.11, `pgcrypto` 1.3, `plpgsql` 1.0, `supabase_vault` 0.3.1, and `uuid-ossp` 1.1. No public relations or public functions were listed. No `collection`, `processing`, or `archive` namespace and no `moobby_runtime` role or membership were present.

These are catalog observations only. The eight triggers are retained exactly as found; this inspection does not determine whether each is stock or owner-customized. The owner reported the Dashboard Exposed schemas list as `graphql_public`, `public`, excluding all three Moobby schemas; this report is owner-confirmed and not independently inspected through a connected Dashboard. Other provider-level settings remain unverified. Managed migration rows and role definitions were not replayed or changed. Reconcile them by keeping them outside this Moobby-only proposal and acknowledging the partial backup scope; any platform-level recovery is a separate owner decision.

## PostgreSQL rehearsal and automated tests

Both numbered migrations and the integration harness were run in isolated PostgreSQL 17.11 and 18.4 clusters. PostgreSQL 17.11 used a temporary data directory and Unix socket with TCP disabled. Results matched on both versions: 13 tables, two ledger rows, seed row, constraints/FKs/indexes, runtime role flags, grants/RLS behavior, receipt and export constraints, migration checksum drift rejection, and synthetic archive/restore tests.

After runtime configuration, the complete Python suite passed **20/20** with `env -u DATABASE_URL ./.venv/bin/python -m pytest -q` and **20/20** with `env -u DATABASE_URL ./.venv/bin/pytest -q`. The tests use disposable local PostgreSQL and do not write to Supabase. No test contacted Orvix. The real Supabase logical backup restore separately passed on local PostgreSQL 17.11: 31/31 included relation counts matched (all zero rows). It is not evidence that excluded platform state is recoverable.

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

The owner accepted the schema and restricted-grant proposals in a reply on 2026-10-22: discovered authors remain separate with stable IDs where available; run methods are `profile`/`search`; modes are `live`/`historical`; `partial` is accepted; raw and CSV payloads stay through verified export; processing jobs are unique per snapshot/pipeline with controlled leases/retries; attempts are append-only with at most one accepted success; same UUID/digest retries are idempotent and a different digest is rejected; runtime remains restricted with RLS and no DELETE; purge stays disabled.

One implementation boundary still needs confirmation before final execution approval. The accepted export requirements include forward-only transitions, frozen membership, checksum/count verification, and dependency checks before any purge. Migrations 0001/0002 constrain allowed statuses, required timestamps, and unique batch/job membership only; they do not implement the other checks. The proposal places those checks in later application transactions, with purge disabled. If database-level enforcement is required now, these hashes are insufficient and must be redesigned/rehearsed.

The owner set and stored the `moobby_runtime` password and provided the runtime URI through local `.env`. The secure procedure and verification record are in [runtime-credentials-and-smoke-test.md](runtime-credentials-and-smoke-test.md); `.env` is ignored and its mode is `0600`. The password and URI were neither requested nor read.

No other owner decisions remain for the choices above. Human review labels remain future work: this schema stage adds no review table, and later exports must preserve original LLM labels separately as required by SPEC.

Deployment gates are: reconfirm the exposed-schema list immediately before execution; confirm application-level enforcement for export lifecycle checks or request a new DB design; arrange owner-operated password setup and obtain the runtime URI without sharing it; validate the reviewed hashes and repeat target/object/role/membership/grant checks immediately before execution; and provide separate explicit approval for the exact target and hashes. The role dump is incomplete and must not be replayed; the eight omitted platform relations must not be manually restored by these migrations.

## Approval boundary

The complete proposal is reviewable in [stage5-installation-proposal.md](stage5-installation-proposal.md). This report does not execute SQL. The next authorized step, if approved, is only the separately scoped live installation described there; any reset, drop, purge, managed-object restore, or remote access-control change requires its own explicit approval.
