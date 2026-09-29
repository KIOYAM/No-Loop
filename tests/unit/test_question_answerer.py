"""Unit tests: dynamic question answerer (no fabrication; needs_user flags)."""

from __future__ import annotations

from app.domain.facts import FactProvenance, ResumeFact, SkillClaim
from app.domain.profile import ApplicationLimits, CandidateProfile, TargetPreference
from app.services.question_answerer import QuestionAnswerer, build_fact_sheet


def profile() -> CandidateProfile:
    base = CandidateProfile(
        name="Python Dev",
        contact_name="Kannan R",
        contact_email="k@example.com",
        contact_phone="+91 90000 00000",
        location="Chennai",
    )
    targeting = TargetPreference(
        role_titles=("Python Developer",),
        locations=("Chennai", "Remote"),
        min_salary=1_200_000,
        currency="INR",
        notice_period_days=30,
    )
    limits = ApplicationLimits(
        per_day=3, per_week=15, match_threshold=0.6, company_cooldown_days=7, active_hours=(9, 20)
    )
    return base.with_targeting(targeting).with_limits(limits)


def facts() -> list[ResumeFact]:
    prov = FactProvenance(user_entry=True)
    return [
        ResumeFact(
            profile_id="p",
            field_class="skill",
            skill=SkillClaim(name="Python"),
            confidence=1.0,
            provenance=prov,
        ),
        ResumeFact(
            profile_id="p", field_class="experience_years", value=2, confidence=1.0, provenance=prov
        ),
    ]


def answerer() -> QuestionAnswerer:
    return QuestionAnswerer(build_fact_sheet(facts(), profile()))


class TestAnswerable:
    def test_years_answered_from_facts(self) -> None:
        result = answerer().answer("How many years of experience do you have?")
        assert result.answer == "2+ years"
        assert result.source == "facts"
        assert not result.needs_user

    def test_salary_answered_from_targeting(self) -> None:
        result = answerer().answer("What are your salary expectations?")
        assert result.answer is not None and "INR" in result.answer

    def test_notice_period(self) -> None:
        result = answerer().answer("What is your notice period?")
        assert result.answer is not None and "30 days" in result.answer

    def test_skills_listing(self) -> None:
        result = answerer().answer("Which technologies do you work with?")
        assert result.answer is not None and "Python" in result.answer

    def test_relocation_uses_targeting_locations(self) -> None:
        result = answerer().answer("Are you willing to relocate?")
        assert result.answer is not None and "Chennai" in result.answer


class TestNeedsUser:
    def test_work_authorization_never_guessed(self) -> None:
        # Legal status: the system must not fabricate — flagged for the user.
        result = answerer().answer("Are you legally authorized to work in this country?")
        assert result.needs_user
        assert "legal" in (result.reason or "").lower() or "user" in (result.source or "")

    def test_sponsorship_never_guessed(self) -> None:
        result = answerer().answer("Do you need visa sponsorship?")
        assert result.needs_user

    def test_unknown_question_flagged_not_guessed(self) -> None:
        result = answerer().answer("What is your favorite programming paradigm and why?")
        assert result.needs_user
        assert result.reason  # honest explanation present

    def test_missing_salary_flagged_when_unset(self) -> None:
        sheet = build_fact_sheet(facts(), CandidateProfile(name="bare"))
        result = QuestionAnswerer(sheet).answer("Expected CTC?")
        assert result.needs_user


class TestFactSheet:
    def test_sheet_shape(self) -> None:
        sheet = build_fact_sheet(facts(), profile())
        assert sheet["experience_years"] == 2
        assert "Python" in sheet["skills"]
        assert sheet["currency"] == "INR"
        assert sheet["email"] == "k@example.com"
