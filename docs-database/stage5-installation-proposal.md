# Stage 5 live migration installation record

**Status: executed within the owner's exact authorization on 2026-10-22.** Only the two listed migrations were applied to the confirmed target. No reset, purge, role adoption, or changes to Supabase-managed schemas occurred. See [final-migration-readiness.md](final-migration-readiness.md) for actual results and the remaining runtime credential check.

## 1. Target confirmation

Last read-only pre-install inspection: 2026-10-22. Target hint: `host=aws-0-ap-northeast-1.pooler.supabase.com; project_ref=vgy…ug`; server PostgreSQL 17.11; `current_user=postgres`; transaction confirmed `read_only=on`. Before execution the masked hint was checked again and matched. The migration connections required TLS with a five-second timeout; client TLS was verified with libpq `ssl_in_use=True`.

## 2. Exact affected objects

Current inspection found no name collisions. The following are the only proposed new objects:

- Schemas: `collection`, `processing`, `archive`.
- Tables (13): `collection.schema_migrations`, `collection.sources`, `collection.discovered_authors`, `collection.collection_runs`, `collection.raw_contents`, `collection.raw_snapshots`, `collection.content_observations`, `processing.processing_jobs`, `processing.llm_attempts`, `archive.processed_fingerprints`, `archive.run_receipts`, `archive.export_batches`, `archive.export_items`.
- Role: `moobby_runtime`, LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOREPLICATION, NOBYPASSRLS. The migration file has no password. Set it out of band only after the owner approves the role and secret-management procedure.
- Seed: one `collection.sources` row: platform `x`, handle `commuterline`.
- Ledger: versions 1 and 2 in `collection.schema_migrations`, each recording the exact migration filename and SHA-256 in the same transaction as its SQL.

No existing objects are dropped, reset, renamed, or truncated. No object in `public`, `auth`, `storage`, `realtime`, `extensions`, `graphql`, `graphql_public`, `pgbouncer`, `vault`, or another Supabase-managed namespace is changed. In particular, the eight existing managed-schema triggers and the platform role graph remain untouched. There is no grant to DELETE and no purge operation.

## 3. Migration order and checksums

Recalculate SHA-256 from the exact file bytes immediately before execution. Abort on any mismatch; do not edit a reviewed file and reuse its version.

| Version | File | SHA-256 |
|---:|---|---|
| 1 | `migrations/0001_collection_processing_archive.sql` | `9305b2ed84db9b9184cea0569b6ea9aafd80f38817dc84757ddac22f19b65737` |
| 2 | `migrations/0002_runtime_role_and_grants.sql` | `24494ed9f98d8be3a849711959974ba4624a7f4e518f3fb53f7e6304c8701d30` |

Apply v1 in a transaction and insert its ledger row before commit. Read the ledger, validate the contiguous prefix/name/checksum using `moobby.migration_ledger.pending_migrations`, then apply v2 and its ledger row in a second transaction. Never run a migration whose recorded hash or name differs; prepare a new numbered migration after review. The local tests do not authorize or perform remote execution.

## 4. Runtime grants and RLS in the reviewed SQL

Version 2 revokes `PUBLIC`, `anon`, and `authenticated` privileges only on the three newly created schemas and their tables. It grants schema USAGE to `moobby_runtime`, with explicit SELECT/INSERT and column-limited UPDATE on the tables needed by the pipeline. The migration enables RLS on all 13 tables and creates policies for the runtime role. It grants no schema/table DELETE, DDL, role management, database creation, replication, or RLS bypass. `sources` and the migration ledger are read-only for runtime. `moobby_runtime` has no memberships at creation and NOINHERIT.

The project Data API is enabled. On 2026-10-22, the owner reported the Dashboard → Project Settings → API → Exposed schemas list as exactly `graphql_public`, `public`; this excludes `collection`, `processing`, and `archive`. This is owner-confirmed, not independently inspected through a connected Dashboard. Reconfirm the list immediately before execution. SQL grants and RLS do not substitute for this check. If an application schema is exposed, stop; any setting change is a separate reviewed remote change and is not included here.

### Runtime credential setup (owner operated)

The migration creates `moobby_runtime` without a password. After the migration is approved and the role exists, the owner should set its password from an interactive `psql` session using a TLS-protected administrative service definition/passfile or an approved secret manager. Run `\password moobby_runtime` at the `psql` prompt; enter the password only at the hidden prompts. Do not put it in SQL source, shell arguments/history, logs, or chat. The owner then obtains the runtime Session Pooler URI from the confirmed project's Dashboard Connect settings, using the new role, and puts that URI in the local Git-ignored `.env` as `DATABASE_URL`. Keep `.env` mode `0600`, verify `git check-ignore .env`, and never print the URI. Keep administrative credentials separate from the application's `DATABASE_URL`. The owner retains and stores the password; the agent will not request or receive it.

## 5. Preconditions and execution checklist

Before any live run, the owner/operator must complete and record each item:

