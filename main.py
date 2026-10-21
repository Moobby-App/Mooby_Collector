"""Moobby pipeline command line entry point."""

from __future__ import annotations

import argparse
import sys

from moobby.config import load_config
from moobby.redaction import configure_secrets, safe_print
from moobby.stages import StageStatus, get_stage, list_stages, run_stages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Moobby data pipeline.")
    parser.add_argument("stage", nargs="?", help="run one registered stage")
    parser.add_argument("--list-stages", action="store_true", help="list registered stages")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_stages:
        for stage in list_stages():
            safe_print(f"{stage.name:10} {stage.description}")
        return 0

    config = load_config(project_root=__file__)
    configure_secrets(config.secret_values)

    if args.stage:
        stage = get_stage(args.stage)
        if stage is None:
            safe_print(f"Unknown stage: {args.stage}")
            safe_print("Registered stages: " + ", ".join(s.name for s in list_stages()))
            return 2
        results = run_stages(config, stages=[stage])
    else:
        results = run_stages(config)

    failed = any(result.status is StageStatus.FAILED for result in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
