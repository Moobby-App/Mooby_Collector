# Supabase logical backup and restore verification

## Result

At **2026-10-21 23:44:48 UTC** (2026-10-22 06:44:48 Asia/Jakarta), the official Supabase CLI logical dump was run against the owner-confirmed project target (`host=aws-0-ap-northeast-1.pooler.supabase.com; project_ref=vgy…ug`). The run used Supabase CLI **2.121.0**, Docker Engine **29.6.1**, and source PostgreSQL **17.11**. The existing `scripts/db_inventory.py` and follow-up catalog/count queries ran in explicitly read-only transactions. No live schema, role, grant, policy, RLS, or data changes were made.

All three dump files restored successfully in one transaction into a temporary, unlinked Supabase CLI local stack running PostgreSQL **17.11**. Exact row counts for all 31 relations represented by `COPY` statements matched the backup: **31 tables, 0 rows**. Source `count(*)` values for those relations also matched. The restore required the local `supabase_admin` role; the local `postgres` login is not a superuser and its first restore attempt rolled back with `permission denied for parameter log_min_messages`.

This verifies the produced logical files and their restorable contents against a compatible local Supabase stack. It does **not** establish full-project recoverability: the SQL dump omits some catalog tables and does not carry provider configuration or Storage object bytes.

On 2026-10-22, the five backup/manifest files were copied to `/Users/nfahrisalim/Documents/Moobby-backups/moobby-supabase-backup-20261021T234448Z` on the APFS Data volume. `fdesetup status` reported FileVault On; `diskutil` reported APFS and FileVault Yes for the Data volume. The destination directory and parent have mode `0700`; all five files have mode `0600`. The original in `/private/tmp/moobby-supabase-backup-20261021T234448Z` remains untouched. SHA-256 values for all five destination files were compared with the original; the detached manifest checksum matches. This is a durable local copy outside Git and temporary directories, encrypted at rest by FileVault. It is not an off-device or independently replicated backup, and does not establish whole-project recoverability.

## Backup files and integrity

The manifest is `manifest.json`; its detached SHA-256 is in `manifest.json.sha256`. The manifest records the masked target, tool and server versions, source inventory, exact row counts for all 39 catalog tables, dump scope, local restore result, and checksums.

| File | Bytes | SHA-256 |
|---|---:|---|
| `roles.sql` | 370 | `168a95a9c745af5ed4679751f90419ac9dc434240a213b03e32a06d5664c2308` |
| `schema.sql` | 2,402 | `9ce7bb5dbf67dec8193c9d9d4504fcff43e82b19f4ed5e2ca3a74f79170192b7` |
| `data.sql` | 10,233 | `48272cc65fe2f59fc54cbb4a0bac455673f1f4dcfcc3235f2ee2308c00841e48` |
| `manifest.json` | 6,656 at finalization | `510525e06b67d63b4d755fd0dd819c58d54220fa82f7e595abe0a64c9ec687b2` |
| `manifest.json.sha256` | 80 | `8868f644204af555f7e5598ac14f457c6ccaff63c28418b051dffaf340fd48b3` |

The manifest checksum is detached because a file cannot contain its own stable checksum. All five file checksums were verified again after copying to the FileVault-protected destination; the source copy remains available. Directory and file permissions were checked at both locations. The three dump file checksums were also rechecked before restore.

## Exact observed scope

The backup followed Supabase's documented three-file CLI workflow: role-only, schema, then data-only with COPY format and the documented exclusions `storage.buckets_vectors` and `storage.vector_indexes` ([official backup and restore guide](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)). The dump output contained:

