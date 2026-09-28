"""Unit tests: candidate profile + mandatory limits gate (LOOP-2; spec §3/§4)."""

from __future__ import annotations

import pytest
from app.domain.profile import ApplicationLimits, CandidateProfile, TargetPreference, WorkMode
from pydantic import ValidationError


class TestApplicationLimits:
    def test_fresh_limits_are_not_configured(self) -> None:
        # Decision: NO silent caps — everything starts unset.
        assert ApplicationLimits().is_configured is False

    def test_partially_set_limits_are_not_configured(self) -> None:
        limits = ApplicationLimits(per_day=3, per_week=15)
        assert limits.is_configured is False

    def test_fully_set_limits_are_configured(self) -> None:
        limits = ApplicationLimits(
            per_day=3,
            per_week=15,
            match_threshold=0.7,
            company_cooldown_days=7,
            active_hours=(9, 20),
        )
        assert limits.is_configured is True

    def test_week_must_not_be_below_day(self) -> None:
        with pytest.raises(ValidationError, match="per_week must be >="):
            ApplicationLimits(per_day=10, per_week=5)


class TestTargetPreference:
    def test_at_least_one_role_title_required(self) -> None:
        with pytest.raises(ValidationError, match="role title"):
            TargetPreference(role_titles=())

    def test_currency_normalized_upper(self) -> None:
        pref = TargetPreference(
            role_titles=("Python Developer",), currency="inr", min_salary=1_200_000
        )
        assert pref.currency == "INR"

    def test_blank_titles_stripped(self) -> None:
        pref = TargetPreference(role_titles=("  Python Developer  ", ""))
        assert pref.role_titles == ("Python Developer",)


class TestCandidateProfile:
    def test_profile_scopes_entities_by_id(self) -> None:
        # Multi-profile decision (spec Round 4): profile is the scoping root.
        p1 = CandidateProfile(name="Python Developer")
        p2 = CandidateProfile(name="ML Engineer")
        assert p1.id != p2.id

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            CandidateProfile(name="   ")

    def test_fresh_profile_limits_not_configured(self) -> None:
        assert CandidateProfile(name="Dev").limits_configured is False

    def test_with_limits_requires_full_configuration(self) -> None:
        profile = CandidateProfile(name="Dev")
        with pytest.raises(ValueError, match="fully configured"):
            profile.with_limits(ApplicationLimits(per_day=3))

    def test_with_limits_configures_gate(self) -> None:
        profile = CandidateProfile(name="Dev")
        limits = ApplicationLimits(
            per_day=3,
            per_week=15,
            match_threshold=0.7,
            company_cooldown_days=7,
            active_hours=(9, 20),
        )
        configured = profile.with_limits(limits)
        assert configured.limits_configured is True
        assert profile.limits_configured is False  # original untouched

    def test_email_basic_shape(self) -> None:
        with pytest.raises(ValidationError, match="email"):
            CandidateProfile(name="Dev", contact_email="not-an-email")

    def test_targeting_round_trip(self) -> None:
        profile = CandidateProfile(name="Dev")
        targeting = TargetPreference(
            role_titles=("AI Engineer", "Backend Developer"),
            locations=("Coimbatore", "Chennai", "Bengaluru", "Remote"),
            work_modes=frozenset({WorkMode.REMOTE, WorkMode.HYBRID}),
            currency="INR",
            notice_period_days=30,
        )
        updated = profile.with_targeting(targeting)
        assert updated.targeting is not None
        assert len(updated.targeting.role_titles) == 2
        assert profile.targeting is None
