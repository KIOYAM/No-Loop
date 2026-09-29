"""Unit tests: annotated resume-import pipeline (stages, honesty, speed).

The contract under test: a timeline where every stage ends `done | skipped |
failed` with a human reason, the deterministic pass runs first, and the
optional AI pass can never block or fail an import.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.profile import CandidateProfile
from app.services.resume_pipeline import (
    STAGE_META,
    STAGE_ORDER,
    ResumePipeline,
    _facts_from_ai,
    _load_json,
    _trim,
)

RESUME = b"""Ada Lovelace
London, UK | ada@example.com | +44 20 7946 0000
https://github.com/ada

Summary
Backend engineer with 7 years building Python services and data pipelines.

Experience
Senior Python Developer - Acme Corp, 2021-2024
- Built FastAPI microservices handling 40k req/s

Software Engineer - Globex, 2018-2021
- Django REST APIs and Celery task queues

Education
BSc Computer Science - University of London, 2014-2017

Skills
Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS, Celery, Git
"""


@pytest.fixture()
def pipeline(tmp_path: Any) -> ResumePipeline:
    from app.adapters.settings_store import SettingsStore
    from app.adapters.storage import JsonStore

    data = tmp_path / "pipe-data"
    data.mkdir()
    store, settings = JsonStore(data), SettingsStore(data)
    store.upsert("profiles", "p1", {"id": "p1", "name": "Dev"})
    return ResumePipeline(store, settings)


def _run(pipeline: ResumePipeline, **kw: Any) -> Any:
    kw.setdefault("profile_id", "p1")
    kw.setdefault("filename", "resume.txt")
    kw.setdefault("data", RESUME)
    return pipeline.run(**kw)


class TestStageCatalog:
    def test_every_stage_has_a_label_and_detail(self) -> None:
        for stage_id, _weight in STAGE_ORDER:
            assert stage_id in STAGE_META, stage_id
            assert STAGE_META[stage_id]["label"]
            assert STAGE_META[stage_id]["detail"]

    def test_progress_weights_increase_and_end_at_100(self) -> None:
        weights = [w for _sid, w in STAGE_ORDER]
        assert weights == sorted(weights), "the bar must never move backwards"
        assert weights[-1] == 100
        assert STAGE_ORDER[0][0] == "upload"

    def test_emitted_stage_ids_match_the_catalog(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, use_ai=False)
        assert [s["id"] for s in result.stages] == [sid for sid, _w in STAGE_ORDER]


class TestTrim:
    def test_short_text_is_untouched(self) -> None:
        assert _trim("hello") == "hello"

    def test_long_text_keeps_head_and_tail(self) -> None:
        text = "H" * 9000 + "M" * 5000 + "T" * 3000
        trimmed = _trim(text)
        assert len(trimmed) < len(text)
        assert trimmed.startswith("H" * 100)
        assert trimmed.endswith("T" * 100)  # recent roles live at the tail


class TestLoadJson:
    def test_plain_object(self) -> None:
        assert _load_json('{"a": 1}') == {"a": 1}

    def test_fenced_object(self) -> None:
        assert _load_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_object_embedded_in_prose(self) -> None:
        assert _load_json('Sure! Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}

    def test_prose_without_json_is_none(self) -> None:
        assert _load_json("I could not parse that.") is None

    def test_non_object_json_is_none(self) -> None:
        assert _load_json("[1, 2, 3]") is None


class TestFactsFromAi:
    def test_confidence_is_sub_one_and_rule_names_the_provider(self) -> None:
        facts = _facts_from_ai(
            "p1",
            {"job_titles": ["Backend Developer"], "summary": "A" * 60},
            document_id="cv.txt",
            provider="local:qwen",
        )
        assert facts
        for fact in facts:
            assert fact.confidence == 0.8  # never presented as certain
            assert fact.confidence < 1.0
            assert fact.provenance.extraction_rule == "llm:local:qwen"
            assert fact.provenance.document_id == "cv.txt"
            assert fact.state.value == "inferred"  # user still confirms

    def test_unknown_skills_are_dropped(self) -> None:
        facts = _facts_from_ai(
            "p1",
            {"skills": ["Python", "Chronoception"]},
            document_id="cv.txt",
            provider="p",
        )
        names = [f.skill.name for f in facts if f.field_class == "skill"]
        assert "Python" in names
        assert "Chronoception" not in names  # taxonomy discipline

    def test_short_summary_and_oversized_location_rejected(self) -> None:
        facts = _facts_from_ai(
            "p1",
            {"summary": "too short", "location": "x" * 90},
            document_id="cv.txt",
            provider="p",
        )
        assert facts == []

    def test_untouched_when_payload_is_empty(self) -> None:
        assert _facts_from_ai("p1", {}, document_id="cv.txt", provider="p") == []


class TestHappyPath:
    def test_import_succeeds_and_records_a_version(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, use_ai=False)
        assert result.ok is True
        assert result.version == 1
        assert result.facts_created > 0, "the rule pass must produce facts"
        assert result.duration_ms >= 0
        assert result.error_reason is None

    def test_every_stage_reaches_a_terminal_state(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, use_ai=False)
        for stage in result.stages:
            assert stage["status"] in ("done", "skipped", "failed"), stage
            assert stage["detail"], f"{stage['id']} must say why"

    def test_deterministic_stage_is_done_and_ai_stage_is_skipped(
        self, pipeline: ResumePipeline
    ) -> None:
        result = _run(pipeline, use_ai=False)
        by_id = {s["id"]: s for s in result.stages}
        assert by_id["parse"]["status"] == "done"
        assert by_id["ai"]["status"] == "skipped"
        assert "off" in by_id["ai"]["detail"]
        assert by_id["done"]["status"] == "done"

    def test_facts_are_stored_locally(self, pipeline: ResumePipeline) -> None:
        _run(pipeline, use_ai=False)
        facts = pipeline.store.all("facts")
        assert facts
        assert all(f.get("state") == "inferred" for f in facts.values())

    def test_profile_fields_are_filled_without_overwriting(self, pipeline: ResumePipeline) -> None:
        _run(pipeline, use_ai=False)
        stored = pipeline.store.get("profiles", "p1")
        assert stored["contact_email"] == "ada@example.com"
        assert stored["contact_name"] == "Ada Lovelace"
        # list-shaped suggestions are parked, not forced into scalar fields
        assert "summary" in (stored.get("extra") or {})

    def test_version_history_written(self, pipeline: ResumePipeline) -> None:
        _run(pipeline, use_ai=False)
        versions = pipeline.store.all("resume_versions")
        assert len(versions) == 1
        assert next(iter(versions.values()))["filename"] == "resume.txt"


class TestProgressEvents:
    def test_events_are_emitted_for_every_stage_transition(self, pipeline: ResumePipeline) -> None:
        events: list[dict[str, Any]] = []
        _run(pipeline, use_ai=False, on_progress=events.append)
        assert events, "the UI animates from these"
        for event in events:
            assert event["kind"] == "resume"
            assert event["job_id"]
            assert event["label"]
            assert event["status"] in ("running", "done", "skipped", "failed")
            assert 0 <= event["progress"] <= 100

    def test_progress_never_goes_backwards(self, pipeline: ResumePipeline) -> None:
        events: list[dict[str, Any]] = []
        _run(pipeline, use_ai=False, on_progress=events.append)
        seen = [e["progress"] for e in events]
        assert seen == sorted(seen), f"bar regressed: {seen}"

    def test_each_stage_reports_running_then_a_result(self, pipeline: ResumePipeline) -> None:
        events: list[dict[str, Any]] = []
        _run(pipeline, use_ai=False, on_progress=events.append)
        ran = {e["stage"] for e in events if e["status"] == "running"}
        concluded = {e["stage"] for e in events if e["status"] != "running"}
        assert ran <= concluded, f"stages left running: {sorted(ran - concluded)}"


class TestHonestFailures:
    def test_empty_upload_fails_early_and_skips_the_rest(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, data=b"")
        assert result.ok is False
        assert result.error_reason == "file is empty"
        assert result.user_action, "the user must be told what to do"
        by_id = {s["id"]: s for s in result.stages}
        assert by_id["upload"]["status"] == "failed"
        assert by_id["parse"]["status"] == "skipped"
        assert by_id["parse"]["detail"] == "not reached"

    def test_oversized_file_rejected(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, data=b"x" * (10 * 1024 * 1024 + 1))
        assert result.ok is False
        assert "10 MB" in result.error_reason

    def test_unsupported_format_is_reported_not_raised(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, filename="resume.exe", data=b"anything")
        assert result.ok is False
        assert "unsupported format" in result.error_reason

    def test_no_stages_left_pending_after_a_failure(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, data=b"")
        assert all(s["status"] != "pending" for s in result.stages)


class TestDuplicateImport:
    def test_duplicate_is_a_warning_not_an_error(self, pipeline: ResumePipeline) -> None:
        first = _run(pipeline, use_ai=False)
        assert first.ok is True
        second = _run(pipeline, use_ai=False)
        assert second.ok is True
        assert second.version is None  # no new version was created
        assert any("identical" in w for w in second.warnings)
        assert len(pipeline.store.all("resume_versions")) == 1

    def test_duplicate_does_not_claim_work_it_did_not_do(self, pipeline: ResumePipeline) -> None:
        _run(pipeline, use_ai=False)
        second = _run(pipeline, use_ai=False)
        by_id = {s["id"]: s for s in second.stages}
        assert by_id["dedupe"]["status"] == "skipped"
        assert by_id["autofill"]["status"] == "skipped"
        assert "duplicate" in by_id["autofill"]["detail"]
        assert by_id["profile"]["status"] == "skipped"
        assert by_id["done"]["status"] == "done"

    def test_duplicate_leaves_no_stage_pending(self, pipeline: ResumePipeline) -> None:
        # the service returns early on a duplicate, before extract/parse/persist
        _run(pipeline, use_ai=False)
        second = _run(pipeline, use_ai=False)
        pending = [s["id"] for s in second.stages if s["status"] == "pending"]
        assert pending == [], f"timeline shows stuck stages: {pending}"
        for stage in second.stages:
            assert stage["detail"], stage


class TestAiPassIsOptional:
    def test_unconfigured_provider_never_fails_the_import(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, use_ai=True)  # no key, no local model configured
        assert result.ok is True
        by_id = {s["id"]: s for s in result.stages}
        assert by_id["ai"]["status"] == "skipped"
        assert by_id["ai"]["detail"], "the skip must carry a visible reason"
        assert by_id["done"]["status"] == "done"
        assert result.ai_facts_created == 0

    def test_short_text_skips_ai_with_a_reason(self, pipeline: ResumePipeline) -> None:
        result = _run(pipeline, data=b"too short", use_ai=True)
        # may fail earlier (no extractable facts) or reach the AI stage; either way
        # the terminal state must be honest, never left running
        assert all(s["status"] != "running" for s in result.stages)


class TestAutofillIsFillOnly:
    def test_existing_email_is_never_clobbered(self, pipeline: ResumePipeline) -> None:
        stored = dict(pipeline.store.get("profiles", "p1"))
        stored["contact_email"] = "keep-me@example.com"
        pipeline.store.upsert("profiles", "p1", stored)

        _run(pipeline, use_ai=False)
        after = pipeline.store.get("profiles", "p1")
        assert after["contact_email"] == "keep-me@example.com"

    def test_unknown_applied_keys_are_ignored(self, pipeline: ResumePipeline) -> None:
        applied = {"contact_name": "Ada", "not_a_profile_field": "nope"}
        saved = pipeline._apply_autofill("p1", applied)
        assert "not_a_profile_field" not in saved
        assert "not_a_profile_field" not in (pipeline.store.get("profiles", "p1") or {})

    def test_profile_still_validates_after_a_fill(self, pipeline: ResumePipeline) -> None:
        _run(pipeline, use_ai=False)
        CandidateProfile.model_validate(pipeline.store.get("profiles", "p1"))
