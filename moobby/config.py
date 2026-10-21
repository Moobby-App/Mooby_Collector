"""Load local pipeline configuration without searching the working directory."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

REQUIRED_KEYS = ("DATABASE_URL", "ORVIX_API_KEY", "ORVIX_MODEL", "X_SESSION_PATH")


@dataclass(frozen=True)
class Config:
    project_root: Path
    database_url: str | None
    orvix_api_key: str | None
    orvix_model: str | None
    x_session_path: Path | None

    @property
    def missing_keys(self) -> tuple[str, ...]:
        values = {
            "DATABASE_URL": self.database_url,
            "ORVIX_API_KEY": self.orvix_api_key,
            "ORVIX_MODEL": self.orvix_model,
            "X_SESSION_PATH": str(self.x_session_path) if self.x_session_path else None,
        }
        return tuple(key for key in REQUIRED_KEYS if not values[key])

    @property
    def secret_values(self) -> tuple[str, ...]:
        return tuple(value for value in (self.database_url, self.orvix_api_key) if value)


def load_config(project_root: str | Path) -> Config:
    """Load `.env` from the directory containing the supplied project entrypoint."""
    root = Path(project_root).resolve()
    if root.is_file():
        root = root.parent
    env_file = root / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        # Let preflight report the missing dependency cleanly instead of crashing
        # before its runtime checks can produce a useful result.
        pass

    session_value = os.getenv("X_SESSION_PATH")
    return Config(
        project_root=root,
        database_url=os.getenv("DATABASE_URL") or None,
        orvix_api_key=os.getenv("ORVIX_API_KEY") or None,
        orvix_model=os.getenv("ORVIX_MODEL") or None,
        x_session_path=(Path(session_value).expanduser() if session_value else None),
    )
