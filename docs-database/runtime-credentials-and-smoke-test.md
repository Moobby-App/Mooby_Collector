# Restricted runtime credentials and smoke test

## Purpose and status

This Stage 5 procedure configures local `DATABASE_URL` for the already installed `moobby_runtime` role, then verifies the live connection and restricted access. The procedure does not reapply migrations, change grants/RLS, reset schemas, or enable purge.

Verified on 2026-10-22 after the owner configured the password interactively and updated local `.env`. With any exported `DATABASE_URL` override removed, the configured URI passed the masked target, custom-role username, Session Pooler port 5432, database, file mode `0600`, and Git-ignore checks. The runtime connected as `moobby_runtime` to PostgreSQL 17.11 over TLS. The prior admin URI was not used for runtime execution.

Password setup and use of the custom role through Supabase shared Session Pooler are supported. Supabase documents Session Pooler on port 5432 and custom role usernames in `role.project-ref` form; copy the host from the Dashboard rather than deriving it. TLS is required by this project’s preflight (`sslmode=require`). Supabase documents that custom `LOGIN` roles work through the shared pooler. PostgreSQL `psql`'s `\password` command prompts for the password and avoids placing cleartext in the SQL command/history.

## Owner-operated password setup

The project owner performs these steps locally. Do not send the password or connection URI to Moobby logs, source control, or chat.

1. Open the intended Supabase project Dashboard. In **Connect**, choose **Session pooler** and copy its host and project reference. Confirm port 5432 and database `postgres`. Do not compose a host from the region.
2. In a local terminal, replace the two non-secret placeholder tokens with the copied host and project reference, then connect as the administrative `postgres` role. This command intentionally contains no password; `-W` prompts for it without echoing it:

   ```sh
   psql -W "host=POOLER_HOST_FROM_DASHBOARD port=5432 dbname=postgres user=postgres.PROJECT_REF_FROM_DASHBOARD sslmode=require"
   ```

3. At the `psql` prompt, run `SELECT current_user;` and proceed only if it reports `postgres` for the intended project. Then run:

   ```text
   \password moobby_runtime
   ```

   Enter a strong random password at both hidden prompts. Save it in the owner’s password manager. Do not use `ALTER ROLE ... PASSWORD '...'`, SQL literals, shell arguments, or echoed terminal commands. Exit with `\q`.
4. In the Dashboard Connect panel, select **Session pooler** again and construct the local runtime connection by using that copied Session Pooler host, port 5432, database `postgres`, the username `moobby_runtime.PROJECT_REF`, and the password just set. Append `sslmode=require` if the Dashboard string does not already contain an SSL mode. Supabase requires reserved URI characters in passwords to be percent-encoded; a password manager can generate a strong password from URI-unreserved characters to avoid manual encoding.
5. Edit the existing root `.env` in a local text editor. Replace only its `DATABASE_URL` value with the runtime connection. Keep the URI in `.env` only; do not paste it into commands, tickets, screenshots, or chat. Ensure the other required variables remain present.
6. In the repository root, restrict permissions and confirm ignore status without printing `.env`:

   ```sh
   chmod 600 .env
   git check-ignore -q .env && echo '.env is ignored'
   ```

7. Open a fresh terminal (or remove any exported `DATABASE_URL` override) so the project-root `.env` value is the one loaded. The configuration loader gives already-exported environment variables precedence over `.env`.

If a runtime login fails immediately after password rotation, avoid repeated rapid attempts. Supabase notes that a shared pooler may briefly cache a previous custom-role credential; verify the password through the owner’s approved secure path and retry only after a short wait. Repeated authentication failures can trigger connection blocking.

## Read-only runtime check

After updating `.env`, run:

```sh
env -u DATABASE_URL ./.venv/bin/python main.py preflight
```

The command uses `.env` because the explicit environment override is removed. Its database line must say `connected as moobby_runtime`, show only the masked target hint, and report `collection schema exists`. Preflight performs SELECTs only; it does not call Orvix or write fixture rows. Do not run the pipeline with the administrator URI.

## Controlled live smoke test

After preflight reports `moobby_runtime`, run the Stage 5 helper:

