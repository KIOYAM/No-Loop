"""Ports (interfaces) — the domain-side contracts every adapter must honor.

R-ARCH-2: every external system is behind a port. Ports use domain language
and domain types only — never vendor names (R-ARCH-3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from app.domain.applications import Application
from app.domain.facts import ResumeFact
from app.domain.jobs import Job, PolicyStatus

__all__ = [
    "PolicyDeclaration",
    "SourceAdapter",
    "DocumentExtractor",
    "ExtractionResult",
    "AIProvider",
    "GenerationRequest",
    "GenerationResult",
]


class PolicyDeclaration:
    """Adapter metadata the UI/services query before any network action.

    Fields map to MASTER_SPEC §6: DISCOVERY / PARSING / APPLICATION / EMAIL /
    CAPABILITIES / POLICY_STATUS. Source URL + review date are mandatory
    (R-POLICY-1) so every classification stays evidence-backed.
    """

    def __init__(
        self,
        *,
        discovery: bool,
        parsing: bool,
        application: bool,
        email: bool,
        policy_status: PolicyStatus,
        policy_source_url: str,
        policy_reviewed_at: str,
    ) -> None:
        self.discovery = discovery
        self.parsing = parsing
        self.application = application
        self.email = email
        self.policy_status = policy_status
        self.policy_source_url = policy_source_url
        self.policy_reviewed_at = policy_reviewed_at


@runtime_checkable
class SourceAdapter(Protocol):
    """A pluggable job source (LOOP-3). One adapter per external system."""

    adapter_id: str
    policy: PolicyDeclaration

    def discover(self, *, query: str | None = None, limit: int = 50) -> AsyncIterator[Job]:
        """Yield normalized Jobs. Must be incremental + rate-limited."""
        ...


@runtime_checkable
class DocumentExtractor(Protocol):
    """Extracts text from one document format (LOOP-5; skill 03)."""

    formats: tuple[str, ...]

    def extract(self, data: bytes) -> ExtractionResult: ...


class ExtractionResult:
    """Outcome of extraction: text or an honest, actionable failure.

    ``page_offsets`` (optional) records the character offset where each page
    begins so facts can carry ``provenance.page`` — extraction ≠ inference, so
    this is layout metadata, never interpretation.
    """

    __slots__ = ("text", "ok", "error_reason", "user_action", "page_offsets")

    def __init__(
        self,
        ok: bool,
        text: str = "",
        *,
        error_reason: str | None = None,
        user_action: str | None = None,
        page_offsets: list[int] | None = None,
    ) -> None:
        self.ok = ok
        self.text = text
        self.error_reason = error_reason
        self.user_action = user_action
        self.page_offsets = page_offsets


@runtime_checkable
class AIProvider(Protocol):
    """AI provider contract (MASTER_SPEC §12; CURSOR_MASTER_PROMPT)."""

    name: str

    def available(self) -> bool: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def privacy_info(self) -> dict[str, Any]: ...

    def estimate_cost(self, request: GenerationRequest) -> dict[str, Any]: ...


class GenerationRequest:
    """Minimal provider-agnostic generation request (fact slices, never full resume)."""

    __slots__ = ("task", "instructions", "facts_payload", "job_payload", "max_chars")

    def __init__(
        self,
        task: str,
        instructions: str,
        facts_payload: str,
        job_payload: str,
        max_chars: int = 4000,
    ) -> None:
        self.task = task
        self.instructions = instructions
        self.facts_payload = facts_payload
        self.job_payload = job_payload
        self.max_chars = max_chars


class GenerationResult:
    __slots__ = ("text", "provider")

    def __init__(self, text: str, provider: str) -> None:
        self.text = text
        self.provider = provider


_ = (Application, ResumeFact)  # referenced for type documentation; keeps import surface explicit
