"""Candidate profile aggregate (MASTER_SPEC §1.3, §15; NOLOOP_DEV_KICKOFF-spec §3).

No_Loop supports MULTIPLE named candidate profiles (e.g. "Python Developer" and
"ML Engineer"). The profile is the scoping root: every profile-scoped entity
carries ``profile_id``. The profile also owns the mandatory application limits
(decision: no silent caps — the queue stays disabled until the user sets them).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["WorkMode", "ApplicationLimits", "TargetPreference", "CandidateProfile"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class WorkMode(enum.StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    ANY = "any"


class ApplicationLimits(BaseModel):
    """User-set application caps. NO defaults by design (spec §3 Round 4, §8.7).

    ``is_configured`` is the gate: discovery/queue features remain disabled
    until the user has explicitly set every limit (MASTER_SPEC §4).
    """

    model_config = ConfigDict(frozen=True)

    per_day: int | None = Field(default=None, ge=1, le=200)
    per_week: int | None = Field(default=None, ge=1, le=1000)
    match_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    company_cooldown_days: int | None = Field(default=None, ge=0, le=365)
    active_hours: tuple[int, int] | None = Field(
        default=None, description="(start_hour, end_hour) in user local time, 0-23."
    )

    @property
    def is_configured(self) -> bool:
        return (
            self.per_day is not None
            and self.per_week is not None
            and self.match_threshold is not None
            and self.company_cooldown_days is not None
            and self.active_hours is not None
        )

    @model_validator(mode="after")
    def _weekly_not_below_daily_times_seven(self) -> ApplicationLimits:
        if self.per_day is not None and self.per_week is not None and self.per_week < self.per_day:
            raise ValueError("per_week must be >= per_day")
        return self


class TargetPreference(BaseModel):
    """What the active profile is targeting (MASTER_SPEC §5)."""

    model_config = ConfigDict(frozen=True)

    role_titles: tuple[str, ...] = Field(min_length=0)
    locations: tuple[str, ...] = Field(default=())
    work_modes: frozenset[WorkMode] = Field(default=frozenset({WorkMode.ANY}))
    min_salary: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    excluded_companies: frozenset[str] = Field(default=frozenset())
    excluded_keywords: frozenset[str] = Field(default=frozenset())
    recency_days: int = Field(default=30, ge=1, le=365)

    @field_validator("role_titles")
    @classmethod
    def _titles_not_blank(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(t.strip() for t in v if t.strip())
        if not cleaned:
            raise ValueError("at least one target role title is required")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class CandidateProfile(BaseModel):
    """Aggregate root for one named candidate profile."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_id)
    name: str = Field(min_length=1, max_length=80)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    location: str | None = None
    links: dict[str, str] = Field(default_factory=dict, description="e.g. github, portfolio site")
    targeting: TargetPreference | None = None
    limits: ApplicationLimits | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("profile name must not be blank")
        return v

    @field_validator("contact_email")
    @classmethod
    def _email_basic_shape(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("contact_email must contain a valid-looking email")
        return v

    @property
    def limits_configured(self) -> bool:
        """Gate used by discovery/queue features (MASTER_SPEC §4 mandatory limits)."""
        return self.limits is not None and self.limits.is_configured

    def with_limits(self, limits: ApplicationLimits) -> CandidateProfile:
        """Return a copy with limits set (immutability-preserving update)."""
        if not limits.is_configured:
            raise ValueError("limits must be fully configured before attaching to a profile")
        return self.model_copy(update={"limits": limits, "updated_at": _utcnow()})

    def with_targeting(self, targeting: TargetPreference) -> CandidateProfile:
        return self.model_copy(update={"targeting": targeting, "updated_at": _utcnow()})
