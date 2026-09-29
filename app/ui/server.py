"""No_Loop local web UI + JSON API (stdlib http.server; no heavy web framework).

Transport design (unchanged from the first slice, extended):

* **Live without polling** — Server-Sent Events push every state change and
  every pipeline *stage annotation* to the browser the moment it happens. One
  long-lived connection per tab, heartbeat every 25s.
* **Local-only** — binds 127.0.0.1; static assets are resolved inside
  ``static/`` with a traversal guard.
* **Write-only secrets** — API keys are stored via SettingsStore (keyring/file)
  and are never echoed back to the browser, never logged.

New in this slice: resume import with per-stage progress, profile CRUD +
autofill, discovery/matching, the agent application run, the AI settings
surface (Gemini + any OpenAI-compatible local model by path/model-name) and
downloadable reports.
"""

from __future__ import annotations

import asyncio
import base64
import json
import queue
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

__all__ = ["EventBroker", "UILauncher", "build_handler", "serve"]

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}

_MAX_JSON_BODY = 64 * 1024
_MAX_UPLOAD_BODY = 20 * 1024 * 1024  # base64 of a 10 MB resume + envelope
_TASK_TIMEOUT_S = 180.0


class EventBroker:
    """Fan-out state-change events to all connected SSE clients (per process)."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event: str, data: dict[str, Any]) -> None:
        message = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                self.unsubscribe(q)  # slow client: drop instead of blocking

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


@dataclass
class UILauncher:
    """Wires the UI to the application services (dependency injection point)."""

    data_dir: str
    broker: EventBroker = field(default_factory=EventBroker)
    host: str = "127.0.0.1"
    port: int = 8765
    state_provider: Callable[[], dict[str, Any]] | None = None
    actions: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # -- service accessors (lazy; constructed once; writes are serialised) ---

    def _services(self) -> dict[str, Any]:
        with self._lock:
            if not hasattr(self, "_cache"):
                from app.adapters.settings_store import SettingsStore
                from app.adapters.storage import JsonStore
                from app.services.queue import ExportService, LedgerService

                store = JsonStore(self.data_dir)
                settings = SettingsStore(self.data_dir)
                ledger = LedgerService()
                for data in store.all("applications").values():
                    from app.domain.applications import Application

                    try:
                        ledger.create(Application.model_validate(data))
                    except Exception:  # noqa: BLE001, S112 - one bad record must not block the UI
                        continue
                self._cache = {
                    "store": store,
                    "settings": settings,
                    "ledger": ledger,
                    "exporter": ExportService(ledger),
                }
            return self._cache

    def upsert(self, collection: str, record_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            self._services()["store"].upsert(collection, record_id, record)

    def _publish_state(self, reason: str) -> None:
        self.broker.publish("state_changed", {"reason": reason, "snapshot": self.snapshot()})

    # -- snapshot ------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Full UI state (rendered on load and pushed on every change)."""
        services = self._services()
        ledger = services["ledger"]
        store = services["store"]
        apps = [
            {
                "id": a.id[:8],
                "full_id": a.id,
                "company": a.company,
                "title": a.title,
                "status": a.status.value,
                "entry_method": a.entry_method.value,
                "url": a.application_url,
                "notes": a.notes,
                "profile_id": a.profile_id,
                "artifacts": len(a.artifact_ids),
                "updated_at": a.updated_at.isoformat(),
                "created_at": a.created_at.isoformat(),
                "follow_up_date": a.follow_up_date,
                "failed_reason": (a.failure or {}).get("reason"),
            }
            for a in ledger.all()
        ]
        profiles = [
            {
                "id": pid[:8],
                "full_id": pid,
                "name": p.get("name"),
                "limits": bool(p.get("limits")),
                "targeting": bool(p.get("targeting")),
                "contact": p.get("contact_email") or p.get("contact_name"),
            }
            for pid, p in store.all("profiles").items()
        ]
        gemini_backend = services["settings"].secret_backend("gemini_api_key")
        facts = store.all("facts")
        confirmed = sum(1 for f in facts.values() if f.get("state") == "confirmed")
        runs = store.all("runs")
        return {
            "kanban": apps,
            "profiles": profiles,
            "pipeline_counts": _pipeline_counts(apps),
            "gemini": {"configured": gemini_backend != "none", "backend": gemini_backend},
            "active_profile": str(services["settings"].get("active_profile_id", "") or ""),
            "counts": {
                "jobs": len(store.all("jobs")),
                "applications": len(apps),
                "runs": len(runs),
                "facts": len(facts),
                "facts_confirmed": confirmed,
            },
            "server_time": time.time(),
        }

    # -- settings -------------------------------------------------------------

    def handle_save_gemini_key(self, body: dict[str, Any]) -> dict[str, Any]:
        key = str(body.get("api_key", "")).strip()
        if not key:
            return {"ok": False, "error": "API key must not be empty"}
        settings = self._services()["settings"]
        settings.set_secret("gemini_api_key", key)
        self.broker.publish("settings_changed", {"gemini_configured": True})
        # never echo the key back
        return {"ok": True, "backend": settings.secret_backend("gemini_api_key")}

    def handle_ai_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.services.ai_registry import AIRegistry

        with self._lock:
            registry = AIRegistry(self._services()["settings"])
            try:
                registry.save_config(body)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            if body.get("active_profile_id") is not None:
                registry.settings.set("active_profile_id", str(body.get("active_profile_id") or ""))
        self.broker.publish("settings_changed", {"ai": True})
        return {"ok": True, "status": registry.status()}

    def handle_ai_status(self) -> dict[str, Any]:
        from app.services.ai_registry import AIRegistry

        return {"ok": True, "ai": AIRegistry(self._services()["settings"]).status()}

    async def _ai_test_async(self) -> dict[str, Any]:
        from app.services.ai_registry import AIRegistry

        return await AIRegistry(self._services()["settings"]).test_async()

    def handle_ai_test(self) -> dict[str, Any]:
        return {"ok": True, "test": _run_async(self._ai_test_async())}

    def handle_local_probe(self) -> dict[str, Any]:
        from app.services.ai_registry import AIRegistry

        registry = AIRegistry(self._services()["settings"])
        return {"ok": True, "probe": _run_async(registry.probe_local_async())}

    def handle_diagnose(self) -> dict[str, Any]:
        from app.adapters.system_probe import diagnose

        return {"ok": True, **diagnose()}

    # -- profiles --------------------------------------------------------------

    def list_profiles(self) -> dict[str, Any]:
        store = self._services()["store"]
        out: list[dict[str, Any]] = []
        for pid, raw in store.all("profiles").items():
            facts = [f for f in store.all("facts").values() if f.get("profile_id") == pid]
            out.append(
                {
                    "id": pid,
                    "name": raw.get("name"),
                    "contact_name": raw.get("contact_name"),
                    "contact_email": raw.get("contact_email"),
                    "location": raw.get("location"),
                    "limits": bool(raw.get("limits")),
                    "targeting": bool(raw.get("targeting")),
                    "facts": len(facts),
                    "facts_confirmed": sum(1 for f in facts if f.get("state") == "confirmed"),
                    "created_at": raw.get("created_at"),
                }
            )
        out.sort(key=lambda p: str(p.get("created_at") or ""))
        return {"ok": True, "profiles": out}

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        store = self._services()["store"]
        raw = store.get("profiles", profile_id)
        if not raw:
            return {"ok": False, "error": "profile not found"}
        facts = [f for f in store.all("facts").values() if f.get("profile_id") == profile_id]
        versions = [
            v for v in store.all("resume_versions").values() if v.get("profile_id") == profile_id
        ]
        versions.sort(key=lambda v: int(v.get("version") or 0), reverse=True)
        applications = list(self._services()["ledger"].all(profile_id=profile_id))
        return {
            "ok": True,
            "profile": raw,
            "facts": sorted(facts, key=lambda f: str(f.get("created_at") or "")),
            "resume_versions": versions,
            "applications": len(applications),
        }

    def handle_profile_save(
        self, body: dict[str, Any], profile_id: str | None = None
    ) -> dict[str, Any]:
        from pydantic import ValidationError

        from app.domain.profile import ApplicationLimits, CandidateProfile, TargetPreference

        store = self._services()["store"]
        if profile_id:
            existing = store.get("profiles", profile_id)
            if not existing:
                return {"ok": False, "error": "profile not found"}
        else:
            existing = {"name": str(body.get("name") or "").strip() or "New profile"}

        data = dict(existing)
        for key in ("name", "contact_name", "contact_email", "contact_phone", "location"):
            if key in body:
                data[key] = body[key]
        # Convenience keys: let the UI send flat fields without nesting.
        flat_targeting = {
            k: body[k]
            for k in ("role_titles", "locations", "work_modes", "min_salary", "excluded_keywords")
            if k in body and body[k] is not None
        }
        if flat_targeting:
            merged = {**(data.get("targeting") or {}), **flat_targeting}
            body = {**body, "targeting": merged}
        if "links" in body and isinstance(body["links"], dict):
            data["links"] = {k: str(v) for k, v in body["links"].items() if str(v).strip()}
        if "summary" in body:
            data["extra"] = {**(data.get("extra") or {}), "summary": str(body.get("summary") or "")}
        try:
            if "targeting" in body:
                targeting = body.get("targeting")
                if targeting:
                    data["targeting"] = TargetPreference(
                        role_titles=tuple(
                            str(t).strip()
                            for t in targeting.get("role_titles", [])
                            if str(t).strip()
                        ),
                        locations=tuple(str(t).strip() for t in targeting.get("locations", [])),
                        work_modes=frozenset(targeting.get("work_modes") or ["any"]),
                        min_salary=targeting.get("min_salary"),
                        currency=targeting.get("currency"),
                        notice_period_days=targeting.get("notice_period_days"),
                        excluded_companies=frozenset(targeting.get("excluded_companies") or []),
                        excluded_keywords=frozenset(targeting.get("excluded_keywords") or []),
                        recency_days=int(targeting.get("recency_days") or 30),
                    ).model_dump(mode="json")
                else:
                    data.pop("targeting", None)
            if "limits" in body:
                limits = body.get("limits")
                if limits:
                    hours = limits.get("active_hours") or [9, 20]
                    data["limits"] = ApplicationLimits(
                        per_day=int(limits.get("per_day") or 1),
                        per_week=int(limits.get("per_week") or 1),
                        match_threshold=float(limits.get("match_threshold") or 0.0),
                        company_cooldown_days=int(limits.get("company_cooldown_days") or 0),
                        active_hours=(int(hours[0]), int(hours[1])),
                    ).model_dump(mode="json")
                else:
                    data.pop("limits", None)
            profile = CandidateProfile.model_validate(data)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg')}"
                for err in exc.errors()[:4]
            )
            return {"ok": False, "error": details or "invalid profile data"}
        except (ValueError, TypeError, IndexError) as exc:
            return {"ok": False, "error": f"invalid targeting/limits: {exc}"}

        # user-entered skills are CONFIRMED facts by definition (CLI parity)
        for skill in body.get("skills") or []:
            name = str(skill).strip()
            if not name:
                continue
            self._add_confirmed_skill(profile.id, name)

        self.upsert("profiles", profile.id, profile.model_dump(mode="json"))
        self._services()["settings"].set("active_profile_id", profile.id)
        self._publish_state("profile_saved")
        return {"ok": True, "profile_id": profile.id, "profile": profile.model_dump(mode="json")}

    def _add_confirmed_skill(self, profile_id: str, name: str) -> None:
        from app.domain.facts import FactProvenance, ResumeFact, SkillClaim

        store = self._services()["store"]
        for existing in store.all("facts").values():
            skill = existing.get("skill") or {}
            if (
                existing.get("profile_id") == profile_id
                and skill.get("name", "").lower() == name.lower()
            ):
                return
        fact = ResumeFact(
            profile_id=profile_id,
            field_class="skill",
            skill=SkillClaim(name=name),
            confidence=1.0,
            provenance=FactProvenance(user_entry=True),
        )
        store.upsert("facts", fact.id, fact.model_dump(mode="json"))

    # -- facts ------------------------------------------------------------------

    def list_facts(self, profile_id: str, state: str | None = None) -> dict[str, Any]:
        facts = []
        for raw in self._services()["store"].all("facts").values():
            if profile_id and raw.get("profile_id") != profile_id:
                continue
            if state and raw.get("state") != state:
                continue
            facts.append(raw)
        facts.sort(key=lambda f: str(f.get("created_at") or ""))
        return {"ok": True, "facts": facts}

    def handle_fact_decision(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.domain.facts import ResumeFact

        fact_id = str(body.get("fact_id") or "")
        decision = str(body.get("decision") or "")
        store = self._services()["store"]
        raw = store.get("facts", fact_id)
        if not raw:
            return {"ok": False, "error": "fact not found"}
        fact = ResumeFact.model_validate(raw)
        try:
            updated = fact.confirm() if decision == "confirm" else fact.reject()
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        store.upsert("facts", fact_id, updated.model_dump(mode="json"))
        self._publish_state("fact_decision")
        return {"ok": True, "state": updated.state.value}

    def handle_facts_bulk(self, body: dict[str, Any]) -> dict[str, Any]:
        decisions = body.get("decisions") or []
        results = []
        for item in decisions:
            results.append(
                self.handle_fact_decision(
                    {"fact_id": item.get("fact_id"), "decision": item.get("decision")}
                )
            )
        return {"ok": all(r.get("ok") for r in results), "results": results}

    # -- resume import (async + annotated) --------------------------------------

    def handle_resume_import(self, body: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        filename = str(body.get("filename") or "resume.txt")
        if body.get("content_base64"):
            try:
                data = base64.b64decode(str(body["content_base64"]), validate=False)
            except (ValueError, TypeError):
                return {"ok": False, "error": "invalid base64 payload"}
        elif body.get("text"):
            data = str(body["text"]).encode("utf-8")
            filename = str(body.get("filename") or "pasted-resume.txt")
        else:
            return {"ok": False, "error": "no file content supplied"}

        use_ai = bool(body.get("use_ai", True))
        job_id = f"import-{uuid.uuid4().hex[:8]}"
        self.broker.publish(
            "progress",
            {
                "kind": "resume",
                "job_id": job_id,
                "stage": "queued",
                "status": "running",
                "label": "Queued",
                "detail": f"{filename} · {len(data) // 1024} KB",
                "progress": 0,
                "elapsed_ms": 0,
            },
        )
        threading.Thread(
            target=self._run_import,
            args=(job_id, profile_id, filename, data, use_ai),
            daemon=True,
            name="noloop-import",
        ).start()
        return {"ok": True, "job_id": job_id, "filename": filename}

    def _run_import(
        self, job_id: str, profile_id: str, filename: str, data: bytes, use_ai: bool
    ) -> None:
        from app.services.resume_pipeline import ResumePipeline

        services = self._services()
        started = time.perf_counter()
        try:
            pipeline = ResumePipeline(services["store"], services["settings"])
            result = pipeline.run(
                profile_id=profile_id,
                filename=filename,
                data=data,
                use_ai=use_ai,
                job_id=job_id,
                on_progress=lambda event: self.broker.publish("progress", event),
            )
            payload = result.to_dict()
        except Exception as exc:  # noqa: BLE001 - surfaced honestly to the browser
            payload = {
                "ok": False,
                "job_id": job_id,
                "error_reason": f"{exc.__class__.__name__}: {exc}",
                "stages": [],
            }
        payload["job_id"] = job_id
        payload["wall_ms"] = int((time.perf_counter() - started) * 1000)
        self.broker.publish("task_done", {"kind": "resume", "job_id": job_id, "result": payload})
        self._publish_state("resume_imported")

    # -- discovery / matching -----------------------------------------------------

    def handle_discover(self, body: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(200, int(body.get("limit") or 30)))
        source = str(body.get("source") or "arbeitnow").strip().lower()
        if source not in ("arbeitnow", "remotive", "adzuna"):
            return {
                "ok": False,
                "error": f"unknown source {source!r} (arbeitnow | remotive | adzuna)",
            }
        query = str(body.get("query") or "").strip() or None
        job_id = f"discover-{uuid.uuid4().hex[:8]}"
        threading.Thread(
            target=self._run_discover,
            args=(job_id, limit, source, query),
            daemon=True,
            name="noloop-discover",
        ).start()
        return {"ok": True, "job_id": job_id, "limit": limit, "source": source}

    def _run_discover(
        self, job_id: str, limit: int, source: str = "arbeitnow", query: str | None = None
    ) -> None:
        from app.adapters.sources.arbeitnow import ArbeitnowAdapter
        from app.adapters.sources.remotive import RemotiveAdapter
        from app.domain.jobs import Job
        from app.services.dedup import JobIdentityResolver

        store = self._services()["store"]
        resolver = JobIdentityResolver()
        for raw in store.all("jobs").values():
            try:
                resolver.add(Job.model_validate(raw))
            except Exception:  # noqa: BLE001, S112 - one bad record must not stop discovery
                continue

        def note(status: str, detail: str, progress: int) -> None:
            self.broker.publish(
                "progress",
                {
                    "kind": "discover",
                    "job_id": job_id,
                    "stage": "fetch",
                    "status": status,
                    "label": "Discovery",
                    "detail": detail,
                    "progress": progress,
                    "elapsed_ms": 0,
                },
            )

        note("running", "contacting the public job feed…", 10)
        fetched = stored = duplicates = 0
        error: str | None = None
        try:

            def _adapter() -> Any:
                if source == "remotive":
                    return RemotiveAdapter()
                if source == "adzuna":
                    from app.adapters.sources.adzuna import AdzunaAdapter
                    from app.domain.errors import DomainError

                    settings = self._services()["settings"]
                    try:
                        return AdzunaAdapter(
                            app_id=str(settings.get("adzuna_app_id") or ""),
                            app_key=str(settings.get_secret("adzuna_app_key") or ""),
                        )
                    except DomainError as exc:
                        from app.domain.errors import SourceFetchError

                        raise SourceFetchError(
                            stage="discovery.configure", reason=str(exc)
                        ) from exc
                return ArbeitnowAdapter()

            async def collect() -> list[Any]:
                adapter = _adapter()
                out: list[Any] = []
                async for job in adapter.discover(limit=limit, query=query):
                    out.append(job)
                return out

            jobs = _run_async(collect())
            fetched = len(jobs)
            note("running", f"{fetched} postings received — de-duplicating", 60)
            for job in jobs:
                clusters_before = len(resolver.clusters())
                resolver.add(job)
                if len(resolver.clusters()) == clusters_before:
                    duplicates += 1  # merged into an existing identity
                    continue
                self.upsert("jobs", job.id, job.model_dump(mode="json"))
                stored += 1
        except Exception as exc:  # noqa: BLE001 - network/policy failures are reported
            error = f"{exc.__class__.__name__}: {exc}"

        if error:
            note("failed", error, 100)
        else:
            note("done", f"{stored} new · {duplicates} duplicates skipped", 100)
        self.broker.publish(
            "task_done",
            {
                "kind": "discover",
                "job_id": job_id,
                "result": {
                    "ok": error is None,
                    "fetched": fetched,
                    "stored": stored,
                    "duplicates": duplicates,
                    "error": error,
                },
            },
        )
        self._publish_state("discovery_complete")

    def handle_match(self, body: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        job_id = f"match-{uuid.uuid4().hex[:8]}"
        threading.Thread(
            target=self._run_match, args=(job_id, profile_id), daemon=True, name="noloop-match"
        ).start()
        return {"ok": True, "job_id": job_id}

    def _record_task_failure(self, kind: str, job_id: str, exc: Exception) -> None:
        """Background tasks must never fail silently: record + publish (R-TRUTH-1)."""
        self.upsert(
            "tasks",
            job_id,
            {
                "id": job_id,
                "kind": kind,
                "status": "failed",
                "error": f"{exc.__class__.__name__}: {exc}",
                "at": time.time(),
            },
        )
        self.broker.publish(
            "task_done",
            {"kind": kind, "job_id": job_id, "result": {"ok": False, "error": str(exc)}},
        )

    def _run_match(self, job_id: str, profile_id: str) -> None:
        from app.domain.jobs import Job
        from app.services.dedup import JobIdentityResolver
        from app.services.match_engine import MatchEngine

        store = self._services()["store"]
        profile_raw = store.get("profiles", profile_id) or {}
        from app.domain.profile import CandidateProfile

        try:
            profile = CandidateProfile.model_validate(profile_raw)
        except Exception as exc:  # noqa: BLE001
            self.broker.publish(
                "task_done",
                {
                    "kind": "match",
                    "job_id": job_id,
                    "result": {"ok": False, "error": f"profile error: {exc}"},
                },
            )
            return
        if profile.targeting is None:
            self.broker.publish(
                "task_done",
                {
                    "kind": "match",
                    "job_id": job_id,
                    "result": {
                        "ok": False,
                        "error": "set target roles before matching (Profile → Targeting)",
                    },
                },
            )
            return

        skills = [
            (f.get("skill") or {}).get("name")
            for f in store.all("facts").values()
            if f.get("profile_id") == profile_id
            and f.get("state") == "confirmed"
            and f.get("skill")
        ]
        engine = MatchEngine(
            profile_id=profile_id,
            profile_skills=[s for s in skills if s],
            targeting=profile.targeting,
        )
        jobs: list[Job] = []
        for raw in store.all("jobs").values():
            try:
                jobs.append(Job.model_validate(raw))
            except Exception:  # noqa: BLE001, S112
                continue
        resolver = JobIdentityResolver()
        for job in jobs:
            resolver.add(job)
        unique = [c.canonical for c in resolver.clusters()]

        try:
            self._score_unique(job_id, profile_id, engine, store, unique)
        except Exception as exc:  # noqa: BLE001 - recorded, never silent
            self._record_task_failure("match", job_id, exc)
            return

    def _score_unique(
        self,
        job_id: str,
        profile_id: str,
        engine: Any,
        store: Any,
        unique: list[Any],
    ) -> None:
        scored: list[tuple[float, dict[str, Any]]] = []
        for index, job in enumerate(unique, start=1):
            result = engine.score(job)
            row = {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "work_mode": job.work_mode,
                "url": job.url,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_currency": job.salary_currency,
                "score": round(result.score, 4),
                "gate": result.hard_gate.value,
                "gate_reasons": list(result.gate_reasons),
                "factors": [f.model_dump() for f in result.factors],
                "missing_requirements": list(result.missing_requirements),
                "notes": list(result.notes),
                "profile_id": profile_id,
                "at": time.time(),
            }
            scored.append((round(result.score, 4), row))
            store.upsert("matches", f"{profile_id}:{job.id}", row)
            if index % 5 == 0 or index == len(unique):
                self.broker.publish(
                    "progress",
                    {
                        "kind": "match",
                        "job_id": job_id,
                        "stage": "score",
                        "status": "running",
                        "label": "Scoring",
                        "detail": f"{index}/{len(unique)} jobs scored",
                        "progress": int(index * 100 / max(1, len(unique))),
                        "elapsed_ms": 0,
                    },
                )
        scored.sort(key=lambda pair: -pair[0])
        results = [row for _, row in scored]
        self.broker.publish(
            "task_done",
            {
                "kind": "match",
                "job_id": job_id,
                "result": {"ok": True, "count": len(results), "results": results},
            },
        )
        self._publish_state("match_complete")

    # -- agent run ----------------------------------------------------------------

    # -- Knowledge Base (A1) --------------------------------------------------

    def handle_kb_save(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.domain.knowledge import KBEntry, KBEntryKind

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        entry_id = str(body.get("id") or "").strip() or None
        try:
            kind = KBEntryKind(str(body.get("kind") or "project"))
            if entry_id:
                existing = self._services()["store"].get("kb_entries", entry_id)
                if not existing:
                    return {"ok": False, "error": "entry not found"}
                entry = KBEntry.model_validate(
                    {
                        **existing,
                        "title": str(body.get("title") or existing.get("title")),
                        "body": str(body.get("body") or existing.get("body")),
                        "kind": kind,
                        "tags": tuple(body.get("tags") or existing.get("tags") or ()),
                    }
                )
            else:
                entry = KBEntry(
                    profile_id=profile_id,
                    kind=kind,
                    title=str(body.get("title") or "").strip(),
                    body=str(body.get("body") or "").strip(),
                    tags=tuple(str(t) for t in (body.get("tags") or [])),
                )
        except Exception as exc:  # noqa: BLE001 - validation errors are user-actionable
            return {"ok": False, "error": str(exc)}
        self._services()["store"].upsert("kb_entries", entry.id, entry.model_dump(mode="json"))
        self._publish_state("kb_changed")
        return {"ok": True, "id": entry.id}

    def handle_kb_delete(self, body: dict[str, Any]) -> dict[str, Any]:
        entry_id = str(body.get("id") or "").strip()
        if not entry_id:
            return {"ok": False, "error": "id is required"}
        self._services()["store"].delete("kb_entries", entry_id)
        self._publish_state("kb_changed")
        return {"ok": True}

    def _profile_and_facts(self, profile_id: str) -> tuple[Any, list[Any]] | None:
        """Validated (profile, confirmed facts) or None if the profile is missing."""
        from app.domain.facts import ResumeFact
        from app.domain.profile import CandidateProfile

        raw = self._services()["store"].get("profiles", profile_id)
        if not raw:
            return None
        prof = CandidateProfile.model_validate(raw)
        facts = [
            ResumeFact.model_validate(f)
            for f in self._services()["store"].all("facts").values()
            if f.get("profile_id") == profile_id and f.get("state") == "confirmed"
        ]
        return prof, facts

    def handle_render_resume(self, body: dict[str, Any]) -> dict[str, Any]:
        """Facts + KB + JD -> tailored resume PDF/DOCX bytes (base64). ADR-7."""
        import base64

        from app.domain.knowledge import KBEntry
        from app.services.renderer import RenderError, render_resume_docx, render_resume_pdf
        from app.services.resume_builder import ResumeAssembler, ats_score

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        loaded = self._profile_and_facts(profile_id)
        if loaded is None:
            return {"ok": False, "error": "profile not found"}
        prof, facts = loaded
        jd_text = str(body.get("jd_text") or "")
        kb_entries = [
            KBEntry.model_validate(e)
            for e in self._services()["store"].all("kb_entries").values()
            if e.get("profile_id") == profile_id
        ]
        assembler = ResumeAssembler(facts, prof)
        try:
            doc = assembler.build(jd_text=jd_text, kb_entries=kb_entries)
            fmt = str(body.get("format") or "pdf").lower()
            if fmt == "docx":
                payload = render_resume_docx(doc)
                mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                payload = render_resume_pdf(doc)
                mime = "application/pdf"
        except RenderError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - honest error envelope
            return {"ok": False, "error": f"render failed: {exc.__class__.__name__}: {exc}"}
        score = ats_score(assembler.resume_text(doc), jd_text) if jd_text.strip() else None
        return {
            "ok": True,
            "format": fmt,
            "mime": mime,
            "content_base64": base64.b64encode(payload).decode("ascii"),
            "bytes": len(payload),
            "ats_score": score,
        }

    def handle_render_prep_pack(self, body: dict[str, Any]) -> dict[str, Any]:
        """JD + confirmed facts -> interview prep pack DOCX (A2)."""
        import base64
        import re

        from app.services.question_answerer import QuestionAnswerer, build_fact_sheet
        from app.services.renderer import RenderError, render_prep_pack_docx

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        loaded = self._profile_and_facts(profile_id)
        if loaded is None:
            return {"ok": False, "error": "profile not found"}
        prof, facts = loaded
        jd_text = str(body.get("jd_text") or "").strip()
        if not jd_text:
            return {"ok": False, "error": "jd_text is required"}
        sentences = re.split(r"[.!?\n]+", jd_text)
        req_sents = [
            s.strip()
            for s in sentences
            if len(s.strip()) > 25
            and any(
                k in s.lower()
                for k in ("experience", "must", "responsib", "require", "skil", "year")
            )
        ][:6]
        answerer = QuestionAnswerer(build_fact_sheet(facts, prof))
        questions = []
        for s in req_sents:
            ans = answerer.answer(s)
            questions.append(
                {
                    "question": s,
                    "outline": ans.answer,
                    "source": (
                        "your confirmed facts"
                        if ans.source == "facts"
                        else "draft your own — not in facts"
                    ),
                }
            )
        pack = {
            "job_title": str(body.get("job_title") or "").strip(),
            "company": str(body.get("company") or "").strip(),
            "prepared_at": time.strftime("%Y-%m-%d %H:%M"),
            "questions": questions,
            "talking_points": [
                e.get("title")
                for e in self._services()["store"].all("kb_entries").values()
                if e.get("profile_id") == profile_id
            ][:5],
            "questions_to_ask": [
                "What does success look like in the first 90 days?",
                "How is the team structured?",
                "What are the biggest current challenges?",
            ],
        }
        try:
            payload = render_prep_pack_docx(pack)
        except RenderError as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_base64": base64.b64encode(payload).decode("ascii"),
            "bytes": len(payload),
        }

    # -- ATS fill plans + answer sheets (P3/P4) ---------------------------------

    def handle_ats_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        """Greenhouse-style fill plan from a public questions schema."""
        from app.services.apply_sheets import ATSFillPlanner

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        loaded = self._profile_and_facts(profile_id)
        if loaded is None:
            return {"ok": False, "error": "profile not found"}
        prof, facts = loaded
        planner = ATSFillPlanner(facts, prof)
        plan = planner.plan_from_questions(
            platform=str(body.get("platform") or "greenhouse"),
            job_url=str(body.get("job_url") or ""),
            questions=list(body.get("questions") or []),
        )
        self.upsert("ats_plans", plan["id"], plan)
        self._publish_state("ats_plan")
        return {"ok": True, "plan": plan}

    def handle_answer_sheet(self, body: dict[str, Any]) -> dict[str, Any]:
        """Assisted answer sheet for LinkedIn Easy-Apply / Naukri (no bots)."""
        from app.domain.jobs import Job
        from app.services.apply_sheets import build_answer_sheet

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        loaded = self._profile_and_facts(profile_id)
        if loaded is None:
            return {"ok": False, "error": "profile not found"}
        prof, facts = loaded
        job = None
        job_id = str(body.get("job_id") or "").strip()
        if job_id:
            raw = self._services()["store"].get("jobs", job_id)
            if raw:
                job = Job.model_validate(raw)
        platform = str(body.get("platform") or "linkedin").strip().lower()
        if platform not in ("linkedin", "naukri", "indeed", "instahyre", "wellfound", "cutshort"):
            return {"ok": False, "error": f"unknown platform {platform!r}"}
        sheet = build_answer_sheet(platform=platform, facts=facts, profile=prof, job=job)
        self.upsert("answer_sheets", sheet["id"], sheet)
        return {"ok": True, "sheet": sheet}

    # -- scheduler (P5) ---------------------------------------------------------

    def handle_schedule(self, body: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        sched = self._scheduler()
        if "enabled" in body:
            return {
                "ok": True,
                "schedule": sched.set_schedule(
                    profile_id,
                    enabled=bool(body.get("enabled")),
                    interval_minutes=int(body.get("interval_minutes") or 120),
                ),
            }
        return {"ok": True, "schedule": sched.get_schedule(profile_id)}

    def _scheduler(self) -> Any:
        with self._lock:
            cache = self._services()
            if "scheduler" not in cache:
                from app.services.scheduler import Scheduler

                def _disc(pid: str) -> Any:
                    self.handle_discover({"limit": 30})
                    return {"ok": True}

                def _match(pid: str) -> Any:
                    self.handle_match({"profile_id": pid})
                    return {"ok": True}

                cache["scheduler"] = Scheduler(cache["store"], _disc, _match)
                cache["scheduler"].start()
            return cache["scheduler"]

    # -- employer intel (P6) ------------------------------------------------------

    def handle_company_intel(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.services.employer_intel import EmployerIntel

        company = str(body.get("company") or "").strip()
        if not company:
            return {"ok": False, "error": "company is required"}
        services = self._services()
        intel = EmployerIntel(services["store"], services["ledger"])
        if body.get("note"):
            added = intel.add_note(company, str(body["note"]))
            if not added.get("ok"):
                return added
        return {"ok": True, "report": intel.company_report(company)}

    def handle_company_top(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.services.employer_intel import EmployerIntel

        services = self._services()
        intel = EmployerIntel(services["store"], services["ledger"])
        return {"ok": True, "companies": intel.top_companies()}

    def handle_agent_run(self, body: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            return {"ok": False, "error": "profile_id is required"}
        limit = max(1, min(50, int(body.get("limit") or 10)))
        job_id = f"run-{uuid.uuid4().hex[:8]}"
        threading.Thread(
            target=self._run_agent,
            args=(job_id, profile_id, limit),
            daemon=True,
            name="noloop-agent",
        ).start()
        return {"ok": True, "job_id": job_id, "limit": limit}

    def _run_agent(self, job_id: str, profile_id: str, limit: int) -> None:
        from app.services.agent_run import AgentRunService

        services = self._services()
        started = time.perf_counter()
        try:
            service = AgentRunService(services["store"], services["ledger"], services["settings"])
            with self._lock:
                result = service.run(
                    profile_id=profile_id,
                    limit=limit,
                    on_event=lambda event: self.broker.publish("progress", event),
                )
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}", "steps": []}
        result["job_id"] = job_id
        result["wall_ms"] = int((time.perf_counter() - started) * 1000)
        self.broker.publish("task_done", {"kind": "agent", "job_id": job_id, "result": result})
        self._publish_state("agent_run_complete")

    # -- applications ---------------------------------------------------------------

    def handle_quick_add(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.domain.applications import Application, ApplicationStatus, EntryMethod

        profile_id = str(body.get("profile_id") or "").strip()
        company = str(body.get("company") or "").strip()
        title = str(body.get("title") or "").strip()
        if not profile_id or not company or not title:
            return {"ok": False, "error": "profile_id, company and title are required"}
        services = self._services()
        application = Application(
            profile_id=profile_id,
            entry_method=EntryMethod.MANUAL,
            company=company,
            title=title,
            application_url=body.get("url") or None,
            notes=body.get("notes") or None,
            submission_evidence={"method": "user_assertion", "note": "recorded via quick-add"},
            status=ApplicationStatus.REVIEW_REQUIRED,
        )
        try:
            services["ledger"].create(application)
            services["ledger"].transition(
                application.id,
                ApplicationStatus.SUBMITTED,
                submission_evidence=application.submission_evidence,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        stored = services["ledger"].get(application.id)
        assert stored is not None
        self.upsert("applications", stored.id, stored.model_dump(mode="json"))
        self._publish_state("quick_add")
        return {"ok": True, "application_id": stored.id}

    # -- board -----------------------------------------------------------------

    def handle_move_card(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.domain.applications import ApplicationStatus

        services = self._services()
        app_id_prefix = str(body.get("application_id", ""))
        target = str(body.get("to_status", ""))
        full = None
        for a in services["ledger"].all():
            if a.id.startswith(app_id_prefix):
                full = a
                break
        if full is None:
            return {"ok": False, "error": "unknown application"}
        try:
            target_status = ApplicationStatus(target)
        except ValueError:
            return {"ok": False, "error": f"unknown status {target}"}
        evidence = (
            {"method": "user_confirmation", "confirmed_by": "kanban-drag", "at": body.get("at")}
            if target_status is ApplicationStatus.SUBMITTED
            else None
        )
        try:
            services["ledger"].transition(
                full.id,
                target_status,
                submission_evidence=evidence,
                failure={
                    "stage": "kanban",
                    "reason": str(body.get("reason", "user marked failed")),
                    "retryable": True,
                }
                if target_status is ApplicationStatus.FAILED
                else None,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        persisted = services["ledger"].get(full.id)
        assert persisted is not None
        self.upsert("applications", persisted.id, persisted.model_dump(mode="json"))
        self._publish_state("move_card")
        return {"ok": True}

    def handle_snapshot(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "snapshot": self.snapshot()}


def _run_async(coro: Any) -> Any:
    """Run a coroutine from a worker thread (each HTTP request has its own)."""
    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _pipeline_counts(apps: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"discovered": 0, "ready": 0, "drafted": 0, "review": 0, "submitted": 0, "closed": 0}
    for a in apps:
        s = a["status"]
        if s in ("discovered", "shortlisted"):
            counts["discovered"] += 1
        elif s in ("ready",):
            counts["ready"] += 1
        elif s in ("drafted",):
            counts["drafted"] += 1
        elif s in ("review_required", "verification_required", "failed"):
            counts["review"] += 1
        elif s in ("submitted", "interview", "offer"):
            counts["submitted"] += 1
        else:
            counts["closed"] += 1
    return counts


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_JSON_GET: list[tuple[re.Pattern[str], Callable[..., dict[str, Any]]]] = []
_JSON_POST: list[tuple[re.Pattern[str], Callable[..., dict[str, Any]]]] = []


def _register_routes() -> None:
    if _JSON_GET:
        return

    _JSON_GET.extend(
        [
            (re.compile(r"^/api/state$"), lambda ln, *_: {"ok": True, "snapshot": ln.snapshot()}),
            (re.compile(r"^/api/meta$"), _meta),
            (re.compile(r"^/api/profiles$"), lambda ln, *_: ln.list_profiles()),
            (
                re.compile(r"^/api/profiles/([^/]+)$"),
                lambda ln, m, *_: ln.get_profile(unquote(m.group(1))),
            ),
            (
                re.compile(r"^/api/facts$"),
                lambda ln, m, b, q: ln.list_facts(
                    q.get("profile_id", [""])[0], q.get("state", [None])[0]
                ),
            ),
            (re.compile(r"^/api/jobs$"), lambda ln, m, b, q: _jobs(ln, q)),
            (re.compile(r"^/api/matches$"), lambda ln, m, b, q: _matches(ln, q)),
            (re.compile(r"^/api/applications$"), lambda ln, m, b, q: _applications(ln, q)),
            (
                re.compile(r"^/api/assisted-packages$"),
                lambda ln, m, b, q: _assisted_packages(ln, q),
            ),
            (re.compile(r"^/api/runs$"), lambda ln, m, b, q: _runs(ln, q)),
            (re.compile(r"^/api/ai/status$"), lambda ln, m, b, q: ln.handle_ai_status()),
            (re.compile(r"^/api/system/diagnose$"), lambda ln, m, b, q: ln.handle_diagnose()),
            (re.compile(r"^/api/reports/summary$"), lambda ln, m, b, q: _report_summary(ln, q)),
            (re.compile(r"^/api/reports/preview$"), lambda ln, m, b, q: _report_preview(ln, q)),
        ]
    )
    _JSON_POST.extend(
        [
            (
                re.compile(r"^/api/settings/gemini-key$"),
                lambda ln, m, b, *_: ln.handle_save_gemini_key(b),
            ),
            (re.compile(r"^/api/settings/ai$"), lambda ln, m, b: ln.handle_ai_settings(b)),
            (re.compile(r"^/api/kb$"), lambda ln, m, b: ln.handle_kb_save(b)),
            (re.compile(r"^/api/kb/delete$"), lambda ln, m, b: ln.handle_kb_delete(b)),
            (re.compile(r"^/api/render/resume$"), lambda ln, m, b: ln.handle_render_resume(b)),
            (
                re.compile(r"^/api/render/prep-pack$"),
                lambda ln, m, b: ln.handle_render_prep_pack(b),
            ),
            (re.compile(r"^/api/ats/plan$"), lambda ln, m, b: ln.handle_ats_plan(b)),
            (re.compile(r"^/api/answer-sheet$"), lambda ln, m, b: ln.handle_answer_sheet(b)),
            (re.compile(r"^/api/schedule$"), lambda ln, m, b: ln.handle_schedule(b)),
            (re.compile(r"^/api/company/intel$"), lambda ln, m, b: ln.handle_company_intel(b)),
            (re.compile(r"^/api/company/top$"), lambda ln, m, b: ln.handle_company_top(b)),
            (
                re.compile(r"^/api/settings/adzuna$"),
                lambda ln, m, b: ln.handle_adzuna_credentials(b),
            ),
            (re.compile(r"^/api/ai/test$"), lambda ln, m, b: ln.handle_ai_test()),
            (re.compile(r"^/api/ai/local-probe$"), lambda ln, m, b: ln.handle_local_probe()),
            (re.compile(r"^/api/board/move$"), lambda ln, m, b: ln.handle_move_card(b)),
            (re.compile(r"^/api/state/refresh$"), lambda ln, m, b: ln.handle_snapshot(b)),
            (re.compile(r"^/api/profiles$"), lambda ln, m, b, *_: ln.handle_profile_save(b)),
            (
                re.compile(r"^/api/profiles/([^/]+)$"),
                lambda ln, m, b, *_: ln.handle_profile_save(b, unquote(m.group(1))),
            ),
            (re.compile(r"^/api/resume/import$"), lambda ln, m, b: ln.handle_resume_import(b)),
            (re.compile(r"^/api/facts/decision$"), lambda ln, m, b: ln.handle_fact_decision(b)),
            (re.compile(r"^/api/facts/bulk$"), lambda ln, m, b: ln.handle_facts_bulk(b)),
            (re.compile(r"^/api/discover$"), lambda ln, m, b: ln.handle_discover(b)),
            (re.compile(r"^/api/match$"), lambda ln, m, b: ln.handle_match(b)),
            (re.compile(r"^/api/agent/run$"), lambda ln, m, b: ln.handle_agent_run(b)),
            (re.compile(r"^/api/applications$"), lambda ln, m, b: ln.handle_quick_add(b)),
        ]
    )


_SSE_PATTERN = re.compile(r"^/api/events$")
_DOWNLOAD_PATTERN = re.compile(r"^/api/reports/download$")
_DOWNLOAD_MIME = {"csv": "text/csv", "json": "application/json", "html": "text/html"}


def _meta(ln: UILauncher, *args: Any) -> dict[str, Any]:
    """Dynamic metadata (stages, transitions, policies) for the front-end."""
    from app.domain.applications import APPLICATION_TRANSITIONS, ApplicationStatus
    from app.services.agent_run import RUN_STEPS
    from app.services.platform_policy import PLATFORM_POLICIES
    from app.services.reports import REPORT_FORMATS, REPORT_KINDS
    from app.services.resume_pipeline import STAGE_META, STAGE_ORDER

    transitions = {
        key.value: sorted(target.value for target in targets)
        for key, targets in APPLICATION_TRANSITIONS.items()
    }
    return {
        "ok": True,
        "stages": [{"id": sid, "weight": w, **STAGE_META[sid]} for sid, w in STAGE_ORDER],
        "run_steps": [{"id": sid, "label": label} for sid, label in RUN_STEPS],
        "columns": [
            {"id": "discovered", "label": "Discovered"},
            {"id": "shortlisted", "label": "Shortlisted"},
            {"id": "ready", "label": "Ready"},
            {"id": "drafted", "label": "Drafted"},
            {"id": "review_required", "label": "Review"},
            {"id": "submitted", "label": "Submitted"},
            {"id": "interview", "label": "Interview"},
            {"id": "offer", "label": "Offer"},
            {"id": "closed", "label": "Closed"},
        ],
        "statuses": [s.value for s in ApplicationStatus],
        "transitions": transitions,
        "reports": {"kinds": list(REPORT_KINDS), "formats": list(REPORT_FORMATS)},
        "policies": [
            {
                "key": p.key,
                "name": p.display_name,
                "status": p.status.value,
                "can_automate": p.can_automate,
                "note": p.policy_note,
                "source": p.policy_source_url,
            }
            for p in PLATFORM_POLICIES.values()
        ],
        "work_modes": ["any", "remote", "hybrid", "onsite"],
    }


def _jobs(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    from app.domain.jobs import Job

    rows = []
    for raw in ln._services()["store"].all("jobs").values():
        try:
            job = Job.model_validate(raw)
        except Exception:  # noqa: BLE001, S112 - one bad record must not break the list
            continue
        rows.append(
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "work_mode": job.work_mode,
                "url": job.url,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_currency": job.salary_currency,
                "posted_at": job.posted_at.isoformat() if job.posted_at else None,
                "adapter": job.source.adapter_id,
                "excerpt": " ".join(job.description_text.split())[:280],
            }
        )
    rows.sort(key=lambda r: str(r.get("posted_at") or ""), reverse=True)
    limit = int(q.get("limit", ["60"])[0])
    return {"ok": True, "jobs": rows[:limit], "total": len(rows)}


def _matches(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    profile_id = q.get("profile_id", [""])[0]
    rows = [
        r
        for r in ln._services()["store"].all("matches").values()
        if not profile_id or str(r.get("profile_id")) == profile_id
    ]
    rows.sort(key=lambda r: -(r.get("score") or 0))
    return {"ok": True, "matches": rows}


def _assisted_packages(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    """Packages for one application (or all), for the assisted-flow viewer."""
    app_id = q.get("application_id", [""])[0]
    packages = [
        p
        for p in ln._services()["store"].all("assisted_packages").values()
        if not app_id or str(p.get("application_id")) == app_id
    ]
    packages.sort(key=lambda p: -(p.get("created_at") or 0))
    return {"ok": True, "packages": packages}


def _applications(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    profile_id = q.get("profile_id", [""])[0] or None
    records = ln._services()["ledger"].all(profile_id=profile_id)
    return {
        "ok": True,
        "applications": [
            {
                "id": a.id,
                "company": a.company,
                "title": a.title,
                "status": a.status.value,
                "entry_method": a.entry_method.value,
                "url": a.application_url,
                "source_url": a.source_url,
                "notes": a.notes,
                "profile_id": a.profile_id,
                "job_id": a.job_id,
                "artifact_ids": list(a.artifact_ids),
                "evidence": a.submission_evidence,
                "failure": a.failure,
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat(),
            }
            for a in records
        ],
    }


def _runs(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    profile_id = q.get("profile_id", [""])[0]
    runs = [
        r
        for r in ln._services()["store"].all("runs").values()
        if not profile_id or r.get("profile_id") == profile_id
    ]
    runs.sort(key=lambda r: str(r.get("started_at", "")), reverse=True)
    return {"ok": True, "runs": runs}


def _report_service(ln: UILauncher) -> Any:
    from app.services.reports import ReportService

    services = ln._services()
    return ReportService(services["store"], services["ledger"])


def _report_summary(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    profile_id = q.get("profile_id", [""])[0] or None
    return {"ok": True, "summary": _report_service(ln).summary(profile_id)}


def _report_preview(ln: UILauncher, q: dict[str, list[str]]) -> dict[str, Any]:
    profile_id = q.get("profile_id", [""])[0] or None
    report = q.get("report", ["applications"])[0]
    service = _report_service(ln)
    try:
        columns = service.columns(report)
        rows = service.records(report, profile_id)[:200]
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "report": report, "columns": list(columns), "rows": rows}


def _report_download(ln: UILauncher, q: dict[str, list[str]]) -> tuple[str, str, bytes]:
    """Build a report file for download → ``(filename, content_type, body)``."""
    from datetime import UTC, datetime

    from app.services.reports import REPORT_FORMATS, REPORT_KINDS, ReportService

    services = ln._services()
    service = ReportService(services["store"], services["ledger"])
    profile_id = q.get("profile_id", [""])[0] or None
    report = q.get("report", ["applications"])[0]
    fmt = q.get("format", ["csv"])[0]
    if fmt not in REPORT_FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    if report not in REPORT_KINDS:
        raise ValueError(f"unknown report: {report}")
    if fmt == "csv":
        payload = service.to_csv(report, profile_id)
    elif fmt == "json":
        payload = service.to_json(report, profile_id)
    else:
        payload = service.to_html(report, profile_id)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"noloop-{report}-{stamp}.{fmt}"
    return filename, _DOWNLOAD_MIME[fmt], payload.encode("utf-8")


def build_handler(launcher: UILauncher) -> type[BaseHTTPRequestHandler]:
    """Build a handler class closed over the launcher (no globals)."""
    _register_routes()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet: no request logs
            pass

        # ---- helpers ----
        def _json(self, code: int, payload: Any) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self, max_bytes: int = _MAX_JSON_BODY) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0 or length > max_bytes:
                return {}
            try:
                parsed = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}

        def _parts(self) -> tuple[str, dict[str, list[str]]]:
            parsed = urlparse(self.path)
            return unquote(parsed.path), parse_qs(parsed.query)

        # ---- routes ----
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            path, query = self._parts()
            if _SSE_PATTERN.match(path):
                self._serve_sse()
                return
            if _DOWNLOAD_PATTERN.match(path):
                self._serve_download(query)
                return
            if path.startswith("/api/"):
                for pattern, handler in _JSON_GET:
                    match = pattern.match(path)
                    if match:
                        try:
                            self._json(200, handler(launcher, match, {}, query))
                        except Exception as exc:  # noqa: BLE001 - honest error envelope
                            self._json(
                                500,
                                {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"},
                            )
                        return
                self._json(404, {"ok": False, "error": "not found"})
                return
            self._serve_static(path)

        def do_POST(self) -> None:  # noqa: N802
            path, _ = self._parts()
            max_bytes = _MAX_UPLOAD_BODY if path == "/api/resume/import" else _MAX_JSON_BODY
            body = self._body(max_bytes)
            if not body and path == "/api/resume/import":
                self._json(413, {"ok": False, "error": "upload too large or malformed"})
                return
            for pattern, handler in _JSON_POST:
                match = pattern.match(path)
                if match:
                    try:
                        result = handler(launcher, match, body)
                    except Exception as exc:  # noqa: BLE001
                        self._json(500, {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"})
                        return
                    self._json(200 if result.get("ok", True) else 400, result)
                    return
            self._json(404, {"ok": False, "error": "not found"})

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        # ---- SSE ----
        def _serve_sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = launcher.broker.subscribe()
            try:
                # initial snapshot so a fresh tab is immediately correct
                init = (
                    "event: state_changed\ndata: "
                    + json.dumps({"snapshot": launcher.snapshot()}, default=str)
                    + "\n\n"
                )
                self.wfile.write(init.encode("utf-8"))
                self.wfile.flush()
                while True:
                    try:
                        message = q.get(timeout=25)  # heartbeat < 30s proxy default
                        self.wfile.write(message.encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")  # comment = keep-alive
                    self.wfile.flush()
            except (ConnectionAbortedError, BrokenPipeError, OSError):
                pass
            finally:
                launcher.broker.unsubscribe(q)

        # ---- static ----
        def _serve_download(self, query: dict[str, list[str]]) -> None:
            try:
                filename, content_type, body = _report_download(launcher, query)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001 - honest error envelope
                self._json(500, {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"})
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _serve_static(self, path: str) -> None:
            relative = path[1:]
            if relative.startswith("static/"):
                relative = relative[len("static/") :]
            if relative in ("", "index", "index.html"):
                relative = "index.html"
            try:
                target = (_STATIC / relative).resolve()
            except (OSError, ValueError):
                self._json(404, {"ok": False, "error": "not found"})
                return
            if _STATIC.resolve() not in target.parents and target != _STATIC.resolve():
                self._json(403, {"ok": False, "error": "forbidden"})  # traversal guard
                return
            if not target.is_file():
                self._json(404, {"ok": False, "error": "not found"})
                return
            body = target.read_bytes()
            content_type = _MIME.get(target.suffix.lower(), "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            cacheable = target.suffix.lower() in {".png", ".jpg", ".webp", ".svg", ".ico", ".woff2"}
            self.send_header("Cache-Control", "max-age=86400" if cacheable else "no-cache")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

    return Handler


def serve(launcher: UILauncher) -> ThreadingHTTPServer:  # pragma: no cover - server loop
    handler = build_handler(launcher)
    server = ThreadingHTTPServer((launcher.host, launcher.port), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="noloop-ui")
    thread.start()
    return server
