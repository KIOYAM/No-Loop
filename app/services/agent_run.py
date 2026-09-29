"""Agent run — the live, observable job-application pipeline (LOOP-4/7/8).

One "run" walks the stored (deduped) jobs and, for each one, executes the full
application workflow with a per-step annotation pushed to the browser over
SSE, so the UI can animate exactly what the agents are doing and why.

Honesty constraints that shape this module (binding):

* **No fake submissions.** v0.1 is fill-only + assisted; every prohibited or
  assisted-only platform gets a *prepared package* and a REVIEW_REQUIRED ledger
  record — the human clicks Submit (R-POLICY-3).
* **The queue stays disabled until limits are configured** (MASTER_SPEC §4).
  When they are missing the run still scores and previews, but records nothing:
  the ``admit``/``create`` steps say so explicitly.
* **Every step is auditable** — the run is persisted to the ``runs`` collection
  and shows up in the Reports page as the agent activity log.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.adapters.ai_providers import RuleBasedProvider
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.domain.facts import FactState, ResumeFact
from app.domain.jobs import Job
from app.domain.profile import CandidateProfile
from app.services.ai_registry import AIRegistry
from app.services.dedup import JobIdentityResolver
from app.services.email_drafter import EmailDrafter
from app.services.match_engine import MatchEngine
from app.services.platform_policy import build_assisted_package, policy_for
from app.services.question_answerer import QuestionAnswerer, build_fact_sheet
from app.services.queue import ApplicationQueue, LedgerService

__all__ = ["AgentRunService", "RUN_STEPS"]

#: Ordered steps of one application, with the label the UI animates.
RUN_STEPS: tuple[tuple[str, str], ...] = (
    ("profile", "Loading profile"),
    ("limits", "Checking application limits"),
    ("dedupe", "De-duplicating"),
    ("policy", "Platform policy check"),
    ("match", "Scoring fit"),
    ("admit", "Queue admission"),
    ("create", "Opening ledger record"),
    ("ready", "Marking ready"),
    ("draft", "Drafting outreach"),
    ("review", "Preparing your review"),
)

_STEP_LABEL = dict(RUN_STEPS)
_TODAY_STATUSES = frozenset(
    {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
        ApplicationStatus.REVIEW_REQUIRED,
        ApplicationStatus.VERIFICATION_REQUIRED,
    }
)


def _platform_key(url: str | None) -> str:
    """Map a job URL to a registered policy key (vendor-free in the domain)."""
    if not url:
        return "unknown"
    host = (urlsplit(url).hostname or "").lower()
    for key in ("linkedin", "indeed", "naukri"):
        if key in host:
            return key
    return "ats_fill" if host else "unknown"


class AgentRunService:
    """Executes one bounded run and reports every step as it happens."""

    def __init__(
        self,
        store: Any,
        ledger: LedgerService | None = None,
        settings: Any = None,
    ) -> None:
        self.store = store
        self.ledger = ledger or LedgerService()
        self._settings = settings
        self._provider: Any = None
        for record in store.all("applications").values():
            try:
                self.ledger.create(Application.model_validate(record))
            except Exception:  # noqa: BLE001, S112 - a corrupt record must not stop the run
                continue

    def _draft_provider(self) -> Any:
        """Resolve the AI provider once per run (Gemini key -> local -> rule)."""
        if self._provider is not None:
            return self._provider
        if self._settings is not None:
            try:
                self._provider = AIRegistry(self._settings).resolve()
                return self._provider
            except Exception:  # noqa: BLE001 - provider resolution must never kill a run
                return RuleBasedProvider()
        self._provider = RuleBasedProvider()
        return self._provider

    # -- public ------------------------------------------------------------

    def run(
        self,
        *,
        profile_id: str,
        limit: int = 10,
        job_ids: list[str] | None = None,
        on_event: Any = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex[:12]
        started = datetime.now(UTC)
        steps: list[dict[str, Any]] = []
        summary = {
            "considered": 0,
            "matched": 0,
            "admitted": 0,
            "recorded": 0,
            "blocked": 0,
            "skipped": 0,
            "failed": 0,
        }

        def emit(
            job: Job | None,
            step: str,
            status: str,
            detail: str,
            *,
            index: int,
            total: int,
            score: float | None = None,
        ) -> None:
            entry = {
                "run_id": run_id,
                "step": step,
                "label": _STEP_LABEL.get(step, step),
                "status": status,
                "detail": detail,
                "index": index,
                "total": total,
                "score": score,
                "job_id": job.id if job else None,
                "company": job.company if job else None,
                "title": job.title if job else None,
                "at": datetime.now(UTC).isoformat(),
            }
            steps.append(entry)
            if on_event is not None:
                on_event({"kind": "agent", **entry})

        profile = self._profile(profile_id)
        jobs = self._jobs(job_ids)
        total = len(jobs)

        if profile is None:
            emit(None, "profile", "failed", f"unknown profile {profile_id}", index=0, total=total)
            return self._finish(run_id, started, steps, summary, profile_id)

        emit(
            None,
            "profile",
            "done",
            f"{profile.name} · "
            f"{'targeting set' if profile.targeting else 'no targeting configured'}",
            index=0,
            total=total,
        )

        limits_ready = profile.limits_configured
        if profile.targeting is None:
            emit(
                None,
                "limits",
                "skipped",
                "set target roles first (Profile → Targeting)",
                index=0,
                total=total,
            )
            summary["blocked"] = total
            return self._finish(run_id, started, steps, summary, profile_id)

        emit(
            None,
            "limits",
            "done" if limits_ready else "skipped",
            (
                f"queue enabled · {profile.limits.per_day}/day, "
                f"threshold {profile.limits.match_threshold:.2f}"
                if limits_ready and profile.limits
                else "queue disabled — set every application limit to start recording"
            ),
            index=0,
            total=total,
        )

        facts = self._confirmed_facts(profile_id)
        skills = [f.skill.name for f in facts if f.field_class == "skill" and f.skill]
        engine = MatchEngine(
            profile_id=profile_id, profile_skills=skills, targeting=profile.targeting
        )
        queue = ApplicationQueue()
        known_jobs = {a.job_id for a in self.ledger.all() if a.job_id}

        for position, job in enumerate(jobs, start=1):
            summary["considered"] += 1
            score: float | None = None

            # de-dup ------------------------------------------------------
            if job.id in known_jobs:
                emit(
                    job,
                    "dedupe",
                    "skipped",
                    "already in your ledger",
                    index=position,
                    total=total,
                )
                summary["skipped"] += 1
                continue
            emit(
                job,
                "dedupe",
                "done",
                f"new · source {job.source.adapter_id}",
                index=position,
                total=total,
            )

            # policy -------------------------------------------------------
            policy = policy_for(_platform_key(job.url))
            emit(
                job,
                "policy",
                "done",
                f"{policy.display_name}: {policy.status.value} — {policy.policy_note[:90]}",
                index=position,
                total=total,
            )

            # match --------------------------------------------------------
            result = engine.score(job)
            score = result.score
            if not result.is_eligible:
                emit(
                    job,
                    "match",
                    "skipped",
                    "hard gate: " + "; ".join(result.gate_reasons[:2]),
                    index=position,
                    total=total,
                    score=score,
                )
                summary["skipped"] += 1
                continue
            summary["matched"] += 1
            explanation = result.explain().splitlines()
            why = (
                explanation[1].strip()[:80] if len(explanation) > 1 else f"score {result.score:.2f}"
            )
            emit(
                job,
                "match",
                "done",
                f"score {result.score:.2f} — {why}",
                index=position,
                total=total,
                score=score,
            )

            # admission -----------------------------------------------------
            decision = queue.admit(
                profile=profile,
                job=job,
                match=result,
                submitted_today=self._submitted_since(profile_id, "day"),
                submitted_this_week=self._submitted_since(profile_id, "week"),
                company_last_applied=self._last_application(profile_id, job.company),
            )
            if not decision.admitted:
                status = "skipped" if limits_ready else "blocked"
                emit(
                    job,
                    "admit",
                    status,
                    decision.reason,
                    index=position,
                    total=total,
                    score=score,
                )
                summary["blocked" if not limits_ready else "skipped"] += 1
                continue
            emit(
                job,
                "admit",
                "done",
                "within every limit",
                index=position,
                total=total,
                score=score,
            )
            summary["admitted"] += 1

            if not limits_ready:  # defensive: admit() already refuses, keep the promise
                continue

            # record + stage transitions ------------------------------------
            record = self._record(
                run_id=run_id,
                profile=profile,
                job=job,
                facts=facts,
                emit=lambda *a, job=job, position=position, score=score, **k: emit(
                    job, *a, index=position, total=total, score=score, **k
                ),
            )
            if record is not None:
                summary["recorded"] += 1
                known_jobs.add(job.id)

        return self._finish(run_id, started, steps, summary, profile_id)

    # -- per-job recording ---------------------------------------------------

    def _record(
        self,
        *,
        run_id: str,
        profile: CandidateProfile,
        job: Job,
        facts: list[ResumeFact],
        emit: Any,
    ) -> Application | None:
        try:
            application = Application(
                profile_id=profile.id,
                entry_method=EntryMethod.ASSISTED,
                job_id=job.id,
                company=job.company,
                title=job.title,
                source_url=job.url,
                application_url=job.url,
                automation_run_id=run_id,
                status=ApplicationStatus.DISCOVERED,
            )
            self.ledger.create(application)
        except Exception as exc:  # noqa: BLE001
            emit("create", "failed", f"{exc.__class__.__name__}: {exc}")
            return None

        artifact_ids: list[str] = []
        try:
            for target in (ApplicationStatus.SHORTLISTED, ApplicationStatus.READY):
                self.ledger.transition(application.id, target)
            emit("ready", "done", "shortlisted → ready (all gates passed)")
        except ValueError as exc:
            emit("ready", "failed", str(exc))
            self._persist(application.id)
            return None

        # draft ------------------------------------------------------------
        try:
            draft = EmailDrafter(self._draft_provider()).draft(
                profile_name=profile.contact_name or profile.name, facts=facts, job=job
            )
            draft_id = uuid.uuid4().hex[:12]
            self.store.upsert(
                "email_drafts",
                draft_id,
                {
                    "id": draft_id,
                    "application_id": application.id,
                    "job_id": job.id,
                    "body": draft.body,
                    "provider": draft.provider,
                    "evidence": draft.evidence,
                },
            )
            artifact_ids.append(draft_id)
            self.ledger.transition(application.id, ApplicationStatus.DRAFTED)
            emit(
                "draft",
                "done",
                f"ready via {draft.provider} · "
                f"{len(draft.evidence.get('skills_used', []))} confirmed skills cited",
            )
        except Exception as exc:  # noqa: BLE001 - guard rejections are honest outcomes
            emit("draft", "failed", f"{exc}")
            self._persist(application.id)
            return None

        # assisted package ---------------------------------------------------
        try:
            policy = policy_for(_platform_key(job.url))
            sheet = build_fact_sheet(facts, profile)
            answerer = QuestionAnswerer(sheet)
            ready: list[dict[str, str]] = []
            needs_user: list[dict[str, str]] = []
            for question in (
                "How many years of experience do you have?",
                "What is your current location?",
                "What are your key skills?",
            ):
                answer = answerer.answer(question)
                bucket = needs_user if answer.needs_user else ready
                bucket.append(
                    {
                        "question": question,
                        "answer": answer.answer or "—",
                        "source": answer.source,
                        "reason": answer.reason or "",
                    }
                )
            package = build_assisted_package(
                platform_key=policy.key,
                policy=policy,
                answers_ready=ready,
                answers_needing_user=needs_user,
                email_draft=draft.body,
                job_title=job.title,
                company=job.company,
            )
            package_id = uuid.uuid4().hex[:12]
            self.store.upsert(
                "assisted_packages",
                package_id,
                {"id": package_id, "application_id": application.id, **package.to_dict()},
            )
            artifact_ids.append(package_id)
            self.ledger.transition(application.id, ApplicationStatus.REVIEW_REQUIRED)
            emit(
                "review",
                "done",
                f"package ready for you — {len(ready)} answers filled, "
                f"{len(needs_user)} need you · you click Submit",
            )
        except Exception as exc:  # noqa: BLE001
            emit("review", "failed", f"{exc}")
            self._persist(application.id)
            return None

        stored = self.ledger.get(application.id)
        if stored is not None and artifact_ids:
            stored = stored.model_copy(update={"artifact_ids": tuple(artifact_ids)})
            self.ledger.replace(stored)
        self._persist(application.id)
        return self.ledger.get(application.id)

    def _persist(self, application_id: str) -> None:
        record = self.ledger.get(application_id)
        if record is not None:
            self.store.upsert("applications", record.id, record.model_dump(mode="json"))

    # -- helpers -------------------------------------------------------------

    def _profile(self, profile_id: str) -> CandidateProfile | None:
        data = self.store.get("profiles", profile_id)
        if not data:
            return None
        try:
            return CandidateProfile.model_validate(data)
        except Exception:  # noqa: BLE001 - invalid stored profile is reported, not raised
            return None

    def _jobs(self, job_ids: list[str] | None) -> list[Job]:
        jobs: list[Job] = []
        for raw in self.store.all("jobs").values():
            try:
                jobs.append(Job.model_validate(raw))
            except Exception:  # noqa: BLE001, S112
                continue
        if job_ids:
            wanted = set(job_ids)
            jobs = [j for j in jobs if j.id in wanted or j.id[:8] in wanted]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        resolver = JobIdentityResolver()
        for job in jobs:
            resolver.add(job)
        canonical = {c.canonical.id for c in resolver.clusters()}
        return [j for j in jobs if j.id in canonical]

    def _confirmed_facts(self, profile_id: str) -> list[ResumeFact]:
        from app.domain.facts import ResumeFact as Fact

        out: list[ResumeFact] = []
        for raw in self.store.all("facts").values():
            if raw.get("profile_id") != profile_id or raw.get("state") != FactState.CONFIRMED.value:
                continue
            try:
                out.append(Fact.model_validate(raw))
            except Exception:  # noqa: BLE001, S112
                continue
        return out

    def _submitted_since(self, profile_id: str, window: str) -> int:
        now = datetime.now(UTC)
        count = 0
        for record in self.ledger.all(profile_id=profile_id):
            if record.status not in _TODAY_STATUSES:
                continue
            stamp = (
                record.created_at
                if record.created_at.tzinfo
                else record.created_at.replace(tzinfo=UTC)
            )
            if (window == "day" and stamp.date() == now.date()) or (
                window == "week" and stamp.isocalendar()[:2] == now.isocalendar()[:2]
            ):
                count += 1
        return count

    def _last_application(self, profile_id: str, company: str) -> datetime | None:
        best: datetime | None = None
        for record in self.ledger.all(profile_id=profile_id):
            if record.company.lower() != company.lower():
                continue
            stamp = record.created_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            if best is None or stamp > best:
                best = stamp
        return best

    def _finish(
        self,
        run_id: str,
        started: datetime,
        steps: list[dict[str, Any]],
        summary: dict[str, int],
        profile_id: str,
    ) -> dict[str, Any]:
        finished = datetime.now(UTC)
        payload = {
            "run_id": run_id,
            "profile_id": profile_id,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "summary": summary,
            "steps": steps,
        }
        self.store.upsert("runs", run_id, payload)
        return payload
