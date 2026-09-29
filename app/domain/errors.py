"""No_Loop domain errors.

Every failure crossing a boundary is a domain error carrying the structured
taxonomy required by MASTER_SPEC §17:
    stage, reason, retryable, user_action, diagnostic_id.

Domain errors never wrap vendor exceptions and never leak vendor names
(R-ARCH-3). Adapters map external exceptions onto these types (skill 04).
"""

from __future__ import annotations

import uuid
from typing import Any

__all__ = [
    "DomainError",
    "ValidationError",
    "ParsingError",
    "SourceFetchError",
    "SourcePolicyError",
    "StorageError",
    "ConsentRequiredError",
    "AutomationBlockedError",
    "ProviderUnavailableError",
]


class DomainError(Exception):
    """Base class for all No_Loop domain errors (MASTER_SPEC §17 taxonomy)."""

    def __init__(
        self,
        *,
        stage: str,
        reason: str,
        retryable: bool = False,
        user_action: str | None = None,
        diagnostic_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create a structured domain error.

        Args:
            stage: Pipeline stage identifier, e.g. ``"discovery.fetch"``.
            reason: Human-readable explanation of what went wrong.
            retryable: Whether retrying the same operation may succeed.
            user_action: What the user can do about it, if anything.
            diagnostic_id: Correlation id for logs; generated when absent.
            details: Sanitized extra context (never secrets, never personal data).
        """
        self.stage = stage
        self.reason = reason
        self.retryable = retryable
        self.user_action = user_action
        self.diagnostic_id = diagnostic_id or str(uuid.uuid4())
        self.details: dict[str, Any] = details or {}
        super().__init__(f"[{self.stage}] {self.reason} (diagnostic_id={self.diagnostic_id})")

    def to_dict(self) -> dict[str, Any]:
        """Return the structured failure record for UI/ledger/log surfaces."""
        return {
            "stage": self.stage,
            "reason": self.reason,
            "retryable": self.retryable,
            "user_action": self.user_action,
            "diagnostic_id": self.diagnostic_id,
            "details": dict(self.details),
        }


class ValidationError(DomainError):
    """Input failed domain validation (types, sizes, invariants)."""

    def __init__(self, stage: str, reason: str, **kwargs: Any) -> None:
        super().__init__(stage=stage, reason=reason, retryable=False, **kwargs)


class ParsingError(DomainError):
    """A document could not be parsed (corrupt, unsupported, no text)."""

    def __init__(
        self, stage: str, reason: str, *, user_action: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            stage=stage, reason=reason, retryable=False, user_action=user_action, **kwargs
        )


class SourceFetchError(DomainError):
    """A job source could not be fetched (network, HTTP, malformed payload)."""

    def __init__(self, stage: str, reason: str, *, retryable: bool = True, **kwargs: Any) -> None:
        super().__init__(stage=stage, reason=reason, retryable=retryable, **kwargs)


class SourcePolicyError(DomainError):
    """An operation is forbidden by the source's policy status (R-POLICY-1..3).

    This error is a designed stop, not a bug: automation attempted on a
    PROHIBITED/ASSISTED_ONLY surface raises this immediately.
    """

    def __init__(self, stage: str, reason: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        kwargs.setdefault(
            "user_action",
            "Use the assisted flow for this source instead of automation.",
        )
        super().__init__(stage=stage, reason=reason, **kwargs)


class StorageError(DomainError):
    """Local persistence failed (DB unavailable, migration failure, disk)."""


class ConsentRequiredError(DomainError):
    """An action that sends data off-device was attempted without consent (R-SEC-3)."""

    def __init__(self, stage: str, reason: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        kwargs.setdefault("user_action", "Review and grant consent before retrying this action.")
        super().__init__(stage=stage, reason=reason, **kwargs)


class AutomationBlockedError(DomainError):
    """Automation hit a hard stop (CAPTCHA, MFA, anti-bot, unknown state) — R-POLICY-2."""

    def __init__(self, stage: str, reason: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        kwargs.setdefault(
            "user_action", "Complete this step manually; No_Loop has paused and recorded evidence."
        )
        super().__init__(stage=stage, reason=reason, **kwargs)


class ProviderUnavailableError(DomainError):
    """The requested AI provider tier is not available; caller must fall back (S7)."""

    def __init__(self, stage: str, reason: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        kwargs.setdefault(
            "user_action", "Continue with the next available provider tier (rule-based / no-AI)."
        )
        super().__init__(stage=stage, reason=reason, **kwargs)
