"""Unit tests: application ledger state machine (LOOP-2; APPLICATION_LEDGER.md)."""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.applications import (
    APPLICATION_TRANSITIONS,
    Application,
    ApplicationStatus,
    EntryMethod,
)


def make_app(**overrides: Any) -> Application:
    defaults: dict[str, Any] = {
        "profile_id": "profile-1",
        "entry_method": EntryMethod.ASSISTED,
        "job_id": "job-1",
        "company": "Acme Corp",
        "title": "Python Developer",
    }
    defaults.update(overrides)
    return Application(**defaults)


def walk_to_review(app: Application) -> Application:
    return (
        app.transition(ApplicationStatus.SHORTLISTED)
        .transition(ApplicationStatus.READY)
        .transition(ApplicationStatus.DRAFTED)
        .transition(ApplicationStatus.REVIEW_REQUIRED)
    )


class TestStateMachine:
    def test_legal_full_path_to_submitted(self) -> None:
        app = walk_to_review(make_app())
        submitted = app.transition(
            ApplicationStatus.SUBMITTED,
            submission_evidence={"method": "user_confirmation", "confirmed_by": "user"},
        )
        assert submitted.status is ApplicationStatus.SUBMITTED
        assert submitted.submission_evidence is not None

    def test_illegal_jump_rejected(self) -> None:
        app = make_app()
        with pytest.raises(ValueError, match="illegal transition"):
            app.transition(ApplicationStatus.SUBMITTED)

    def test_terminal_states_have_no_exits(self) -> None:
        assert APPLICATION_TRANSITIONS[ApplicationStatus.CLOSED] == frozenset()
        assert APPLICATION_TRANSITIONS[ApplicationStatus.SKIPPED] == frozenset()
        assert APPLICATION_TRANSITIONS[ApplicationStatus.REJECTED_BY_USER] == frozenset()

    def test_failed_requires_structured_failure_record(self) -> None:
        # MASTER_SPEC §17: FAILED without stage/reason record is forbidden.
        app = walk_to_review(make_app())
        with pytest.raises(ValueError, match="§17 failure record|failure record"):
            app.transition(ApplicationStatus.FAILED)

    def test_failed_with_record_then_retry_path(self) -> None:
        app = walk_to_review(make_app())
        failed = app.transition(
            ApplicationStatus.FAILED,
            failure={
                "stage": "assisted.handoff",
                "reason": "portal unreachable",
                "retryable": True,
            },
        )
        retried = failed.transition(ApplicationStatus.READY)
        assert retried.status is ApplicationStatus.READY

    def test_submitted_requires_evidence_r_truth_5(self) -> None:
        # Invariant 1: no SUBMITTED without evidence — "looks submitted" ≠ submitted.
        app = walk_to_review(make_app())
        with pytest.raises(ValueError, match="submission evidence"):
            app.transition(ApplicationStatus.SUBMITTED)

    def test_automated_requires_consent_envelope(self) -> None:
        # Invariant: automated submissions carry a recorded consent envelope (R-SEC-3).
        app = walk_to_review(make_app(entry_method=EntryMethod.AUTOMATED))
        evidence = {"method": "completion_signal", "marker": "application-received"}
        with pytest.raises(ValueError, match="consent envelope"):
            app.transition(ApplicationStatus.SUBMITTED, submission_evidence=evidence)

    def test_automated_with_consent_passes_gate(self) -> None:
        app = walk_to_review(
            make_app(entry_method=EntryMethod.AUTOMATED, consent_envelope_id="consent-1")
        )
        submitted = app.transition(
            ApplicationStatus.SUBMITTED,
            submission_evidence={"method": "completion_signal", "marker": "application-received"},
        )
        assert submitted.status is ApplicationStatus.SUBMITTED


class TestEntryMethods:
    def test_manual_quick_add_defaults_to_submitted_review(self) -> None:
        # Quick-Add: user asserts they already applied; evidence = user assertion.
        app = make_app(entry_method=EntryMethod.MANUAL, job_id=None)
        assert app.status is ApplicationStatus.REVIEW_REQUIRED

    def test_manual_record_starts_at_review_for_enrichment(self) -> None:
        app = make_app(entry_method=EntryMethod.MANUAL, job_id="job-9")
        assert app.status is ApplicationStatus.REVIEW_REQUIRED

    def test_profile_scoping_required(self) -> None:
        # pydantic raises ValidationError (min_length) for an empty profile id.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            make_app(profile_id="")


class TestUrlValidation:
    def test_source_url_must_be_http(self) -> None:
        with pytest.raises(ValueError, match="http"):
            make_app(source_url="javascript:alert(1)")

    def test_application_url_must_be_http(self) -> None:
        with pytest.raises(ValueError, match="http"):
            make_app(application_url="ftp://files.example.com/apply")
