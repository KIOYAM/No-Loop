"""Tests for the six reference-gap features (P1-P6)."""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.facts import FactProvenance, FactState, ResumeFact, SkillClaim
from app.domain.knowledge import KBEntry, cosine_similarity, tfidf_rank, tokenize
from app.domain.profile import CandidateProfile
from app.services.apply_sheets import ATSFillPlanner, build_answer_sheet
from app.services.employer_intel import EmployerIntel
from app.services.resume_builder import ResumeAssembler, ats_score
from app.services.scheduler import Scheduler


def _fact(field_class: str, value: Any = None, skill: str | None = None) -> ResumeFact:
    return ResumeFact(
        profile_id="p1",
        field_class=field_class,
        value=value,
        skill=SkillClaim(name=skill) if skill else None,
        confidence=1.0,
        state=FactState.CONFIRMED,
        provenance=FactProvenance(user_entry=True, source="test"),
    )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Kannan",
        contact_name="Kannan",
        contact_email="k@example.com",
        contact_phone="+91 90000 00000",
        location="Chennai",
    )


def _kb() -> list[KBEntry]:
    return [
        KBEntry(
            profile_id="p1",
            kind="project",
            title="HRMS platform",
            body="Built an HRMS with FastAPI and PostgreSQL serving 10k employees",
            tags=("hrms", "fastapi", "postgresql"),
        ),
        KBEntry(
            profile_id="p1",
            kind="achievement",
            title="ML pipeline migration",
            body="Migrated ML pipelines to Docker, processing 2M records daily",
            tags=("ml", "docker"),
        ),
    ]


# ------------------------------------------------------------------ P2: KB --
class TestKnowledge:
    def test_tfidf_ranks_relevant_entry_first(self) -> None:
        ranked = tfidf_rank(_kb(), "Need a FastAPI developer with PostgreSQL for HR systems")
        assert ranked, "expected at least one match"
        assert ranked[0][0].title == "HRMS platform"
        assert 0 < ranked[0][1] <= 1.0

    def test_tfidf_empty_inputs(self) -> None:
        assert tfidf_rank([], "anything") == []
        assert tfidf_rank(_kb(), "") == []

    def test_cosine_and_tokenize(self) -> None:
        assert cosine_similarity([], ["x"]) == 0.0
        toks = tokenize("C++ and CI/CD experience with .NET")
        assert "c++" in toks and "ci/cd" in toks and "net" in toks
        assert "and" not in toks  # stopword

    def test_kb_entry_user_asserted_and_reuse_counter(self) -> None:
        e = _kb()[0]
        e2 = e.touch_used()
        assert e2.times_used == e.times_used + 1
        from pydantic import ValidationError

        with pytest.raises(ValidationError):  # blank body rejected
            KBEntry(profile_id="p1", kind="blurb", title="t", body="   ")


# ------------------------------------------------------- P1/P2: resume docs --
class TestResumeBuilderAndRender:
    def _facts(self) -> list[ResumeFact]:
        return [
            _fact("skill", skill="Python"),
            _fact("skill", skill="FastAPI"),
            _fact("experience_years", 3),
            _fact("employer", "Acme"),
            _fact("title", "Python Developer"),
        ]

    def test_build_and_ats_score(self) -> None:
        asm = ResumeAssembler(self._facts(), _profile())
        jd = "We need a Python developer with FastAPI experience."
        doc = asm.build(jd_text=jd, kb_entries=_kb())
        assert doc["contact"]["name"] == "Kannan"
        assert "Python" in doc["skills"]
        text = asm.resume_text(doc)
        score = ats_score(text, jd)
        assert 0.0 <= score <= 1.0 and score > 0.05

    def test_tailoring_suggestions_never_fabricate(self) -> None:
        asm = ResumeAssembler(self._facts(), _profile())
        out = asm.tailoring_suggestions(
            "Looking for Kubernetes and FastAPI experience", kb_entries=_kb()
        )
        assert any("kubernetes" in m for m in out["missing_terms"])
        assert any("NOT claim" in s for s in out["suggestions"])

    def test_render_resume_pdf_and_docx(self) -> None:
        from app.services.renderer import render_resume_docx, render_resume_pdf

        asm = ResumeAssembler(self._facts(), _profile())
        doc = asm.build(jd_text="Python FastAPI role", kb_entries=_kb())
        pdf = render_resume_pdf(doc)
        assert pdf.startswith(b"%PDF") and len(pdf) > 1000
        docx_bytes = render_resume_docx(doc)
        assert docx_bytes[:2] == b"PK"  # zip container
        from app.services.renderer import RenderError

        with pytest.raises(RenderError):
            render_resume_pdf({"contact": {}})

    def test_render_prep_pack(self) -> None:
        from app.services.renderer import render_prep_pack_docx

        pack = {
            "job_title": "Python Developer",
            "company": "Acme",
            "questions": [
                {
                    "question": "Tell me about a project",
                    "outline": "HRMS platform",
                    "source": "your confirmed facts",
                }
            ],
            "talking_points": ["HRMS platform"],
            "questions_to_ask": ["What does success look like?"],
        }
        data = render_prep_pack_docx(pack)
        assert data[:2] == b"PK"