1. Explicitly approve this target and the two exact hashes above.
2. Confirm the current Dashboard project ref and compare the masked target hint. Confirm PostgreSQL 17 compatibility and TLS.
3. Capture a fresh read-only R0 inventory. Confirm all three schemas and `moobby_runtime` are absent; check role membership, inherited access, ownership, grants, policies, and object dependencies. Stop on any collision; do not adopt an existing object.
4. Confirm `anon` and `authenticated` exist and inspect their current project role configuration read-only. Do not modify their memberships.
5. Confirm exposed schemas exclude the three new names. Record the exact list outside secrets.
6. Pause only the owner-approved application writers relevant to the target. Create a fresh backup for the agreed scope and complete isolated restore/rehearsal. The existing CLI bundle is a partial platform dump and not a whole-project recovery point.
7. Accept or revise the unresolved schema choices listed in [final-migration-readiness.md](final-migration-readiness.md). Confirm migration owner and out-of-band runtime password procedure.
8. Recompute hashes, record the operator, timestamp, target hint, and change window. Keep credentials out of shell history/output.
9. Execute migration 0001 transaction plus ledger insert; verify commit and read the ledger. Then validate the checksum/sequence again before executing migration 0002 transaction plus ledger insert.
10. Run post-migration checks below. Stop writers and preserve the resulting state if any check fails. Do not automatically retry, drop schemas, or change managed objects.

## 6. Post-migration validation

Use read-only checks unless a test write is separately approved and isolated from live data. Verify:

- Exactly the 13 listed tables exist in the three new schemas; no unrelated schema/object changed.
- Ledger rows are exactly versions 1 and 2 with the approved names and byte-level hashes.
- Exactly one profile source seed exists: `x:commuterline`.
- Expected primary/unique/check constraints, indexes, and foreign keys exist, including the `(snapshot_id, content_id)` observation FK and the one-success-per-job partial unique index.
- RLS is enabled on all 13 tables; expected runtime policy definitions exist; `anon`/`authenticated` lack schema/table privileges and cannot reach these schemas through the Data API.
- The runtime role flags are restricted, password setup is completed through the approved secret channel, and it has no memberships or unintended inherited privileges.
- Grants equal the reviewed table/column list, with no DELETE, DDL, ownership, role management, or RLS bypass.
- Supabase-managed schemas, the eight observed triggers, platform roles, and existing objects match the pre-run inventory.

The isolated PostgreSQL 17.11/18.4 integration tests establish behavior in those local test clusters, not live Supabase role inheritance or Data API behavior. Avoid live row mutations for permission tests unless the owner separately approves a safe, isolated fixture protocol.

**Export enforcement boundary:** the approved SQL files constrain allowed status values, required lifecycle timestamps, and duplicate batch/job membership. They do not enforce forward-only transitions, immutable membership after preparation, matching record counts/checksums, or purge dependency checks. The accepted policy is that these checks are enforced by application transactions in a later implementation; purge remains disabled and has no DELETE grant. If database-level enforcement is required at installation time, do not apply these hashes: design, rehearse, and review a new numbered migration first.

## 7. Recovery objective and procedure

**Scope:** protect the pre-installation application state only. The latest inventory showed no Moobby schemas/tables or runtime role, so there are no existing Moobby rows to lose. Preserve every pre-existing platform/application object unchanged. Each migration and ledger insert is atomic as one transaction; a failed transaction must roll back fully. No numeric RTO is asserted.

If a transaction fails, stop and retain redacted diagnostics. Do not run the next migration. If a migration commits but its post-check fails, stop all relevant writers and preserve the database as-is for review. The migrations are additive and not self-reversing. A corrective migration may be prepared after diagnosis. Dropping the three schemas or `moobby_runtime` is destructive and requires separate explicit approval; it is not an automatic rollback.

The verified CLI files are at `/Users/nfahrisalim/Documents/Moobby-backups/moobby-supabase-backup-20261021T234448Z` on the local FileVault-encrypted APFS Data volume, with directory mode 0700 and files mode 0600. Their SHA-256 values match the temporary originals. The original remains in `/private/tmp`. This is a local partial logical dump, not offsite storage or whole-project disaster recovery. It omits eight catalog relations (247 rows), the complete role/membership graph, provider settings, Data API configuration, and Storage object bytes. Do not replay its role file or restore its managed objects as part of this proposal. The application-scoped migration recovery objective does not claim those omissions are recovered.

## 8. Owner decisions and approval record

The owner has accepted the schema/grant proposals listed in the readiness report, including discovered author separation, profile/search methods, live/historical modes, `partial` status, payload retention through verified export, job/attempt uniqueness, receipt retry comparison, the restricted role/RLS design, and no purge. The owner also supplied the exposed-schema list recorded above and confirmed they will set/store the runtime password and keep the runtime URI in local `.env`.

The owner confirmed that export lifecycle checks will be enforced by later application transactions and approved exact installation of migrations 0001 and 0002 at the named target. Both transactions committed with their ledger rows. The partial backup/recovery scope and no-purge/no-managed-object-change boundary remain as documented. Runtime credential setup is pending and owner-operated.

**Execution result:** authorization was received in the conversation on 2026-10-22. Both migrations and subsequent restricted-runtime verification passed. No further remote schema change is authorized by this record. The runtime password and URI remain owner-managed and are not recorded here.
