"""User settings persistence + secret handling (MASTER_SPEC §14; R-SEC-1).

Secrets (BYOK API keys, SMTP passwords) go to the OS credential store via
``keyring`` when available, with an explicit, disclosed dev fallback to a
local ``secrets.json`` (gitignored). Secrets are NEVER written to the normal
settings file, NEVER logged, and NEVER exported.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path
from typing import Any

__all__ = ["SettingsStore", "SECRET_KEYS"]

SECRET_KEYS = frozenset({"gemini_api_key", "local_llm_api_key", "smtp_password"})
_SERVICE = "No_Loop"
_ACCOUNT = "secrets"


class SettingsStore:
    """Non-secret settings in ``settings.json``; secrets via keyring/file."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path = self.data_dir / "settings.json"
        self._secrets_path = self.data_dir / "secrets.json"  # gitignored fallback
        self._keyring: Any = None
        try:  # optional extra: keyring
            import keyring  # noqa: F401 — optional extra

            self._keyring = keyring
        except ImportError:
            self._keyring = None  # disclosed dev fallback below

    # ----- non-secret settings -----

    def get(self, key: str, default: Any = None) -> Any:
        data = self._read_settings()
        return data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key in SECRET_KEYS:
            raise ValueError(f"{key} is a secret; use set_secret() (R-SEC-1)")
        data = self._read_settings()
        data[key] = value
        self._write_settings(data)

    def all(self) -> dict[str, Any]:
        return self._read_settings()

    # ----- secrets -----

    def set_secret(self, key: str, value: str) -> None:
        if key not in SECRET_KEYS:
            raise ValueError(f"unknown secret key: {key}")
        if not value or not value.strip():
            raise ValueError("secret value must not be empty")
        if self._keyring is not None:
            self._keyring.set_password(_SERVICE, key, value)
            # record which backend is in use (no value!)
            data = self._read_settings()
            data[f"{key}__backend"] = "keyring"
            self._write_settings(data)
        else:
            existing: dict[str, str] = {}
            if self._secrets_path.exists():
                with contextlib.suppress(ValueError, OSError):
                    existing = json.loads(self._secrets_path.read_text(encoding="utf-8"))
            existing[key] = value
            self._secrets_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            self._restrict(self._secrets_path)
            data = self._read_settings()
            data[f"{key}__backend"] = "file"
            self._write_settings(data)

    def get_secret(self, key: str) -> str | None:
        if key not in SECRET_KEYS:
            raise ValueError(f"unknown secret key: {key}")
        backend = self.get(f"{key}__backend")
        result: str | None = None
        if backend == "keyring" and self._keyring is not None:
            result = str(self._keyring.get_password(_SERVICE, key))
        elif self._secrets_path.exists():
            with contextlib.suppress(ValueError, OSError):
                secrets = json.loads(self._secrets_path.read_text(encoding="utf-8"))
                result = secrets.get(key)
        return result

    def delete_secret(self, key: str) -> None:
        if self._keyring is not None:
            with contextlib.suppress(Exception):  # backend may not have the entry
                self._keyring.delete_password(_SERVICE, key)
        if self._secrets_path.exists():
            try:
                secrets = json.loads(self._secrets_path.read_text(encoding="utf-8"))
                secrets.pop(key, None)
                self._secrets_path.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
            except (ValueError, OSError):
                pass
        data = self._read_settings()
        data.pop(f"{key}__backend", None)
        self._write_settings(data)

    def secret_backend(self, key: str) -> str:
        return str(self.get(f"{key}__backend", "none"))

    # ----- internals -----

    @staticmethod
    def _restrict(path: Path) -> None:
        """Best-effort owner-only permissions (Windows ACLs differ from POSIX)."""
        try:
            if os.name == "posix":
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # best effort; documented in SECURITY.md

    def _read_settings(self) -> dict[str, Any]:
        if not self._settings_path.exists():
            return {}
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def _write_settings(self, data: dict[str, Any]) -> None:
        self._settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