# ---------------------------------------------------------------- P3: ATS --
class TestATSFillPlanner:
    def test_plan_from_questions(self) -> None:
        planner = ATSFillPlanner(
            [_fact("skill", skill="Python"), _fact("experience_years", 3)], _profile()
        )
        plan = planner.plan_from_questions(
            platform="greenhouse",
            job_url="https://boards.greenhouse.io/acme/jobs/1",
            questions=[
                {
                    "id": "1",
                    "label": "How many years of experience do you have?",
                    "type": "short_text",
                },
                {"id": "2", "label": "Upload your CV", "type": "file"},
            ],
        )
        assert plan["fillable_count"] >= 1
        kinds = {p["field_id"]: p["fillable"] for p in plan["fields"]}
        assert kinds["2"] is False  # file upload is human territory

    def test_reliability_gate(self) -> None:
        logs = [{"ok": True}] * 45 + [{"ok": False}] * 5  # 90% < 98% threshold
        verdict = ATSFillPlanner.reliability(logs)
        assert verdict["verdict"] == "not-reliable-enough"
        assert ATSFillPlanner.reliability([{"ok": True}])["verdict"] == "insufficient-data"


# ---------------------------------------------------------------- P4: sheets --
class TestAnswerSheets:
    def test_easy_apply_sheet_fills_from_facts(self) -> None:
        sheet = build_answer_sheet(
            platform="linkedin",
            facts=[_fact("skill", skill="Python"), _fact("experience_years", 3)],
            profile=_profile(),
        )
        assert sheet["platform"] == "linkedin"
        assert sheet["filled"] >= 1
        years = next(e for e in sheet["entries"] if "years" in e["question"].lower())
        assert "3+" in years["answer"]

    def test_naukri_sheet_has_recruiter_fields(self) -> None:
        sheet = build_answer_sheet(
            platform="naukri", facts=[_fact("skill", skill="Python")], profile=_profile()
        )
        assert any("headline" in e["question"].lower() for e in sheet["entries"])


# ------------------------------------------------------------- P5: scheduler --
class TestScheduler:
    def test_set_and_due(self, tmp_path: Any) -> None:
        from app.adapters.storage import JsonStore

        store = JsonStore(tmp_path)
        sched = Scheduler(store, lambda pid: {"ok": True}, lambda pid: {"ok": True})
        out = sched.set_schedule("p1", enabled=True, interval_minutes=30)
        assert out["enabled"] is True and out["interval_minutes"] == 30
        # force next_run_at into the past -> due
        raw = store.get("schedules", "p1")
        store.upsert("schedules", "p1", {**raw, "next_run_at": 0})
        assert sched._due_profiles() == ["p1"]
        off = sched.set_schedule("p1", enabled=False)
        assert off["enabled"] is False and off["next_run_at"] is None

    def test_run_for_persists_result(self, tmp_path: Any) -> None:
        from app.adapters.storage import JsonStore

        store = JsonStore(tmp_path)
        calls: list[str] = []
        sched = Scheduler(store, lambda pid: calls.append("d"), lambda pid: calls.append("m"))
        sched.set_schedule("p1", enabled=True)
        sched._run_for("p1")
        assert calls == ["d", "m"]
        assert store.get("schedules", "p1")["last_run_at"] is not None


# ---------------------------------------------------------------- P6: intel --
class TestEmployerIntel:
    def test_company_report_and_notes(self, tmp_path: Any) -> None:
        from app.adapters.storage import JsonStore
        from app.domain.applications import Application, ApplicationStatus, EntryMethod
        from app.services.queue import LedgerService

        store = JsonStore(tmp_path)
        ledger = LedgerService()
        a1 = Application(
            profile_id="p1",
            entry_method=EntryMethod.MANUAL,
            company="Acme",
            title="Dev",
            submission_evidence={"method": "user_assertion"},
        )
        a2 = a1.model_copy(
            update={
                "id": "b" * 12,
                "status": ApplicationStatus.REJECTED,
            }
        )
        ledger.create(a1)
        ledger.create(a2)
        intel = EmployerIntel(store, ledger)
        out = intel.add_note("Acme", "recruiter ghosted after round 2")
        assert out["ok"]
        report = intel.company_report("acme")
        assert report["applications"] == 2
        assert report["outcomes"].get("rejected") == 1
        assert report["notes"]
        assert intel.top_companies()[0]["company"] == "Acme"
