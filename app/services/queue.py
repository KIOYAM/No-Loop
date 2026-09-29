"""Application queue + ledger services (LOOP-4; APPLICATION_LEDGER.md).

Queue admission enforces, in order:
1. profile limits are FULLY configured (no silent caps — MASTER_SPEC §4)
2. hard gate pass + soft score >= user threshold (S1)
3. per-day / per-week caps
4. company cooldown
5. active hours window

The ledger service owns all state transitions + in-memory append-only audit
(SR persistence lands with the storage slice; port-compatible).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.applications import (
    Application,
    ApplicationStatus,
)
from app.domain.errors import ValidationError
from app.domain.jobs import Job
from app.domain.matching import MatchResult
from app.domain.profile import CandidateProfile

__all__ = ["AdmissionDecision", "ApplicationQueue", "LedgerService", "ExportService"]


@dataclass
class AdmissionDecision:
    admitted: bool
    reason: str
    job_id: str
    score: float


class ApplicationQueue:
    """Admission control between matching and the ledger (S1 threshold pipeline)."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or datetime.now

    def admit(
        self,
        *,
        profile: CandidateProfile,
        job: Job,
        match: MatchResult,
        submitted_today: int,
        submitted_this_week: int,
        company_last_applied: datetime | None = None,
    ) -> AdmissionDecision:
        limits = profile.limits
        if limits is None or not limits.is_configured:
            return AdmissionDecision(
                False,
                "queue disabled: application limits are not fully"
                " configured (set every limit first)",
                job.id,
                match.score,
            )
        if not match.is_eligible:
            return AdmissionDecision(False, "hard gate failed", job.id, match.score)
        if match.score < (limits.match_threshold or 0.0):
            return AdmissionDecision(
                False,
                f"score {match.score:.2f} below threshold {limits.match_threshold:.2f}",
                job.id,
                match.score,
            )
        if submitted_today >= (limits.per_day or 0):
            return AdmissionDecision(
                False, f"daily cap reached ({limits.per_day})", job.id, match.score
            )
        if submitted_this_week >= (limits.per_week or 0):
            return AdmissionDecision(
                False, f"weekly cap reached ({limits.per_week})", job.id, match.score
            )
        if company_last_applied is not None and limits.company_cooldown_days:
            from datetime import timedelta

            cooldown_end = company_last_applied + timedelta(days=limits.company_cooldown_days)
            if self._clock() < cooldown_end:
                return AdmissionDecision(
                    False,
                    f"company cooldown active until {cooldown_end.date()}"
                    f" ({limits.company_cooldown_days}d)",
                    job.id,
                    match.score,
                )
        now = self._clock()
        if limits.active_hours:
            start, end = limits.active_hours
            hour = now.hour
            in_window = start <= hour < end if start <= end else hour >= start or hour < end
            if not in_window:  # overnight window, e.g. 22..6
                return AdmissionDecision(
                    False, f"outside active hours {start:02d}:00-{end:02d}:00", job.id, match.score
                )
        return AdmissionDecision(True, "admitted", job.id, match.score)


class LedgerService:
    """Append-only audit trail over domain state transitions.

    Every transition is validated by the domain first; the service records the
    audit event with the §17/§evidence payloads. In-memory here; the storage
    slice swaps the backing store without changing this contract.
    """

    def __init__(self) -> None:
        self._records: dict[str, Application] = {}
        self._audit: list[dict[str, Any]] = []

    def create(self, application: Application) -> Application:
        if application.id in self._records:
            raise ValidationError(stage="ledger.create", reason="duplicate application id")
        self._records[application.id] = application
        self._audit.append(
            {
                "event": "created",
                "application_id": application.id,
                "status": application.status.value,
                "at": application.created_at.isoformat(),
            }
        )
        return application

    def get(self, application_id: str) -> Application | None:
        return self._records.get(application_id)

    def all(self, *, profile_id: str | None = None) -> list[Application]:
        records = list(self._records.values())
        if profile_id:
            records = [r for r in records if r.profile_id == profile_id]
        return records

    def transition(
        self,
        application_id: str,
        target: ApplicationStatus,
        *,
        submission_evidence: dict[str, Any] | None = None,
        failure: dict[str, Any] | None = None,
    ) -> Application:
        current = self._records.get(application_id)
        if current is None:
            raise ValidationError(
                stage="ledger.transition", reason=f"unknown application {application_id}"
            )
        updated = current.transition(
            target, submission_evidence=submission_evidence, failure=failure
        )
        self._records[application_id] = updated
        self._audit.append(
            {
                "event": "transition",
                "application_id": application_id,
                "from": current.status.value,
                "to": target.value,
                "at": updated.updated_at.isoformat(),
                "evidence_attached": submission_evidence is not None,
                "failure_attached": failure is not None,
            }
        )
        return updated

    @property
    def audit_trail(self) -> list[dict[str, Any]]:
        return list(self._audit)

    def replace(self, application: Application) -> Application:
        """Persist a side-effect of a transition (e.g. generated artifact ids).

        The record keeps its status — this is *not* a state transition; it only
        links the artifacts the pipeline produced so reports can show them.
        """
        if application.id not in self._records:
            raise ValidationError(
                stage="ledger.replace", reason=f"unknown application {application.id}"
            )
        self._records[application.id] = application
        self._audit.append(
            {
                "event": "artifacts_linked",
                "application_id": application.id,
                "artifact_count": len(application.artifact_ids),
                "at": application.updated_at.isoformat(),
            }
        )
        return application


class ExportService:
    """CSV/JSON export of the ledger (excludes credential references by design)."""

    def __init__(self, ledger: LedgerService) -> None:
        self._ledger = ledger

    def to_json(self, *, profile_id: str | None = None) -> str:
        import json

        records = self._ledger.all(profile_id=profile_id)
        return json.dumps([self._public_record(r) for r in records], indent=2, default=str)

    def to_csv(self, *, profile_id: str | None = None) -> str:
        import csv
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "profile_id",
                "entry_method",
                "company",
                "title",
                "status",
                "created_at",
                "application_url",
            ]
        )
        for r in self._ledger.all(profile_id=profile_id):
            writer.writerow(
                [
                    r.id,
                    r.profile_id,
                    r.entry_method.value,
                    r.company,
                    r.title,
                    r.status.value,
                    r.created_at,
                    r.application_url or "",
                ]
            )
        return buffer.getvalue()

    @staticmethod
    def _public_record(r: Application) -> dict[str, Any]:
        data = r.model_dump(mode="json")
        data.pop("consent_envelope_id", None)  # internal reference, not user data
        return data
