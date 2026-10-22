# R0 inventory results

## Purpose and method

This is the review record for the read-only R0 inspection required by SPEC §8. The inventory was run on 22 October 2026 against the project configured in the local environment. The report masked its target as `host=aws-0-ap-northeast-1.pooler.supabase.com; project_ref=vgy…ug`; credentials and the complete connection URI are intentionally omitted.

`scripts/db_inventory.py` connected with TLS, a five-second connection timeout, and a psycopg read-only transaction. It confirmed `transaction_read_only=on` before issuing catalog queries. The script contains SELECT/catalog queries only and does not write a report file. No DDL, DML, role, grant, policy, or RLS change was made.

## Findings

- Non-system schemas: `auth`, `extensions`, `graphql`, `graphql_public`, `pgbouncer`, `public`, `realtime`, `storage`, `vault`.
- No `collection`, `processing`, `archive`, or `supabase_migrations` schema was listed. The draft schema names therefore appear unused at this inspection, but this does not establish that creating them is approved.
- Catalog report listed 39 tables, 136 constraints (including 29 foreign keys), 3 views, 103 functions, 30 roles, and 24 role memberships. Table row counts are PostgreSQL planner estimates, not exact counts. Most estimates were `-1` (no estimate); visible non-negative examples included 82 rows for `auth.schema_migrations`, 91 for `realtime.schema_migrations`, and 74 for `storage.migrations`. These are estimates and must not be treated as exact backup counts.
- The listed foreign keys were in `auth` and `storage`. No FK in `public` or a Moobby schema was listed.
- Views listed were `extensions.pg_stat_statements`, `extensions.pg_stat_statements_info`, and `vault.decrypted_secrets`.
- Functions were present across Supabase-managed schemas. No Moobby schema functions were listed.
- `anon` and `authenticated` exist. The catalog listed 30 roles and 24 memberships; `postgres` has memberships including `anon`, `authenticated`, `authenticator`, and `service_role`. This is a role graph observation, not a privilege audit of all inherited table access.
- Schema grants include `USAGE` for `anon` and `authenticated` on Supabase-managed schemas and `public`; this is not by itself table access. The `public` schema had `USAGE` for `PUBLIC`, `anon`, `authenticated`, and `postgres`, with no `CREATE` grant shown in the captured report.
- Table grants exist on Supabase-managed tables, including grants to `anon`/`authenticated` on `realtime` and `storage` objects. These are platform objects and were not changed. No public application table was listed.
- RLS was enabled on many `auth` and `storage` tables, plus `realtime.messages`; it was disabled on other listed managed tables. The inventory returned zero visible policies from `pg_policies`. This needs owner-level confirmation during rehearsal because catalog visibility/managed-project configuration may affect what the connecting role can inspect.
- Migration-like internal tables were present under `auth`, `realtime`, and `storage`. Their contents were not read. No application migration ledger was found in the listed schemas; how to record Moobby migrations remains a project decision.

## Comparison with the draft

The inventory found no existing Moobby objects or application tables that conflict by name with the draft. It did not reveal pre-existing application data to migrate. The proposed `collection`, `processing`, and `archive` namespaces are still subject to a fresh check immediately before any migration. Existing Supabase-managed schemas and their grants, dependencies, RLS, and contents are out of scope for these drafts and must be left untouched.

The final inventory rerun included all table constraint types and confirmed the read-only transaction. The inventory is not an exact row-count or backup manifest. Before rehearsal or migration, capture exact counts for the application tables selected for backup, complete object definitions/dependencies, relevant role memberships and grants, and the project’s exposed-schema/Data API configuration. The Data API setting was not checked through PostgreSQL and remains **UNVERIFIED**.

## Limitations

- No write capability was tested; read-only inventory does not establish runtime write grants.
- No exact `COUNT(*)` scans were run.
- Supabase-managed migration ledger rows were not inspected.
- The policy query returned zero rows. Confirm policy visibility with the project owner before relying on it.
- At the historical R0 stage, no schema DDL was applied, no role or grant was changed, no backup was taken, and no restore/rehearsal was performed. Stage 4 added an isolated local synthetic backup/restore test; no remote backup or restore was performed.

## Table inventory detail

`reltuples` values other than the three noted above were `-1`; treat them as unknown. The RLS column reflects `relrowsecurity` from the catalog and is not the same as a user access test.

| Schema | Tables (approximate rows; RLS enabled) |
|---|---|
| `auth` | `audit_log_entries` (-1; yes), `custom_oauth_providers` (-1; no), `flow_state` (-1; yes), `identities` (-1; yes), `instances` (-1; yes), `mfa_amr_claims` (-1; yes), `mfa_challenges` (-1; yes), `mfa_factors` (-1; yes), `mfa_recovery_code_sets` (-1; no), `mfa_recovery_codes` (-1; no), `oauth_authorizations` (-1; no), `oauth_client_states` (-1; no), `oauth_clients` (-1; no), `oauth_consents` (-1; no), `one_time_tokens` (-1; yes), `refresh_tokens` (-1; yes), `saml_providers` (-1; yes), `saml_relay_states` (-1; yes), `schema_migrations` (82; yes), `scim_tokens` (-1; no), `scim_users` (-1; no), `sessions` (-1; yes), `sso_domains` (-1; yes), `sso_providers` (-1; yes), `users` (-1; yes), `webauthn_challenges` (-1; no), `webauthn_credentials` (-1; no) |
| `realtime` | `messages` (-1; yes), `schema_migrations` (91; no), `subscription` (-1; no) |
| `storage` | `buckets` (-1; yes), `buckets_analytics` (-1; yes), `buckets_vectors` (-1; yes), `migrations` (74; yes), `objects` (-1; yes), `s3_multipart_uploads` (-1; yes), `s3_multipart_uploads_parts` (-1; yes), `vector_indexes` (-1; yes) |
| `vault` | `secrets` (-1; no) |

