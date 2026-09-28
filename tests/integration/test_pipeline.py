"""Integration tests: the core value pipeline, end-to-end, no network (W6).

Covers: dedup clustering (S8) -> MatchEngine (hard gate + score + explanation)
-> email drafter guards (G1/G2/G3) -> queue caps -> ledger -> export.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.adapters.ai_providers import RuleBasedProvider
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.domain.errors import ProviderUnavailableError, ValidationError
from app.domain.facts import FactProvenance, ResumeFact, SkillClaim
from app.domain.jobs import Job, SourceRef
from app.domain.matching import GateVerdict
from app.domain.profile import ApplicationLimits, CandidateProfile, TargetPreference, WorkMode
from app.ports import GenerationResult
from app.services.dedup import JobIdentityResolver
from app.services.email_drafter import EmailDrafter
from app.services.match_engine import MatchEngine
from app.services.queue import ApplicationQueue, ExportService, LedgerService


def make_job(
    title: str = "Python Developer",
    company: str = "Acme",
    location: str = "Chennai",
    mode: str = "hybrid",
    jd: str = "Required: strong Python and FastAPI. Must have REST API experience. Docker a plus.",
    smin: int | None = None,
    smax: int | None = None,
    cur: str | None = None,
    url: str = "https://jobs.example.com/1",
    adapter: str = "adapter_a",
) -> Job:
    return Job(
        title=title,
        company=company,
        location=location,
        work_mode=mode,
        description_text=jd,
        salary_min=smin,
        salary_max=smax,
        salary_currency=cur,
        posted_at=datetime.now(UTC) - timedelta(days=2),
        source=SourceRef(
            kind="public_api",
            adapter_id=adapter,
            native_id=f"{company}-{title}".replace(" ", "-"),
            url=url,
        ),
    )


def make_targeting(**overrides: Any) -> TargetPreference:
    defaults: dict[str, Any] = {
        "role_titles": ("Python Developer", "Backend Developer"),
        "locations": ("Chennai", "Bengaluru", "Remote"),
        "work_modes": frozenset({WorkMode.HYBRID, WorkMode.REMOTE}),
        "excluded_companies": frozenset({"BlackListed Corp"}),
    }
    defaults.update(overrides)
    return TargetPreference(**defaults)


def make_profile_limits(threshold: float = 0.3) -> ApplicationLimits:
    return ApplicationLimits(
        per_day=3,
        per_week=15,
        match_threshold=threshold,
        company_cooldown_days=7,
        active_hours=(0, 24),
    )


# ---------------------------------------------------------------------------
# Dedup (S8)
# ---------------------------------------------------------------------------


class TestDedup:
    def test_same_url_from_two_adapters_merges(self) -> None:
        resolver = JobIdentityResolver()
        a = make_job(adapter="adapter_a", url="https://x.io/j/1?utm_source=mail")
        b = make_job(adapter="adapter_b", url="https://x.io/j/1")
        resolver.add(a)
        cluster = resolver.add(b)
        assert len(resolver.clusters()) == 1
        assert sorted(cluster.provenance) == ["adapter_a", "adapter_b"]

    def test_same_native_id_same_adapter_merges(self) -> None:
        resolver = JobIdentityResolver()
        j1 = make_job()
        j2 = make_job(url="https://other.io/x")
        resolver.add(j1)
        resolver.add(j2)
        # different urls, same fingerprint content => fingerprint key merges
        assert len(resolver.clusters()) == 1

    def test_distinct_jobs_stay_separate(self) -> None:
        resolver = JobIdentityResolver()
        resolver.add(
            make_job(
                title="Java Dev",
                company="OtherCo",
                url="https://x.io/j/9",
                jd="Java, Spring, SQL. 5 years required.",
            )
        )
        resolver.add(make_job())
        assert len(resolver.clusters()) == 2

    def test_provenance_preserved_on_merge(self) -> None:
        resolver = JobIdentityResolver()
        resolver.add(make_job(adapter="adapter_a"))
        cluster = resolver.add(make_job(adapter="adapter_b", url="https://x.io/j/1?ref=nl"))
        assert "adapter_a" in cluster.provenance and "adapter_b" in cluster.provenance


# ---------------------------------------------------------------------------
# Matching (Match Triangle)
# ---------------------------------------------------------------------------


class TestMatchEngine:
    def test_good_job_passes_with_factors_and_explanation(self) -> None:
        engine = MatchEngine(
            profile_id="p1",
            profile_skills=["Python", "FastAPI", "Docker"],
            targeting=make_targeting(),
        )
        result = engine.score(make_job())
        assert result.hard_gate is GateVerdict.PASS
        assert result.score > 0.3
        names = [f.name for f in result.factors]
        assert "skills_overlap" in names and "title_similarity" in names
        assert "Excluded" not in result.explain()
        assert "skills_overlap" in result.explain()

    def test_work_mode_mismatch_hard_fails_with_reason(self) -> None:
        engine = MatchEngine(
            profile_id="p1",
            profile_skills=["Python"],
            targeting=make_targeting(work_modes=frozenset({WorkMode.REMOTE})),
        )
        result = engine.score(make_job(mode="onsite"))
        assert result.hard_gate is GateVerdict.FAIL
        assert "work mode mismatch" in result.gate_reasons[0]

    def test_location_mismatch_for_onsite_jobs(self) -> None:
        engine = MatchEngine(profile_id="p1", profile_skills=["Python"], targeting=make_targeting())
        result = engine.score(make_job(location="Berlin", mode="onsite"))
        assert result.hard_gate is GateVerdict.FAIL
        assert "location mismatch" in result.explain()

    def test_remote_job_bypasses_location_gate(self) -> None:
        engine = MatchEngine(profile_id="p1", profile_skills=["Python"], targeting=make_targeting())
        result = engine.score(make_job(mode="remote", location="Anywhere"))
        assert result.hard_gate is GateVerdict.PASS

    def test_excluded_company_hard_fails(self) -> None:
        engine = MatchEngine(profile_id="p1", profile_skills=["Python"], targeting=make_targeting())
        result = engine.score(make_job(company="BlackListed Corp"))
        assert result.hard_gate is GateVerdict.FAIL

    def test_recency_gate(self) -> None:
        old = make_job()
        old = old.model_copy(update={"posted_at": datetime.now(UTC) - timedelta(days=90)})
        engine = MatchEngine(profile_id="p1", profile_skills=["Python"], targeting=make_targeting())
        result = engine.score(old)
        assert result.hard_gate is GateVerdict.FAIL

    def test_salary_alignment_factor_when_present(self) -> None:
        engine = MatchEngine(
            profile_id="p1",
            profile_skills=["Python"],
            targeting=make_targeting(min_salary=900000, currency="INR"),
        )
        result = engine.score(make_job(smin=800000, smax=1000000, cur="INR"))
        salary = next(f for f in result.factors if f.name == "salary_alignment")
        assert 0.0 < salary.score <= 1.0

    def test_missing_salary_is_noted_not_zeroed(self) -> None:
        engine = MatchEngine(
            profile_id="p1",
            profile_skills=["Python"],
            targeting=make_targeting(min_salary=900000, currency="INR"),
        )
        result = engine.score(make_job())  # no salary fields
        assert any("salary_alignment undetermined" in n for n in result.notes)

    def test_gated_out_job_scores_zero_with_explanation(self) -> None:
        engine = MatchEngine(profile_id="p1", profile_skills=["Python"], targeting=make_targeting())
        result = engine.score(make_job(mode="onsite", location="Berlin"))
        assert result.score == 0.0
        assert result.explain().startswith("Excluded:")


# ---------------------------------------------------------------------------
# Email drafter guards
# ---------------------------------------------------------------------------


def confirmed_facts() -> list[ResumeFact]:
    return [
        ResumeFact(
            profile_id="p1",
            field_class="skill",
            skill=SkillClaim(name="Python", claimed_level="2 years"),
            confidence=1.0,
            provenance=FactProvenance(user_entry=True),
        ),
        ResumeFact(
            profile_id="p1",
            field_class="skill",
            skill=SkillClaim(name="FastAPI"),
            confidence=1.0,
            provenance=FactProvenance(user_entry=True),
        ),
        ResumeFact(
            profile_id="p1",
            field_class="experience_years",
            value=2,
            confidence=1.0,
            provenance=FactProvenance(user_entry=True),
        ),
        # an inferred fact that MUST NOT be consumed:
        ResumeFact(
            profile_id="p1",
            field_class="skill",
            skill=SkillClaim(name="Kubernetes"),
            confidence=0.5,
            provenance=FactProvenance(document_id="d1"),
        ),
    ]


class TestEmailDrafter:
    def test_draft_is_job_specific_and_evidence_mapped(self) -> None:
        drafter = EmailDrafter(RuleBasedProvider())
        draft = drafter.draft(profile_name="Kannan", facts=confirmed_facts(), job=make_job())
        assert "Python Developer" in draft.body
        assert "Acme" in draft.body
        assert "Python" in draft.body and "FastAPI" in draft.body
        assert draft.evidence["fact_ids"], "evidence map must reference confirmed facts"
        assert draft.job_specificity["references_role"] is True

    def test_inferred_facts_never_used(self) -> None:
        # Kubernetes is inferred (unconfirmed) — must not appear as claimed skill.
        drafter = EmailDrafter(RuleBasedProvider())
        draft = drafter.draft(profile_name="K", facts=confirmed_facts(), job=make_job())
        assert "Kubernetes" not in draft.body

    def test_empty_jd_refuses_generation(self) -> None:
        drafter = EmailDrafter(RuleBasedProvider())
        with pytest.raises(ValidationError, match="generic filler"):
            drafter.draft(profile_name="K", facts=confirmed_facts(), job=make_job(jd="   "))

    def test_banned_certainty_phrases_rejected(self) -> None:
        class EvilProvider(RuleBasedProvider):
            def generate(self, request: object) -> GenerationResult:
                return GenerationResult(
                    text="Dear team, I am a guaranteed 100% match. Best, K", provider="evil"
                )

        drafter = EmailDrafter(EvilProvider())
        with pytest.raises(ValidationError, match="banned certainty"):
            drafter.draft(profile_name="K", facts=confirmed_facts(), job=make_job())

    def test_noprovider_refuses_generation_visibly(self) -> None:
        from app.adapters.ai_providers import NoAIProvider

        provider = NoAIProvider()
        with pytest.raises(ProviderUnavailableError):
            provider.generate(None)


# ---------------------------------------------------------------------------
# Queue caps + ledger
# ---------------------------------------------------------------------------


class TestQueue:
    def test_queue_disabled_without_limits(self) -> None:
        profile = CandidateProfile(name="Dev")  # no limits set
        engine = MatchEngine(
            profile_id=profile.id, profile_skills=["Python"], targeting=make_targeting()
        )
        match = engine.score(make_job())
        decision = ApplicationQueue().admit(
            profile=profile, job=make_job(), match=match, submitted_today=0, submitted_this_week=0
        )
        assert decision.admitted is False
        assert "limits are not fully configured" in decision.reason

    def test_threshold_blocks_low_scores(self) -> None:
        profile = CandidateProfile(name="Dev", limits=make_profile_limits(threshold=0.99))
        engine = MatchEngine(
            profile_id=profile.id, profile_skills=["COBOL"], targeting=make_targeting()
        )
        match = engine.score(make_job())
        decision = ApplicationQueue().admit(
            profile=profile, job=make_job(), match=match, submitted_today=0, submitted_this_week=0
        )
        assert decision.admitted is False
        assert "below threshold" in decision.reason

    def test_daily_cap_enforced(self) -> None:
        profile = CandidateProfile(name="Dev", limits=make_profile_limits())
        engine = MatchEngine(
            profile_id=profile.id,
            profile_skills=["Python", "FastAPI", "Docker", "REST API"],
            targeting=make_targeting(),
        )
        match = engine.score(make_job())
        decision = ApplicationQueue(clock=lambda: datetime(2026, 9, 28, 10)).admit(
            profile=profile, job=make_job(), match=match, submitted_today=3, submitted_this_week=3
        )
        assert decision.admitted is False
        assert "daily cap" in decision.reason

    def test_company_cooldown_enforced(self) -> None:
        profile = CandidateProfile(name="Dev", limits=make_profile_limits())
        engine = MatchEngine(
            profile_id=profile.id, profile_skills=["Python"], targeting=make_targeting()
        )
        match = engine.score(make_job())
        decision = ApplicationQueue(clock=lambda: datetime(2026, 9, 28, 10)).admit(
            profile=profile,
            job=make_job(),
            match=match,
            submitted_today=0,
            submitted_this_week=0,
            company_last_applied=datetime(2026, 9, 25, 10),
        )
        assert decision.admitted is False
        assert "cooldown" in decision.reason

    def test_happy_admission(self) -> None:
        profile = CandidateProfile(name="Dev", limits=make_profile_limits())
        engine = MatchEngine(
            profile_id=profile.id,
            profile_skills=["Python", "FastAPI", "Docker"],
            targeting=make_targeting(),
        )
        match = engine.score(make_job())
        decision = ApplicationQueue(clock=lambda: datetime(2026, 9, 28, 10)).admit(
            profile=profile, job=make_job(), match=match, submitted_today=0, submitted_this_week=0
        )
        assert decision.admitted is True


class TestLedger:
    def test_transition_audit_trail_append_only(self) -> None:
        ledger = LedgerService()
        app = Application(
            profile_id="p1", entry_method=EntryMethod.ASSISTED, company="A", title="T"
        )
        ledger.create(app)
        ledger.transition(app.id, ApplicationStatus.SHORTLISTED)
        ledger.transition(app.id, ApplicationStatus.READY)
        events = ledger.audit_trail
        assert [e["event"] for e in events] == ["created", "transition", "transition"]
        assert events[-1]["to"] == "ready"

    def test_export_excludes_consent_references(self) -> None:
        ledger = LedgerService()
        app = Application(
            profile_id="p1",
            entry_method=EntryMethod.AUTOMATED,
            consent_envelope_id="secret-consent-ref",
            company="A",
            title="T",
        )
        ledger.create(app)
        exported = ExportService(ledger).to_json()
        assert "secret-consent-ref" not in exported
