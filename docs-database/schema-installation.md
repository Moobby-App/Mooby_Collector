# Schema installation and migration rehearsal

## Purpose

This document records the installation contract and actual Stage 5 execution for `migrations/0001_collection_processing_archive.sql` and `migrations/0002_runtime_role_and_grants.sql`. The owner authorized exactly these hashes for the confirmed target; both were applied successfully to PostgreSQL 17.11 in separate transactions, each with its ledger row inserted before commit. No reset, purge, or Supabase-managed object change occurred. See [final-migration-readiness.md](final-migration-readiness.md) for verification and remaining runtime credential actions.

## Inputs, outputs, and dependencies

Inputs are the two numbered SQL files and their exact byte-level SHA-256 checksums. Migration 0001 creates the `collection`, `processing`, and `archive` schemas and the `collection.schema_migrations` ledger. Migration 0002 creates `moobby_runtime`, grants the draft access, enables RLS, and installs policies. The runtime password is not stored in the SQL and must be set out of band after a separate review.

The migration operator needs an administrative connection able to create schemas and roles, PostgreSQL client or psycopg, the exact target environment, and a verified backup. The application runtime role is not a migration identity. `main.py` remains the application pipeline entry point; this migration process is an administrative operation.

`moobby.migration_ledger` provides pure local-file hash and history validation. It does not connect, execute SQL, or apply migrations. Before any migration SQL is executed, pass the local `MigrationFile` list and the database ledger rows to `pending_migrations`. It returns only missing versions; it raises `MigrationDriftError` on an unknown database version, out-of-order history, name mismatch, missing checksum, or changed file checksum. A repeated recorded version is therefore not treated as pending. The ledger primary key rejects duplicate versions, `NOT NULL` rejects rows without checksums, and applying DDL plus its ledger row in one transaction prevents a committed but untracked migration when this procedure is followed.

## Installation transaction procedure

This is the process verified by the isolated integration harness and followed during the approved live installation.

1. Confirm the target and verify that a current backup and isolated rehearsal exist.
2. Read `collection.schema_migrations` if it exists. For a fresh schema, there is no ledger yet and only migration 0001 is eligible.
3. Compute SHA-256 from the exact bytes of the pending migration file. Do not edit the file after computing the checksum.
4. In one transaction, execute the pending migration SQL, then insert `(version, name, checksum_sha256)` into `collection.schema_migrations`. Commit only if both operations succeed. On failure, roll back the complete transaction.
5. Before the next version or any retry, fetch the ledger and call `pending_migrations` again. Never execute a file whose version is already recorded. If a recorded checksum differs from the local file, stop and prepare a new numbered migration instead of editing/replaying the old one.
6. Verify the resulting table/index/constraint definitions, grants, RLS policies, and ledger checksums against the rehearsal manifest.

For this target, version 1 created the ledger and recorded itself in the same transaction; version 2 was then applied and recorded in a second transaction. Do not apply the SQL files directly with `psql -f` without the ledger insert, because that would leave an untracked schema. The automated tests perform this procedure with local psycopg connections and exact file hashes.

## Recovery procedure

The migrations are additive drafts but are not self-reversing or directly rerunnable. Do not write a drop-schema rollback and run it automatically. If an isolated rehearsal fails, stop the harness, retain its log, discard only that disposable local cluster, and create a fresh cluster for the next run.

Before any future live migration, keep the verified backup and manifest outside the repository. The current CLI files have been copied to FileVault-encrypted local APFS storage and hash-verified, but they are a partial platform dump, not a whole-project recovery point. If a live migration is later approved and fails, stop relevant writers, preserve the failed database for diagnosis, and follow the app-scoped recovery objective in [stage5-installation-proposal.md](stage5-installation-proposal.md). Do not restore or modify Supabase-managed schemas/roles as part of this Moobby-only proposal.

Payload purge is not installed or enabled by these migrations. The runtime role has no DELETE grant. Do not add a purge procedure/role until export verification, local backup retention, and all dependent event/review references have a separately reviewed design.

## Isolated validation results

