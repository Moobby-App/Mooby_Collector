"""Ordered pipeline stage registry and execution/reporting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable

from moobby.config import Config
from moobby.preflight import run_preflight
from moobby.redaction import safe_print


class StageStatus(str, Enum):
    PASSED = "PASS"
    WARN = "WARN"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StageResult:
    name: str
    status: StageStatus
    reason: str


@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    runner: Callable[[Config], StageResult]


def _preflight(config: Config) -> StageResult:
    checks = run_preflight(config)
    safe_print("Preflight summary")
    safe_print(f"{'CHECK':16} {'STATUS':6} DETAILS")
    for check in checks:
        safe_print(f"{check.name:16} {check.status.value:6} {check.reason}")
    failed = any(check.status.value == "FAIL" for check in checks)
    warned = any(check.status.value == "WARN" for check in checks)
    status = StageStatus.FAILED if failed else StageStatus.WARN if warned else StageStatus.PASSED
    reason = "one or more checks failed" if failed else "one or more checks need attention" if warned else "all checks passed"
    return StageResult("preflight", status, reason)


def _placeholder(name: str) -> Callable[[Config], StageResult]:
    def run(_: Config) -> StageResult:
        return StageResult(name, StageStatus.SKIPPED, "not implemented")

    return run


_REGISTRY = (
    Stage("preflight", "read-only environment and access checks", _preflight),
    Stage("collect", "collect source posts", _placeholder("collect")),
    Stage("filter", "filter relevant posts", _placeholder("filter")),
    Stage("extract", "extract structured claims", _placeholder("extract")),
    Stage("validate", "validate claims", _placeholder("validate")),
    Stage("export", "export labeled dataset", _placeholder("export")),
)


def list_stages() -> tuple[Stage, ...]:
    return _REGISTRY


def get_stage(name: str) -> Stage | None:
    return next((stage for stage in _REGISTRY if stage.name == name), None)


def run_stages(config: Config, stages: Iterable[Stage] | None = None) -> list[StageResult]:
    selected = tuple(stages) if stages is not None else _REGISTRY
    results: list[StageResult] = []
    for stage in selected:
        try:
            result = stage.runner(config)
        except Exception as exc:  # Keep unexpected stage errors contained and redacted.
            result = StageResult(stage.name, StageStatus.FAILED, redact_error(exc))
        results.append(result)
        safe_print(f"STAGE {result.status.value:7} {result.name}: {result.reason}")
        if result.status is StageStatus.FAILED:
            break
    _print_summary(results)
    return results


def redact_error(exc: Exception) -> str:
    from moobby.redaction import redact

    return redact(f"{type(exc).__name__}: {exc}")


def _print_summary(results: list[StageResult]) -> None:
    if any(result.status is StageStatus.FAILED for result in results):
        overall = "FAILED"
    elif any(result.status is StageStatus.WARN for result in results):
        overall = "WARN"
    elif any(result.status is StageStatus.SKIPPED for result in results):
        overall = "INCOMPLETE"
    else:
        overall = "PASS"
    safe_print("\nPipeline summary")
    safe_print(f"{'STAGE':10} {'STATUS':9} REASON")
    for result in results:
        safe_print(f"{result.name:10} {result.status.value:9} {result.reason}")
    safe_print(f"Overall: {overall}")
