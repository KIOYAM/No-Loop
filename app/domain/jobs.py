"""Job domain model (MASTER_SPEC §6; RESEARCH.md S8).

Jobs arrive from adapters as raw external shapes and are normalized into this
domain model. Vendor/portal names never appear here (R-ARCH-3) — the source is
identified by the opaque ``SourceRef`` the adapter supplies.
"""

from __future__ import annotations

import enum
import hashlib
import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["PolicyStatus", "SourceRef", "Job", "content_fingerprint"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class PolicyStatus(enum.StrEnum):
    """Policy classification per R-POLICY-1 / DATA_SOURCES.md §9."""

    ALLOWED_PUBLIC_API = "allowed_public_api"
    PERMITTED_WITH_LIMITS = "permitted_with_limits"
    USER_ACCOUNT_REQUIRED = "user_account_required"
    ASSISTED_ONLY = "assisted_only"
    PROHIBITED = "prohibited"


class SourceRef(BaseModel):
    """Opaque identity of the source a job came from.

    ``kind`` is a generic taxonomy word (e.g. ``"public_api"``, ``"ats_board"``,
    ``"url_import"``, ``"jd_import"``) — never a vendor name. The concrete
    adapter id (configured, e.g. ``"source_adapter_01"``) lives in
    ``adapter_id`` so the domain stays vendor-free (R-ARCH-3).
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1, max_length=40)
    adapter_id: str = Field(min_length=1, max_length=80)
    native_id: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2048)

    @field_validator("url")
    @classmethod
    def _url_scheme_allowlist(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("source url must be http(s)")
        return v


def content_fingerprint(title: str, company: str, description_text: str) -> str:
    """Stable content fingerprint for dedup (S8 key 4).

    Normalizes whitespace/case so cosmetic HTML differences do not create
    duplicate identities.
    """
    norm = re.sub(r"\s+", " ", f"{title}|{company}|{description_text}".strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class Job(BaseModel):
    """Normalized job posting.

    Dedup identity keys (S8): source native_id, canonical URL, content
    fingerprint. Cross-source company+title fuzzy matching happens in the
    JobIdentity resolver (LOOP-6), not here.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_id)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)

    @field_validator("title", "company")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    location: str | None = None
    work_mode: str | None = Field(
        default=None, description="remote|hybrid|onsite|unknown (normalized)"
    )
    description_text: str = Field(
        default="", max_length=100_000, description="Sanitized plain text"
    )
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    posted_at: datetime | None = None
    source: SourceRef
    fingerprint: str | None = Field(
        default=None, description="content_fingerprint(...), set on creation"
    )
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _finalize(self) -> Job:
        if self.fingerprint is None:
            object.__setattr__(
                self,
                "fingerprint",
                content_fingerprint(self.title, self.company, self.description_text),
            )
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must be <= salary_max")
        return self

    @property
    def url(self) -> str | None:
        return self.source.url

    @property
    def is_remote_friendly(self) -> bool:
        return (self.work_mode == "remote") or ("remote" in (self.location or "").lower())
