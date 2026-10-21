# Configuration and preflight

## Purpose

Stage 1 provides one local entry point for the planned pipeline. The real stage is a read-only preflight that checks the Python runtime, required environment variables, optional local X session storage, and PostgreSQL connectivity. `collect`, `filter`, `extract`, `validate`, and `export` are registered in their fixed order and currently report `SKIPPED` because they are not implemented.

## Input and output

Inputs are the project-root `.env` file, environment overrides, and the configured local X session file. Preflight does not read session contents. The database check opens a TLS connection, runs `SELECT 1`, reads `current_user`, and checks the `collection` schema catalog entry. It performs no writes. Orvix is checked only for configuration; the API is never called.

The command prints per-check and per-stage status, followed by an overall summary. A missing or unusable X session is reported as `auth_required` with a manual-login instruction. Placeholder stages are `SKIPPED`. A failed stage makes the process exit non-zero and prevents later stages from running.

## Dependencies

- Python 3.10 or newer
- `python-dotenv==1.1.1`
- `psycopg[binary]==3.2.9`
- `pytest==8.4.2` for tests

## Configuration keys

Create `.env` from `.env.example` and supply local values. The loader resolves `.env` from the project root, independent of the current working directory; exported environment variables take precedence.

| Key | Purpose |
|---|---|
| `DATABASE_URL` | Supabase PostgreSQL Session pooler URI copied from the intended project's Connect settings. The check forces TLS and uses a five-second connection timeout. |
| `ORVIX_API_KEY` | Reserved for later extraction stages. Preflight only checks that it is set. |
| `ORVIX_MODEL` | Model name reserved for later extraction stages. Preflight only checks that it is set. |
| `X_SESSION_PATH` | Path to the local X session storage file. Relative paths are resolved from the project root. |

Never put real credentials in `.env.example`. `.env`, session/cookie files, exports, logs, virtualenvs, and Python cache files are ignored by Git. Logs and CLI errors pass through the central redactor; database output shows only a masked target hint.

## Failure modes

- Missing required environment variables fail the configuration check by key name only.
- A missing Python dependency or unsupported Python version fails the runtime check.
- An unavailable database, TLS/connectivity error, or failed read-only query fails the database check. The URI and password are redacted from the message.
- A reachable database without `collection` is a warning: initialization is expected to happen in a later stage.
- A missing, empty, or unreadable session file is a warning with status `auth_required`; log in manually once and rerun preflight. This stage does not log in or retry.
- Missing Orvix key/model is a configuration failure. No request is sent to Orvix.
- Placeholder stages do not count as passed or failed. When any are skipped, the overall result is `INCOMPLETE` unless a warning or failure takes precedence.

## Acceptance criteria covered

- **AC-01 (partial):** one shared `.env` configuration and session path are loaded by the runner. Collector reuse cannot be demonstrated until those later stages exist.
- **AC-02 (preflight portion):** unusable X session is reported as `auth_required`; the runner does not claim overall success. Manual login flow and collection-run receipts are later work.
- **AC-07 (preflight portion):** Orvix key/model presence is checked without calling the API, and secret-bearing text is redacted. The required User-Agent behavior must be implemented and verified with the later Orvix adapter.

## Test results

`python3 -m compileall -q main.py moobby tests` passed. The pytest suite could not run in this environment: pytest was not installed, and installing the pinned requirements in the project virtualenv failed because `pypi.org` could not be resolved. The suite uses a mocked database connection and does not itself require network access. No live database or X session was tested.

## Limitations

This stage does not create or migrate a schema, collect X posts, log in to X, filter posts, call Orvix, validate claims, or export data. A successful mocked DB test does not establish that a real project URI, role, TLS route, or permissions work. The target database and local session have not been assumed or inspected. The `X_SESSION_PATH` name is an implementation choice because §7 describes local session storage without naming an environment variable.

## Setup and run

From the repository root, run these commands:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` with the local connection URI, Orvix key/model, and X session file path, then run:

```sh
python main.py --list-stages
python main.py preflight
python main.py
pytest
```

`python main.py` runs all registered stages in order and stops at the first failed stage. During Stage 1, the later five stages are placeholders.
