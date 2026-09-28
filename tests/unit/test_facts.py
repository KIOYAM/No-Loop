"""Unit tests: fact ledger invariants (LOOP-2; skill 03)."""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.facts import FactProvenance, FactState, ResumeFact, SkillClaim
from pydantic import ValidationError

PROFILE_ID = "profile-1"


def make_fact(**overrides: Any) -> ResumeFact:
    defaults: dict[str, Any] = {
        "profile_id": PROFILE_ID,
        "field_class": "skill",
        "skill": SkillClaim(name="Python", claimed_level="2 years"),
        "confidence": 0.9,
        "provenance": FactProvenance(document_id="doc-1", page=1),
    }
    defaults.update(overrides)
    return ResumeFact(**defaults)


class TestProvenance:
    def test_fact_without_provenance_origin_is_rejected(self) -> None:
        # Invariant: no orphan facts — must have document_id or user_entry.
        with pytest.raises(ValidationError, match="provenance"):
            FactProvenance(document_id=None, user_entry=False)

    def test_document_provenance_is_valid(self) -> None:
        p = FactProvenance(document_id="doc-9", page=2, extraction_rule="pdf.heading")
        assert p.document_id == "doc-9"


class TestInitialStates:
    def test_extracted_fact_starts_inferred(self) -> None:
        fact = make_fact()
        assert fact.state is FactState.INFERRED
        assert fact.decided_at is None

    def test_user_entered_fact_is_confirmed_immediately(self) -> None:
        fact = make_fact(
            provenance=FactProvenance(user_entry=True),
            confidence=1.0,
            skill=None,
            value="Bengaluru",
            field_class="location",
        )
        assert fact.state is FactState.CONFIRMED
        assert fact.decided_at is not None

    def test_confidence_one_reserved_for_user_entry(self) -> None:
        # Invariant: extractor can never claim certainty — that is the user's role.
        with pytest.raises(ValidationError, match="1.0 is reserved"):
            make_fact(confidence=1.0)

    def test_confidence_bounds_enforced(self) -> None:
        with pytest.raises(ValidationError):
            make_fact(confidence=1.5)


class TestTransitions:
    def test_confirm_inferred_fact(self) -> None:
        fact = make_fact().confirm()
        assert fact.state is FactState.CONFIRMED
        assert fact.decided_at is not None

    def test_reject_inferred_fact(self) -> None:
        fact = make_fact().reject()
        assert fact.state is FactState.REJECTED

    def test_rejected_fact_is_terminal(self) -> None:
        # Invariant: a rejected fact cannot be resurrected; new provenance required.
        rejected = make_fact().reject()
        with pytest.raises(ValueError, match="rejected fact cannot change state"):
            rejected.confirm()

    def test_confirmed_cannot_demote_to_inferred(self) -> None:
        confirmed = make_fact().confirm()
        with pytest.raises(ValueError, match="cannot be demoted"):
            confirmed._ensure_transition_allowed(FactState.INFERRED)

    def test_double_confirm_is_rejected(self) -> None:
        confirmed = make_fact().confirm()
        with pytest.raises(ValueError, match="already confirmed"):
            confirmed.confirm()

    def test_confirm_returns_new_instance(self) -> None:
        original = make_fact()
        confirmed = original.confirm()
        assert original.state is FactState.INFERRED  # original untouched (immutability)
        assert confirmed.id == original.id
        assert confirmed is not original


class TestSkillClaims:
    def test_blank_skill_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SkillClaim(name="   ")

    def test_claimed_level_is_never_invented_by_model(self) -> None:
        # The model stores what the source claimed; it has no default level.
        claim = SkillClaim(name="FastAPI")
        assert claim.claimed_level is None
        assert claim.normalized_name is None  # set later by taxonomy normalizer