The 29 foreign keys are all in `auth` and `storage`. The three views and 103 functions were reported by name/signature in stdout; they belong to `extensions`, `auth`, `graphql_public`, `pgbouncer`, `realtime`, `storage`, or `vault`. The complete role and grant rows were likewise emitted by the script to stdout; the concise findings above highlight the grants to `anon`/`authenticated` and platform scope. Re-run the inventory for the current full listing rather than treating this dated record as a live source of truth.

## Stage 4 refreshed read-only inventory

On 22 October 2026, `scripts/db_inventory.py` was rerun against the configured target. It again confirmed a read-only transaction and printed the masked hint `host=aws-0-ap-northeast-1.pooler.supabase.com; project_ref=vgy…ug`. Catalog section totals were 9 non-system schemas, 39 tables, 136 constraints, 29 foreign keys, 3 views, 103 functions, 30 roles, 24 memberships, 60 schema grants, 341 table grants, 39 RLS entries, and 0 visible policies. The schemas and tables match the list above: no `collection`, `processing`, `archive`, or public application tables were listed. The role section lists 30 roles and does not include `moobby_runtime`.

The project owner supplied PostgreSQL server version **17.11**, Data API enabled, exposed schemas not yet confirmed, and Dashboard backups unavailable. The version and Data API-enabled state are owner-provided facts; the catalog run did not query server version or Data API settings. The rerun performed no writes and created no report file. Approximate table estimates remain estimates, not exact counts. As no Moobby application tables currently appear in the inventory, there are no existing Moobby table counts to include in an application-schema backup; this does not constitute a backup of the Supabase project or its managed schemas. Re-run R0 immediately before deployment.

## Stage 4 backup-time inventory and collision recheck (2026-10-22)

Before the CLI dump, the masked target hint matched the Stage 4 inventory record. Docker Engine **29.6.1** and Supabase CLI **2.121.0** were used for the official logical dump. After the dump, `scripts/db_inventory.py` was rerun with a read-only transaction and confirmed server version **17.11**, current user `postgres`, 9 non-system schemas, 39 tables, 136 constraints, 29 foreign keys, 3 views, 103 functions, 30 roles, 24 role memberships, 60 schema grants, 341 table grants, 39 RLS entries, and 0 visible policies. A separate read-only catalog check confirmed `collection`, `processing`, `archive`, and `moobby_runtime` were still absent. No live changes were made.

Exact `count(*)` results were recorded for all 39 tables in the protected manifest described in [backup-restore-verification.md](backup-restore-verification.md). Counts for the 31 tables represented in the CLI data dump matched the dump and isolated restore exactly: all had 0 rows. The other 8 relations were absent from `data.sql` and had 247 rows total, all in platform migration metadata tables (`auth.schema_migrations`, `realtime.schema_migrations`, and `storage.migrations`). These actual counts supplement, but do not rewrite, the earlier planner estimates above.

The exposed Data API schema list remains **UNVERIFIED**. The CLI dump and local restore did not include project-level API configuration or Storage object bytes. At the time this Stage 4 inventory entry was written, the backup was still under `/private/tmp/moobby-supabase-backup-20261021T234448Z`; the Stage 5 preparation section below records the later verified copy to FileVault-encrypted local storage.

## Stage 5 preparation: read-only managed-object review (2026-10-22)

The target hint matched the previously confirmed masked target before connecting. A TLS connection with a five-second timeout confirmed PostgreSQL 17.11 and `transaction_read_only=on`; all subsequent statements were catalog SELECTs. The current catalog listed eight non-internal triggers in managed schemas: one on `realtime.subscription`, five on `storage.buckets`, and two on `storage.objects`. Their trigger functions were in the corresponding managed schemas. `pg_policies` returned zero visible rows. Five extensions were listed: `pg_stat_statements` 1.11, `pgcrypto` 1.3, `plpgsql` 1.0, `supabase_vault` 0.3.1, and `uuid-ossp` 1.1. No relation or function was listed in `public`. No `collection`, `processing`, or `archive` namespace, `moobby_runtime` role, or role membership involving that name was present.

These catalog results do not determine whether the managed triggers are vendor defaults or owner customizations. No managed schema, platform role, grant, policy, or trigger was modified. Data API exposed schemas remain **UNVERIFIED** because PostgreSQL inventory does not establish the Dashboard/PostgREST setting. Role/migration state omissions from the logical dump are documented in [backup-restore-verification.md](backup-restore-verification.md); the omitted platform objects were left in place and were not replayed.

The five backup/manifest files were copied to `/Users/nfahrisalim/Documents/Moobby-backups/moobby-supabase-backup-20261021T234448Z`. The destination is on the APFS Data volume with FileVault On; destination directory/parent modes are `0700`, files are `0600`, all five SHA-256 values match the temporary original, and the detached manifest checksum matches. The original `/private/tmp/moobby-supabase-backup-20261021T234448Z` was not removed. This is local encrypted storage, not an independently replicated/offsite copy.
