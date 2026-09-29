"""Bounded scheduler (REFERENCE_GAP_ANALYSIS A7).

Unattended discovery+matching on a per-profile cadence — every run passes the
same caps/limits gates as manual runs; nothing submits, ever. The schedule is
persisted in the store so restarts don't lose the next-run time. Active-hours
windows come from the profile limits (already enforced by the queue).

Design: one daemon tick thread, checks every 60s, runs at most one job per
tick, fully bounded (interval >= 30 min, one profile per tick).
"""

from __future__ import annotations

import threading
import time
from typing import Any

__all__ = ["Scheduler"]

_MIN_INTERVAL_S = 30 * 60  # never tighter than every 30 minutes
_TICK_S = 60


class Scheduler:
    """Persisted, bounded auto-discovery/match loop. Default OFF per profile."""

    def __init__(self, store: Any, run_discover: Any, run_match: Any) -> None:
        self._store = store
        self._run_discover = run_discover
        self._run_match = run_match
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- settings (persisted) -------------------------------------------------
    def get_schedule(self, profile_id: str) -> dict[str, Any]:
        raw = self._store.get("schedules", profile_id) or {}
        return {
            "profile_id": profile_id,
            "enabled": bool(raw.get("enabled")),
            "interval_minutes": int(raw.get("interval_minutes") or 120),
            "next_run_at": raw.get("next_run_at"),
            "last_run_at": raw.get("last_run_at"),
            "last_result": raw.get("last_result"),
        }

    def set_schedule(
        self,
        profile_id: str,
        *,
        enabled: bool,
        interval_minutes: int = 120,
    ) -> dict[str, Any]:
        interval = max(30, min(24 * 60, int(interval_minutes)))  # 30 min .. 24 h
        with self._lock:
            raw = self._store.get("schedules", profile_id) or {}
            updated = {
                **raw,
                "profile_id": profile_id,
                "enabled": bool(enabled),
                "interval_minutes": interval,
                "next_run_at": time.time() + interval * 60 if enabled else None,
            }
            self._store.upsert("schedules", profile_id, updated)
        return self.get_schedule(profile_id)

    # -- loop -----------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="noloop-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _due_profiles(self) -> list[str]:
        now = time.time()
        due: list[str] = []
        for raw in self._store.all("schedules").values():
            if not raw.get("enabled"):
                continue
            next_at = raw.get("next_run_at")
            if next_at is None or now >= float(next_at):
                due.append(str(raw.get("profile_id")))
        return due

    def _loop(self) -> None:
        while not self._stop.wait(_TICK_S):
            try:
                due = self._due_profiles()
                if not due:
                    continue
                profile_id = due[0]  # one profile per tick — strictly bounded
                self._run_for(profile_id)
            except Exception:  # noqa: BLE001, S112 - scheduler must survive any run error
                continue

    def _run_for(self, profile_id: str) -> None:
        started = time.time()
        result: dict[str, Any] = {}
        try:
            disc = self._run_discover(profile_id)
            result["discover"] = disc
        except Exception as exc:  # noqa: BLE001
            result["discover"] = {"ok": False, "error": str(exc)}
        try:
            match = self._run_match(profile_id)
            result["match"] = match
        except Exception as exc:  # noqa: BLE001
            result["match"] = {"ok": False, "error": str(exc)}

        with self._lock:
            raw = self._store.get("schedules", profile_id) or {}
            interval = max(30, min(24 * 60, int(raw.get("interval_minutes") or 120)))
            updated = {
                **raw,
                "last_run_at": started,
                "next_run_at": time.time() + interval * 60,
                "last_result": result,
            }
            self._store.upsert("schedules", profile_id, updated)