```sh
env -u DATABASE_URL ./.venv/bin/python scripts/runtime_smoke_test.py
```

The helper has a hard guard for the approved masked target and `current_user = moobby_runtime`; it verifies client TLS, server version, migration versions 1 and 2, the monitored source row, runtime role attributes/memberships, schema USAGE without CREATE, and absence of database CREATE. It then performs an INSERT and column-limited UPDATE on one random `collection.discovered_authors` fixture. It probes that schema DDL and DELETE are denied. The fixture, and any DDL that unexpectedly succeeds, are contained in a transaction/savepoint; the outer transaction is always rolled back. The helper never commits test data and grants no DELETE privilege. It prints no URI or password.

Expected successful output includes permitted SELECT/INSERT/UPDATE, denied schema DDL, denied DELETE, `identity=moobby_runtime`, TLS on, and `fixture transaction: rolled back`. A failure or unexpected permission must stop Stage 5; do not alter grants or RLS to make the helper pass. The owner can report the redacted output, but should omit any unrelated terminal content.

## Verification results and acceptance criteria

- **AC-03: PASS.** The live session authenticated as `moobby_runtime`, with LOGIN and no SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS, INHERIT, or memberships.
- Runtime schema access: USAGE on `collection`, `processing`, and `archive`; no schema CREATE or database CREATE. Catalog checks saw 13/13 tables with SELECT, INSERT on 11 tables, column-limited UPDATE grants (33 visible column grants), and no table-level UPDATE or DELETE. RLS policies visible: 13.
- Live controlled smoke test: SELECT from source/ledger, INSERT and allowed-column UPDATE on a random author fixture passed. CREATE TABLE and DELETE were denied. The fixture transaction rolled back. A follow-up read-only query found zero leftover smoke fixtures and zero forbidden test tables.
- `env -u DATABASE_URL ./.venv/bin/python main.py preflight`: PASS, connected as `moobby_runtime`; configuration, initialized collection schema, X session, and Orvix-key/model checks passed. The Orvix API was not called.
- After runtime configuration, `env -u DATABASE_URL ./.venv/bin/python -m pytest -q`: **20 passed**; `env -u DATABASE_URL ./.venv/bin/pytest -q`: **20 passed**. Tests use disposable local PostgreSQL only; they do not write to Supabase.
- The helper passes `.venv/bin/python -m py_compile scripts/runtime_smoke_test.py`. No migrations were reapplied and no runtime grants/RLS were changed.

## Dependencies and failure modes

The procedure uses the existing pinned `psycopg[binary]`, `python-dotenv`, the existing config/redaction helpers, local `psql`, and the Supabase Session Pooler. Authentication failure, wrong project hint, non-runtime identity, missing TLS, changed grants, unavailable schema/source/ledger, or a permitted DDL/DELETE probe fails the check. Do not retry indefinitely or change production grants as a diagnostic shortcut.

`sslmode=require` encrypts the client-to-pooler connection but does not validate the server certificate. Supabase documents downloading the root certificate and using `sslmode=verify-full` for certificate/hostname verification; the current Moobby preflight explicitly requires `sslmode=require` and has not been changed in this stage. A future certificate-verification change needs a reviewed application/configuration update.

The smoke test exercises an INSERT and a specific column UPDATE on `discovered_authors`, read access to the source/ledger, and denied DDL/DELETE. It does not exercise writes on every table or verify X, Orvix, filtering, export, receipt retries, or application transactions that do not yet exist. It is not authorization to enable purge. The transaction rollback is the fixture cleanup, so it tests permission behavior without requiring runtime DELETE.

## Official references

- [Supabase: Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres) — Session Pooler selection, port 5432, custom-role username format, reserved-character encoding, TLS behavior.
- [Supabase: Postgres Roles](https://supabase.com/docs/guides/database/postgres/roles) — custom login roles and least-privilege role usage.
- [Supabase: FATAL: Password authentication failed](https://supabase.com/kb/troubleshooting/fatal-password-authentication-failed) — custom roles through shared Supavisor and short-lived credential cache behavior.
- [PostgreSQL `psql` reference](https://www.postgresql.org/docs/17/app-psql.html) — `\password` prompts interactively and avoids cleartext in command history/logs.
