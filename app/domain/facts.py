"""Fact ledger domain models (RESEARCH.md S4; MASTER_SPEC §3).

The fact ledger is the truth foundation of No_Loop:
- Facts are extracted observations with provenance + confidence.
- Facts are *inferred* until the user confirms them.
- Downstream generation may consume ONLY confirmed facts (S2 anti-fabrication).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["FactState", "FactProvenance", "ResumeFact", "SkillClaim"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class FactState(enum.StrEnum):
    """Lifecycle of a fact. Only CONFIRMED facts may feed generation (LOOP-5)."""

    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class FactProvenance(BaseModel):
    """Where a fact came from. Provenance is mandatory — no orphan facts."""

    model_config = ConfigDict(frozen=True)

    document_id: str | None = Field(
        default=None, description="ResumeDocument id, when extracted from a file."
    )
    user_entry: bool = Field(
        default=False, description="True when the user typed/edited this fact directly."
    )
    page: int | None = Field(default=None, ge=1)
    span: tuple[int, int] | None = Field(default=None, description="Character span in source text.")
    extraction_rule: str | None = Field(
        default=None, description="Extractor/rule identifier that produced the fact."
    )
    observed_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _must_have_origin(self) -> FactProvenance:
        if self.document_id is None and not self.user_entry:
            raise ValueError("fact must have provenance: document_id or user_entry=True")
        return self


class SkillClaim(BaseModel):
    """A technology/skill claim with its asserted proficiency evidence level."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    normalized_name: str | None = Field(
        default=None, description="Taxonomy surface form (ESCO/O*NET-informed); set by normalizer."
    )
    claimed_level: str | None = Field(
        default=None,
        description=(
            "Level AS CLAIMED by the source text (e.g. '2 years', 'advanced'). Never inferred here."
        ),
    )

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("skill name must not be blank")
        return v


class ResumeFact(BaseModel):
    """A single structured observation about the candidate.

    Invariants (tested):
    - state starts as INFERRED unless the user entered it directly.
    - CONFIRMED/REJECTED transitions carry a decision timestamp.
    - a REJECTED fact can never return to INFERRED/CONFIRMED without new provenance
      (a new fact must be created instead).
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_id)
    profile_id: str = Field(
        min_length=1, description="Owning candidate profile (multi-profile scoping)."
    )
    field_class: str = Field(
        min_length=1,
        description=(
            "Field class, e.g. 'skill', 'employer', 'title', 'education', 'date_range', 'location'."
        ),
    )
    value: Any = None
    skill: SkillClaim | None = None
    confidence: float = Field(
        ge=0.0, le=1.0, description="Extractor confidence; 1.0 for user_entry."
    )
    state: FactState = FactState.INFERRED
    provenance: FactProvenance
    created_at: datetime = Field(default_factory=_utcnow)
    decided_at: datetime | None = None

    @model_validator(mode="after")
    def _check_initial_state(self) -> ResumeFact:
        if self.provenance.user_entry and self.state == FactState.INFERRED:
            # Direct user entry is by definition confirmed.
            object.__setattr__(self, "state", FactState.CONFIRMED)
            object.__setattr__(self, "decided_at", _utcnow())
        if (
            self.state == FactState.INFERRED
            and self.confidence >= 1.0
            and not self.provenance.user_entry
        ):
            raise ValueError("confidence 1.0 is reserved for user-entered facts")
        return self

    def confirm(self) -> ResumeFact:
        """User confirms this inferred fact (returns a new immutable instance)."""
        self._ensure_transition_allowed(FactState.CONFIRMED)
        return self.model_copy(update={"state": FactState.CONFIRMED, "decided_at": _utcnow()})

    def reject(self) -> ResumeFact:
        """User rejects this inferred fact (returns a new immutable instance)."""
        self._ensure_transition_allowed(FactState.REJECTED)
        return self.model_copy(update={"state": FactState.REJECTED, "decided_at": _utcnow()})

    def _ensure_transition_allowed(self, target: FactState) -> None:
        if self.state == FactState.REJECTED:
            raise ValueError(
                "a rejected fact cannot change state; create a new fact with fresh provenance"
            )
        if self.state == target:
            raise ValueError(f"fact is already {target.value}")
        if self.state == FactState.CONFIRMED and target == FactState.INFERRED:
            raise ValueError("a confirmed fact cannot be demoted; edit creates a new fact")

    @property
    def is_confirmed(self) -> bool:
        return self.state == FactState.CONFIRMED