- Environment: macOS, Homebrew PostgreSQL **17.11** and **18.4**, each using a temporary data directory and Unix-domain socket under the OS temporary directory; TCP listening disabled. The harness does not read `.env` or `DATABASE_URL`. PostgreSQL 17.11 was explicitly selected through `PATH`, and the temporary server's `SHOW server_version` value was asserted as 17.11. Docker Engine 29.6.1 and Supabase CLI 2.121.0 were also used for a project logical dump and isolated local Supabase restore on PostgreSQL 17.11; see the backup verification report for exclusions.
- Migrations: both files executed in order inside transactions. The seeded source and two migration ledger rows were verified.
- SQL checks: 13 tables, composite snapshot/content FK, partial unique success index, CHECK constraints, unique constraints, and foreign keys were validated by PostgreSQL and exercised by integration tests. The live inventory count of 136 constraints is unrelated to the local draft count; local assertions are listed by behavior in `tests/test_migrations_postgres.py`.
- Access checks: `moobby_runtime` can read the source registry and insert a discovered author under RLS. It has no superuser, database/role creation, RLS bypass, inherited role membership, raw-text update, DELETE, or DDL rights. `anon` and `authenticated` cannot select the Moobby source table.
- Invariant checks: unique content identity, composite observation ownership, unique processing job, processing lease requirement, unique attempt number, at most one successful LLM attempt per job, nullable token usage, unique run receipt, export-item uniqueness, and required export timestamps.
- Version/checksum checks: the ledger requires non-null SHA-256; the local checksum helper accepts the recorded file hash, reports no pending migrations, rejects a changed file checksum, and rejects a duplicate version row.
- Automated integration result (Stage 4 rerun): four PostgreSQL integration tests passed on both PostgreSQL 17.11 and 18.4, including role collision and ownership checks plus a synthetic custom-format dump, TOC listing, SHA-256/byte-size manifest, exact per-table counts, and restore into a second isolated database. The 17.11 full suite passed 20 tests. Full commands and limitations are recorded in [final-migration-readiness.md](final-migration-readiness.md).

## Remaining limitations and assumptions

- Live installation and restricted runtime validation are complete for the two approved migrations. The owner-configured runtime connection authenticated as `moobby_runtime`; read-only and transactional smoke checks passed. Preflight passed using the runtime connection.
- Remote catalog checks confirmed the exact 13 tables, two checksummed ledger rows, source seed, 13 enabled RLS tables, 13 policies, no `anon`/`authenticated` schema/table access, and the restricted runtime role flags. Client TLS was confirmed through libpq; `pg_stat_ssl` described the pooler-to-server side and reported false, so it was not used as the client TLS indicator.

- The project owner supplied target PostgreSQL version **17.11**. Migration syntax, ledger behavior, grants/RLS, constraints, and the synthetic backup/restore tests now pass on local PostgreSQL 17.11. This does not prove Supabase-specific behavior or prove the actual Supabase project backup is recoverable.
- The pure checksum helper must be invoked by a migration operator before SQL execution. There is no general remote migration runner in this stage. Add a controlled migration runner only after the live deployment procedure and approval boundary are agreed.
- Supabase Data API exposed-schema settings and provider-specific role behavior are not represented by local PostgreSQL. The owner reported the Dashboard list as exactly `graphql_public`, `public`, excluding the Moobby schemas; this report is owner-confirmed, not independently inspected from a connected Dashboard, and must be reconfirmed immediately before deployment.
- The actual logical dump restored all 31 included relations with exact row counts, but excludes eight inventoried relations, role/membership state, provider configuration, Data API settings, and Storage object bytes. It is not whole-project disaster recovery and is not a substitute for a fresh backup/rehearsal immediately before installation.
- No tests enable purge, delete rows, or alter remote objects.

## Live installation status and remaining owner action

The approved installation is complete for migrations 0001 and 0002. The target, byte-level checksums, two transaction commits, ledger, 13 tables, source seed, runtime flags/grants, RLS/policies, and absence of `anon`/`authenticated` privileges were verified after installation. No migration SQL was changed. The pre-install backup limitations and application-scoped recovery objective above still apply.

The owner operated the interactive `psql \password moobby_runtime` procedure and configured the restricted runtime Session Pooler URI in Git-ignored `.env` with mode `0600`. The live login, preflight, grants, denied operations, and rollback-only fixture test passed as documented in [runtime-credentials-and-smoke-test.md](runtime-credentials-and-smoke-test.md). No further remote SQL is needed for these migrations. Stage 6 has not been started.
