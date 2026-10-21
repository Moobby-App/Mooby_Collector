from moobby.config import Config
from moobby.preflight import CheckStatus, _database_check


def test_database_failure_is_reported_without_leaking_uri(monkeypatch, tmp_path):
    import psycopg

    def fail_connect(*args, **kwargs):
        raise RuntimeError("connection rejected for postgresql://u:db-password@host/db")

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    config = Config(tmp_path, "postgresql://u:db-password@host/db", "api-secret", "model", tmp_path / "session")
    result = _database_check(config)
    assert result.status is CheckStatus.FAIL
    assert "db-password" not in result.reason
    assert "postgresql://" not in result.reason


def test_missing_session_is_auth_required_warning(tmp_path):
    from moobby.preflight import _session_check

    config = Config(tmp_path, None, None, None, tmp_path / "missing-session")
    result = _session_check(config)
    assert result.status is CheckStatus.WARN
    assert "auth_required" in result.reason
    assert "log in manually once" in result.reason
