"""File-backed repository (transitional storage adapter).

NOTE (R-TRUTH-3 honesty): SQLite is the target store but ADR-6 (benchmark per
spec §4.2) is deliberately executed BEFORE depending on SQLite-specific
behavior. Until then this JSON-file store implements the same port: it
auto-creates the data dir, writes atomically, and is fully swappable when
ADR-6 lands. It is NOT a placeholder: it persists real data for the CLI now.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["JsonStore"]


class JsonStore:
    """Atomic JSON-file collection store. One file per collection."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)  # auto-create (no user setup)

    def _path(self, collection: str) -> Path:
        return self.data_dir / f"{collection}.json"

    def load_all(self, collection: str) -> dict[str, Any]:
        path = self._path(collection)
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            # Corrupt file: keep a forensic copy, start clean (never silent).
            backup = path.with_suffix(".corrupt.bak")
            path.replace(backup)
            return {}

    def save_all(self, collection: str, records: dict[str, Any]) -> None:
        path = self._path(collection)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.data_dir, delete=False, suffix=".tmp"
        ) as fh:
            json.dump(records, fh, indent=2, default=str)
            tmp_name = fh.name
        Path(tmp_name).replace(path)  # atomic on same filesystem

    def upsert(self, collection: str, record_id: str, record: dict[str, Any]) -> None:
        records = self.load_all(collection)
        records[record_id] = record
        self.save_all(collection, records)

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        return self.load_all(collection).get(record_id)

    def all(self, collection: str) -> dict[str, Any]:
        return self.load_all(collection)
