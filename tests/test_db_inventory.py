from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace

from moobby.config import Config
from scripts import db_inventory


def test_inventory_uses_read_only_transaction_and_selects_only(monkeypatch, capsys, tmp_path):
    statements = []
    connect_args = {}

    class Cursor:
        last_query = ""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query):
            self.last_query = query
            statements.append(query)

        def fetchone(self):
            return ("on",)

        def fetchall(self):
            return []

    class Connection:
        read_only = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def transaction(self):
            return nullcontext()

        def cursor(self):
            return Cursor()

    connection = Connection()

    def connect(dsn, **kwargs):
        connect_args.update(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    database_url = "postgresql://inventory_user:inventory_password@db.example.test/postgres"
    config = Config(Path(tmp_path), database_url, None, None, None)
    monkeypatch.setattr(db_inventory, "load_config", lambda _: config)

    assert db_inventory.main() == 0
    assert connection.read_only is True
    assert connect_args["sslmode"] == "require"
    assert connect_args["connect_timeout"] == 5
    assert statements and all(query.lstrip().upper().startswith("SELECT") for query in statements)
    output = capsys.readouterr().out
    assert "inventory_password" not in output
    assert database_url not in output
    assert "Transaction: read-only confirmed" in output


def test_inventory_queries_are_read_only_selects():
    query_constants = [
        name for name in vars(db_inventory)
        if name.endswith("_SQL") and isinstance(getattr(db_inventory, name), str)
    ]
    assert query_constants
    assert all(getattr(db_inventory, name).lstrip().upper().startswith("SELECT") for name in query_constants)


def test_inventory_aborts_before_catalog_queries_if_read_only_not_confirmed(monkeypatch, capsys, tmp_path):
    statements = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query):
            statements.append(query)

        def fetchone(self):
            return ("off",)

    class Connection:
        read_only = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def transaction(self):
            return nullcontext()

        def cursor(self):
            return Cursor()

    connection = Connection()
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
    )
    config = Config(
        Path(tmp_path),
        "postgresql://inventory_user:inventory_password@db.example.test/postgres",
        None,
        None,
        None,
    )
    monkeypatch.setattr(db_inventory, "load_config", lambda _: config)

    assert db_inventory.main() == 1
    assert connection.read_only is True
    assert len(statements) == 1
    output = capsys.readouterr().out
    assert "read-only transaction" in output
    assert "inventory_password" not in output
