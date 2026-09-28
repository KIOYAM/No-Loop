"""Unit tests: domain error taxonomy (LOOP-2; MASTER_SPEC §17)."""

from __future__ import annotations

import uuid

import pytest
from app.domain.errors import (
    AutomationBlockedError,
    ConsentRequiredError,
    DomainError,
    SourcePolicyError,
)


class TestDomainError:
    def test_carries_full_taxonomy(self) -> None:
        err = DomainError(
            stage="discovery.fetch",
            reason="source returned HTTP 503",
            retryable=True,
            user_action="Try again later.",
        )
        record = err.to_dict()
        assert record["stage"] == "discovery.fetch"
        assert record["reason"] == "source returned HTTP 503"
        assert record["retryable"] is True
        assert record["user_action"] == "Try again later."
        assert record["diagnostic_id"]

    def test_diagnostic_id_auto_generated_and_valid_uuid(self) -> None:
        err = DomainError(stage="parse.pdf", reason="no text")
        uuid.UUID(err.diagnostic_id)  # must not raise

    def test_explicit_diagnostic_id_preserved(self) -> None:
        err = DomainError(stage="x", reason="y", diagnostic_id="fixed-id")
        assert err.diagnostic_id == "fixed-id"


class TestDesignedStops:
    def test_policy_error_is_never_retryable(self) -> None:
        # R-POLICY: policy stops are designed, not transient.
        err = SourcePolicyError(
            stage="automation.fill", reason="automation prohibited for this source"
        )
        assert err.retryable is False
        assert err.user_action is not None

    def test_consent_error_directs_to_consent(self) -> None:
        err = ConsentRequiredError(stage="email.send", reason="no consent envelope on file")
        assert "consent" in (err.user_action or "").lower()

    def test_automation_blocked_directs_to_manual(self) -> None:
        err = AutomationBlockedError(stage="automation.fill", reason="CAPTCHA detected")
        assert err.retryable is False
        assert "manual" in (err.user_action or "").lower()


class TestNoSilentFailure:
    @pytest.mark.parametrize(
        ("exc", "stage"),
        [
            (SourcePolicyError(stage="s", reason="r"), "s"),
            (ConsentRequiredError(stage="s", reason="r"), "s"),
            (AutomationBlockedError(stage="s", reason="r"), "s"),
        ],
    )
    def test_every_error_renders_message(self, exc: DomainError, stage: str) -> None:
        # Never silent: str() always carries stage + reason + diagnostic id.
        assert stage in str(exc)
        assert "r" in str(exc)
