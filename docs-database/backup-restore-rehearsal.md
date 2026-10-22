# Backup, restore, and isolated migration rehearsal plan

## Purpose

This is the procedure for SPEC §8 R1–R3. On 2026-10-22, the official Supabase CLI role/schema/data dump was run against the confirmed target and restored to an isolated local Supabase stack. No migration, reset, or live access change was performed. The CLI dump and successful restore cover only the included SQL scope; they do not prove full-project recovery. See [backup-restore-verification.md](backup-restore-verification.md).

## Stage 4 verification status

The isolated synthetic Moobby archive exercise remains covered by `tests/test_migrations_postgres.py` on PostgreSQL **17.11** and **18.4**. In addition, Docker Engine **29.6.1** and Supabase CLI **2.121.0** were verified and the official Supabase CLI dump was run. Its three files restored in one transaction into a local Supabase CLI stack on PostgreSQL **17.11**. Exact row counts matched for all 31 relations present in `data.sql`; each had zero rows. The source had 39 catalog tables, with eight relations absent from the dump and 247 rows in those omitted tables. The actual CLI restore is therefore verified for the produced files but is not a complete project recovery point. Details, checksums, omissions, and owner actions are in [backup-restore-verification.md](backup-restore-verification.md). See [final-migration-readiness.md](final-migration-readiness.md) for current deployment blockers.

## Before backup (R1)

1. Confirm the Supabase project ref and environment from the masked target with the owner. Re-run the read-only inventory immediately before backup. Record schemas, objects, dependencies, migration history, roles/memberships, schema and table grants, RLS/policies, exposed-schema settings, exact row counts for in-scope application tables, and object definitions.
2. Identify which data and objects belong to Moobby versus other applications. Do not include or modify Supabase-managed `auth`, `storage`, `realtime`, or other platform schemas unless the owner explicitly defines a recovery requirement.
3. Schedule a write pause. Stop local pipeline writers and verify no other writer is changing the in-scope data. Record the pause time and the last accepted run/receipt.
4. Use the owner-approved Supabase backup/export mechanism or PostgreSQL client in a controlled terminal. Supply credentials via a protected service file/passfile or approved secret manager; do not put a URI/password in shell arguments, command history, logs, tickets, or this repository. Keep TLS verification enabled according to the approved connection method.
5. Back up DDL, data, ownership/grants/policies needed to restore the in-scope application objects, and the project’s configuration metadata needed for access review. Keep the backup encrypted at rest, access-limited, and outside the repository. Do not put X session files, `.env`, or unredacted logs in the backup bundle.
6. Generate a manifest containing target project ref (masked in ordinary reports), UTC capture time, included/excluded schemas and objects, file byte sizes, SHA-256 checksums, exact per-table row counts, and tool/version details. Store the manifest with the backup in the protected backup location.
7. Verify checksums and test that the backup archive can be listed/read. A successful dump command alone is not backup verification.

### Example command sequence (after service definitions and scope review)

Configure protected PostgreSQL service entries named `moobby_backup` and `moobby_rehearsal` in the operator’s PostgreSQL service file, with TLS verification, the correct host/database/user, and a protected `passfile` (or an approved secret manager). Do not put credentials in the commands below. These examples are not approved targets. They include only the proposed Moobby schemas; the current R0 inventory found these schemas absent, so the dump command must not be run until a fresh inventory confirms the exact existing scope. Add a `--schema` flag only for each additional owner-approved application schema.

```sh
export BACKUP_DIR="/secure/path/moobby-backup-YYYYMMDD"
mkdir -m 700 -p "$BACKUP_DIR"
pg_dump --dbname="service=moobby_backup" --format=custom \
  --schema=collection --schema=processing --schema=archive \
  --file="$BACKUP_DIR/moobby.dump"
pg_restore --list "$BACKUP_DIR/moobby.dump" > "$BACKUP_DIR/archive-list.txt"
sha256sum "$BACKUP_DIR/moobby.dump" > "$BACKUP_DIR/SHA256SUMS"
sha256sum --check "$BACKUP_DIR/SHA256SUMS"
```

Restore only into a newly provisioned isolated database. Review the service target first; omit `--clean` so the command cannot drop objects in a non-empty target.

```sh
pg_restore --dbname="service=moobby_rehearsal" \
  --exit-on-error --single-transaction "$BACKUP_DIR/moobby.dump"
```

Capture exact row counts and compare them to the manifest using an owner-reviewed, read-only SQL report. The custom dump and restore commands do not themselves prove that provider-specific API exposure or secrets/configuration were backed up.

## Restore rehearsal (R3)

1. Provision a separate isolated Supabase project or PostgreSQL instance with no production credentials, no application writers, and no route to the live database. Never use the live project as the rehearsal target.
2. Restore the backup into the isolated target using a dedicated rehearsal identity. Review the generated command and target before execution. Restore only the approved schemas/data/configuration; omit managed platform schemas unless the isolated provider requires them and the owner approves.
3. Compare restored object inventory and exact row counts to the backup manifest. Check constraints, FK integrity, views/functions, grants, role memberships, RLS/policies, and exposed-schema configuration. Document provider-specific settings that cannot be restored by SQL.
4. Preserve the restored baseline. Create a second clean isolated database/project for migration rehearsal, or reset only the isolated rehearsal database after confirming it contains no needed backup data. Apply the numbered draft migrations there through the proposed migration process.
5. Validate the expected tables/constraints/indexes, the `x:commuterline` seed, RLS and grants, role capability boundaries, digest mismatch handling, restart/retry behavior, CSV payload retention, verified export lifecycle, and retention dependency checks. Use synthetic fixtures only; do not copy real post text into a test artifact.
6. Apply the drafts only on a clean isolated database after reviewing target and files:

   ```sh
   psql --dbname="service=moobby_rehearsal" --no-psqlrc \
     --set ON_ERROR_STOP=1 --file=migrations/0001_collection_processing_archive.sql
   psql --dbname="service=moobby_rehearsal" --no-psqlrc \
     --set ON_ERROR_STOP=1 --file=migrations/0002_runtime_role_and_grants.sql
   ```

   The role has no password in the SQL. Set any rehearsal password out of band and never reuse a production password.
7. Test a rollback by discarding/recreating only the isolated rehearsal target from the verified backup. Compare the restored manifest again. Record commands, versions, outputs, and deviations without secrets.

## Stop gates before live migration (R4/R5)

No live migration is ready until all of these are complete:

- owner confirms the target and exact in-scope objects after a fresh R0 inventory;
- schema proposals and open decisions are reviewed, including author identity, enum contracts, receipt behavior, payload retention/purge, and export transition enforcement;
- backup manifest and checksum verification are complete;
- isolated restore and migration rehearsal pass;
- grants, role inheritance, RLS policy behavior, and Data API exposure are reviewed;
- migration owner supplies an out-of-band runtime password and verifies any role-name collision without changing an existing role;
- a concrete migration plan shows exact target, SQL files/checksums, resulting objects, data effects, and recovery steps;
- owner explicitly approves the live migration plan.

Do not run reset SQL as part of this plan. Any destructive reset or purge requires a separate decision and approval tied to a concrete object/data list.

## Recovery outline

If a rehearsal fails, stop writers in the isolated environment, retain the verified backup, discard only the isolated failed target, and recreate it from the backup. For any future live incident, stop all writers, preserve the original backup and logs, restore only the approved objects into the agreed recovery target, and compare counts, keys, and FK relationships before resuming. Do not promise transactional rollback for multi-step provider operations.
