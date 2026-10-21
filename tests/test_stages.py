from moobby.config import Config
from moobby.stages import Stage, StageResult, StageStatus, list_stages, run_stages


def test_registered_stage_order_and_placeholders(tmp_path):
    stages = list_stages()
    assert [stage.name for stage in stages] == ["preflight", "collect", "filter", "extract", "validate", "export"]
    config = Config(tmp_path, None, None, None, None)
    results = run_stages(config, stages=stages[1:])
    assert all(result.status is StageStatus.SKIPPED for result in results)
    assert all(result.reason == "not implemented" for result in results)


def test_stops_at_first_failed_stage(tmp_path):
    seen = []

    def failed(_):
        seen.append("first")
        return StageResult("first", StageStatus.FAILED, "failure")

    def later(_):
        seen.append("later")
        return StageResult("later", StageStatus.PASSED, "ok")

    results = run_stages(Config(tmp_path, None, None, None, None), [
        Stage("first", "", failed), Stage("later", "", later)
    ])
    assert seen == ["first"]
    assert results[0].status is StageStatus.FAILED


def test_cli_exit_nonzero_when_preflight_fails(monkeypatch):
    import main as entrypoint

    monkeypatch.setattr(entrypoint, "load_config", lambda project_root: Config(__import__("pathlib").Path("."), None, None, None, None))
    assert entrypoint.main([]) != 0
