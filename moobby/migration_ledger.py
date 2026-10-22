"""Pure helpers for validating migration file hashes against a DB ledger.

The module does not connect to PostgreSQL or execute migration SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class MigrationFile:
    version: int
    name: str
    path: Path

    @property
    def checksum_sha256(self) -> str:
        return sha256(self.path.read_bytes()).hexdigest()


class MigrationDriftError(ValueError):
    """Raised when a recorded migration differs from its local file."""


def pending_migrations(
    files: Iterable[MigrationFile],
    recorded: Mapping[int, tuple[str, str | None]],
) -> list[MigrationFile]:
    """Validate recorded history and return unapplied files in version order.

    Existing rows with a different name, missing checksum, or changed file hash
    are rejected before a caller can execute any migration SQL.
    """
    ordered = sorted(files, key=lambda migration: migration.version)
    versions = [migration.version for migration in ordered]
    if len(versions) != len(set(versions)):
        raise MigrationDriftError("local migration versions are duplicated")
    known = {migration.version: migration for migration in ordered}
    unknown = sorted(set(recorded) - set(known))
    if unknown:
        raise MigrationDriftError(f"database contains unknown migration version(s): {unknown}")

    recorded_versions = sorted(recorded)
    if recorded_versions != versions[:len(recorded_versions)]:
        raise MigrationDriftError("database migration history is not a contiguous ordered prefix")

    for version, (recorded_name, recorded_checksum) in recorded.items():
        migration = known[version]
        if recorded_name != migration.name:
            raise MigrationDriftError(f"migration {version} name does not match local file")
        if recorded_checksum is None or recorded_checksum != migration.checksum_sha256:
            raise MigrationDriftError(f"migration {version} checksum does not match local file")

    applied = set(recorded)
    return [migration for migration in ordered if migration.version not in applied]
