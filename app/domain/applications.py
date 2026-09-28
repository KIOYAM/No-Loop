"""Application domain model + Readiness Gate state machine
(APPLICATION_LEDGER.md; NOLOOP_DEV_KICKOFF-spec §3 Round 6).

The ledger tracks ALL applications: automated (v0.1 = fill-only),
assisted (No_Loop prepared, human submitted), and fully manual (Quick-Add).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ApplicationStatus",
    "EntryMethod",
    "APPLICATION_TRANSITIONS",
    "Application",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class EntryMethod(enum.StrEnum):
    AUTOMATED = "automated"
    ASSISTED = "assisted"
    MANUAL = "manual"


class ApplicationStatus(enum.StrEnum):
    DISCOVERED = "discovered"
    SHORTLISTED = "shortlisted"
    READY = "ready"
    DRAFTED = "drafted"
    REVIEW_REQUIRED = "review_required"
    SUBMITTED = "submitted"
    VERIFICATION_REQUIRED = "verification_required"
    FAILED = "failed"
    WITHDRAWN = "withdrawn"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    OFFER = "offer"
    CLOSED = "closed"
    REJECTED_BY_USER = "rejected_by_user"
    SKIPPED = "skipped"


#: Legal transitions (APPLICATION_LEDGER.md state machine). Append-only ledger
#: events validate against this map before persisting.
APPLICATION_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.DISCOVERED: frozenset(
        {
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.SKIPPED,
            ApplicationStatus.REJECTED_BY_USER,
        }
    ),
    ApplicationStatus.SHORTLISTED: frozenset(
        {ApplicationStatus.READY, ApplicationStatus.SKIPPED, ApplicationStatus.REJECTED_BY_USER}
    ),
    ApplicationStatus.READY: frozenset(
        {ApplicationStatus.DRAFTED, ApplicationStatus.SKIPPED, ApplicationStatus.REJECTED_BY_USER}
    ),
    ApplicationStatus.DRAFTED: frozenset(
        {
            ApplicationStatus.REVIEW_REQUIRED,
            ApplicationStatus.SKIPPED,
            ApplicationStatus.REJECTED_BY_USER,
        }
    ),
    ApplicationStatus.REVIEW_REQUIRED: frozenset(
        {
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.VERIFICATION_REQUIRED,
            ApplicationStatus.FAILED,
            ApplicationStatus.SKIPPED,
            ApplicationStatus.REJECTED_BY_USER,
        }
    ),
    ApplicationStatus.VERIFICATION_REQUIRED: frozenset(
        {ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED}
    ),
    ApplicationStatus.SUBMITTED: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.REJECTED,
            ApplicationStatus.CLOSED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.FAILED: frozenset({ApplicationStatus.READY, ApplicationStatus.CLOSED}),
    ApplicationStatus.WITHDRAWN: frozenset({ApplicationStatus.CLOSED}),
    ApplicationStatus.REJECTED: frozenset({ApplicationStatus.CLOSED}),
    ApplicationStatus.INTERVIEW: frozenset(
        {ApplicationStatus.OFFER, ApplicationStatus.REJECTED, ApplicationStatus.CLOSED}
    ),
    ApplicationStatus.OFFER: frozenset({ApplicationStatus.CLOSED, ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.CLOSED: frozenset(),
    ApplicationStatus.REJECTED_BY_USER: frozenset(),
    ApplicationStatus.SKIPPED: frozenset(),
}

_TERMINAL = frozenset(
    {
        ApplicationStatus.CLOSED,
        ApplicationStatus.REJECTED_BY_USER,
        ApplicationStatus.SKIPPED,
    }
)


def _initial_status(entry_method: EntryMethod, has_job: bool) -> ApplicationStatus:
    if entry_method == EntryMethod.MANUAL:
        # Quick-Add records typically start at the user-asserted stage; the
        # caller passes the user's chosen status via initial_status override.
        return (
            ApplicationStatus.SUBMITTED if has_job is False else ApplicationStatus.REVIEW_REQUIRED
        )
    if entry_method == EntryMethod.ASSISTED:
        return ApplicationStatus.DISCOVERED
    return ApplicationStatus.DISCOVERED


class Application(BaseModel):
    """One ledger record. State changes go through :meth:`transition` only."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_id)
    profile_id: str = Field(min_length=1, description="Owning candidate profile.")
    entry_method: EntryMethod
    job_id: str | None = Field(
        default=None, description="Null for manual entries with no discovered job."
    )
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=2048)
    application_url: str | None = Field(default=None, max_length=2048)
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    artifact_ids: tuple[str, ...] = Field(default=())
    email_draft_id: str | None = None
    automation_run_id: str | None = None
    consent_envelope_id: str | None = None
    submission_evidence: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Automated: completion signal + hashes. Assisted/manual: user confirmation record."
        ),
    )
    failure: dict[str, Any] | None = Field(
        default=None, description="MASTER_SPEC §17 record when FAILED"
    )
    follow_up_date: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_creation(self) -> Application:
        if self.source_url is not None and not self.source_url.lower().startswith(
            ("http://", "https://")
        ):
            raise ValueError("source_url must be http(s)")
        if self.application_url is not None and not self.application_url.lower().startswith(
            ("http://", "https://")
        ):
            raise ValueError("application_url must be http(s)")
        if self.entry_method == EntryMethod.MANUAL and self.status is ApplicationStatus.DISCOVERED:
            # Quick-Add never enters the discovery pipeline (APPLICATION_LEDGER.md).
            # Default manual records to REVIEW_REQUIRED; caller may set a later
            # user-asserted status explicitly.
            self.status = ApplicationStatus.REVIEW_REQUIRED
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def transition(
        self,
        target: ApplicationStatus,
        *,
        submission_evidence: dict[str, Any] | None = None,
        failure: dict[str, Any] | None = None,
    ) -> Application:
        """Return a new Application in ``target`` status, enforcing invariants.

        Invariant 1 (R-TRUTH-5): entering SUBMITTED requires submission_evidence.
        Invariant 3: transitions follow APPLICATION_TRANSITIONS (append-only events
        upstream); FAILED requires the §17 failure record.
        """
        allowed = APPLICATION_TRANSITIONS[self.status]
        if target not in allowed:
            raise ValueError(f"illegal transition {self.status.value} -> {target.value}")

        if target == ApplicationStatus.SUBMITTED:
            if not submission_evidence:
                raise ValueError("entering SUBMITTED requires submission evidence (R-TRUTH-5)")
            if self.entry_method == EntryMethod.AUTOMATED and not self.consent_envelope_id:
                raise ValueError(
                    "automated submission requires a recorded consent envelope (R-SEC-3)"
                )

        if target == ApplicationStatus.VERIFICATION_REQUIRED and not submission_evidence:
            raise ValueError("VERIFICATION_REQUIRED requires the partial evidence captured so far")

        if target == ApplicationStatus.FAILED and not failure:
            raise ValueError(
                "FAILED requires the §17 failure record (stage/reason/retryable/user_action)"
            )

        if self.is_terminal:
            raise ValueError(f"record is terminal ({self.status.value}); no further transitions")

        return self.model_copy(
            update={
                "status": target,
                "submission_evidence": submission_evidence or self.submission_evidence,
                "failure": failure or self.failure,
                "updated_at": _utcnow(),
            }
        )
