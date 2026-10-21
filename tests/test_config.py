from moobby.config import Config, load_config
from moobby.preflight import _configuration_check


def test_missing_config_reports_key_names_only(tmp_path, monkeypatch):
    for key in ("DATABASE_URL", "ORVIX_API_KEY", "ORVIX_MODEL", "X_SESSION_PATH"):
        monkeypatch.delenv(key, raising=False)
    config = load_config(tmp_path)
    result = _configuration_check(config)
    assert result.status.value == "FAIL"
    assert set(config.missing_keys) == {"DATABASE_URL", "ORVIX_API_KEY", "ORVIX_MODEL", "X_SESSION_PATH"}
    assert "missing-secret-value" not in result.reason


def test_loads_env_file_from_project_root_not_current_directory(tmp_path, monkeypatch):
    project = tmp_path / "project"
    unrelated_cwd = tmp_path / "elsewhere"
    project.mkdir()
    unrelated_cwd.mkdir()
    (project / ".env").write_text("ORVIX_MODEL=model-from-project\n")
    (unrelated_cwd / ".env").write_text("ORVIX_MODEL=wrong-model\n")
    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.delenv("ORVIX_MODEL", raising=False)
    config = load_config(project)
    assert config.orvix_model == "model-from-project"