- `roles.sql`: 3 `ALTER ROLE` statements and 1 `GRANT`; it contained no `CREATE ROLE` statement. The source inventory showed 30 roles and 24 memberships, so the file does not recreate that full role catalog/membership graph. Some roles are supplied by the platform baseline; other role state needs a separate recovery review.
- `schema.sql`: 4 `CREATE EXTENSION` statements (`pg_stat_statements`, `pgcrypto`, `supabase_vault`, `uuid-ossp`) and 4 `GRANT` statements; it contained no `CREATE SCHEMA`, `CREATE TABLE`, `CREATE VIEW`, or `CREATE FUNCTION` statements. Managed schema/table definitions were supplied by the isolated Supabase stack, not by this dump.
- `data.sql`: 31 `COPY` blocks, all with zero rows. Exact source counts taken afterward matched all 31 included relations.
- The remote inventory had 39 tables. Eight were absent from `data.sql`: `auth.schema_migrations` (82 rows), `realtime.messages` (0), `realtime.schema_migrations` (91), `realtime.subscription` (0), `storage.buckets_vectors` (0), `storage.migrations` (74), `storage.vector_indexes` (0), and `vault.secrets` (0). These observed omissions total 247 rows. The two vector tables are explicitly excluded by the documented command; the remaining exclusions were observed in the CLI output and are not assumed to be included by this workflow.

The inventory listed nine non-system schemas: `auth`, `extensions`, `graphql`, `graphql_public`, `pgbouncer`, `public`, `realtime`, `storage`, and `vault`. No `collection`, `processing`, or `archive` schema, public application table, or `moobby_runtime` role was present during the read-only recheck. The runbook did not create or modify any of them.

## Restore procedure and evidence

The restore target was created with `supabase init` and `supabase start` under a protected temporary work directory, with no project link and no remote target. The local PostgreSQL server reported **17.11**. The restore used the official order and trigger handling:

```sh
psql --single-transaction --set ON_ERROR_STOP=1 \
  --file roles.sql \
  --file schema.sql \
  --command 'SET session_replication_role = replica' \
  --file data.sql \
  --dbname "$LOCAL_SUPABASE_DB_URL"
```

`LOCAL_SUPABASE_DB_URL` referred only to the local Docker stack. The restore ran as the local `supabase_admin` superuser because the stack's ordinary `postgres` login could not execute a role setting in `roles.sql`. The official guide also documents single-transaction restore and replica trigger handling; it notes that custom Auth/Storage schema changes may need separate recovery ([restore instructions and managed-schema notes](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)).

Post-restore checks verified PostgreSQL 17.11, successful commit of all three files, four declared extensions present, and exact `count(*)` equality for each of the 31 data-dump relations. The result was 31/31 relation counts equal and 0 restored rows, matching the dump. The local stack was stopped and restarted; all 31 relation objects, their row counts, and all four extension objects were present afterward. It is now stopped with its local volume retained. Checksums and protected file modes passed. This test did not compare provider-level settings, storage object bytes, or customizations within managed schemas.

## Exclusions and limitations

- The CLI dump is not a whole Supabase project backup. Supabase-managed schema definitions are supplied by the destination platform; the `schema.sql` produced here contains no table DDL.
- The CLI output did not contain eight inventoried table relations listed above. The manifest records their exact source counts; do not infer that excluded platform migration/history rows are unnecessary for every recovery scenario.
- Storage object bytes are not in PostgreSQL SQL dumps. Auth provider settings, API/Data API exposed-schema configuration, project secrets, Edge Function files/settings, Realtime configuration, and other Dashboard/provider configuration were not included or restored.
- Custom changes inside `auth` and `storage` may require a separate diff/recovery step per Supabase guidance. The current inventory showed no visible RLS policies, but did not prove the absence of every possible managed-schema customization.
- Exposed Data API schemas remain **UNVERIFIED**. The owner must inspect the Dashboard and ensure `collection`, `processing`, and `archive` stay unexposed before any live installation.
- The three files were captured sequentially, not under one cross-file snapshot. The exact post-backup source counts matched included relation counts, but no write pause was performed and unrelated writers were not independently ruled out.
- The destination is local FileVault-encrypted storage, not an offsite or independently backed-up copy. Device loss/failure can still make it unavailable. No cloud backup synchronization or retention policy was verified.

## Owner actions

1. Maintain a second encrypted copy if recovery from device loss is required; the local destination is not offsite.
2. Decide whether platform migration metadata, role definitions/memberships, and managed-schema customizations need a separate platform-level recovery plan. They were intentionally not restored or modified.
3. Confirm the Data API exposed-schema list and project configuration recovery process.
4. Before a future live migration, capture a fresh inventory, pause writers to the agreed scope, create a new backup, and rehearse that exact recovery scope. Live migrations remain unauthorized.
