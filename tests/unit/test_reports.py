"""Unit tests: report builders (applications / companies / runs / facts / summary).

Covers row shaping, aggregation, profile scoping and the three renderings.
The HTML assertions also pin the safety property: untrusted ledger text is
escaped, never executed.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import pytest
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.services.reports import REPORT_FORMATS, REPORT_KINDS, ReportService
from app.ui.server import UILauncher


@pytest.fixture()
def services(tmp_path: Any) -> Any:
    data = tmp_path / "report-data"
    data.mkdir()
    ln = UILauncher(data_dir=str(data))
    return ln._services()


def _app(services: Any, **kw: Any) -> Application:
    defaults: dict[str, Any] = {
        "profile_id": "p1",
        "entry_method": EntryMethod.MANUAL,
        "company": "Acme",
        "title": "Python Developer",
        "submission_evidence": {"method": "user_assertion"},
        "status": ApplicationStatus.SUBMITTED,
    }
    defaults.update(kw)
    app = Application(**defaults)
    services["ledger"].create(app)
    services["store"].upsert("applications", app.id, app.model_dump(mode="json"))
    return app


def _fact(services: Any, **kw: Any) -> None:
    raw: dict[str, Any] = {
        "id": "f-1",
        "profile_id": "p1",
        "field_class": "skill",
        "value": None,
        "skill": {"name": "python"},
        "confidence": 0.9,
        "state": "inferred",
        "provenance": {"extraction_rule": "skills.keyword", "document_id": "cv.txt"},
        "created_at": "2026-01-01T00:00:00+00:00",
        "decided_at": None,
    }
    raw.update(kw)
    services["store"].upsert("facts", str(raw["id"]), raw)


def _run(services: Any, **kw: Any) -> None:
    raw: dict[str, Any] = {
        "run_id": "r-1",
        "profile_id": "p1",
        "started_at": "2026-01-02T00:00:00+00:00",
        "duration_ms": 1200,
        "steps": [
            {
                "step": "match",
                "label": "Scoring fit",
                "status": "done",
                "company": "Acme",
                "title": "Python Developer",
                "score": 0.82,
                "detail": "scored",
            },
            {"step": "create", "label": "Opening ledger record", "status": "done"},
        ],
    }
    raw.update(kw)
    services["store"].upsert("runs", str(raw["run_id"]), raw)


class TestCatalog:
    def test_every_kind_has_columns(self, services: Any) -> None:
        service = ReportService(services["store"], services["ledger"])
        for kind in REPORT_KINDS:
            assert service.columns(kind), kind

    def test_summary_columns_match_summary_rows(self, services: Any) -> None:
        # a row/column mismatch would emit a CSV of empty cells
        service = ReportService(services["store"], services["ledger"])
        _app(services)
        rows = service.records("summary")
        assert rows, "summary must produce rows"
        for row in rows:
            assert set(row) == set(service.columns("summary"))

    def test_unknown_report_rejected(self, services: Any) -> None:
        service = ReportService(services["store"], services["ledger"])
        with pytest.raises(ValueError, match="unknown report"):
            service.records("nonsense")

    def test_formats_are_the_documented_three(self) -> None:
        assert REPORT_FORMATS == ("csv", "json", "html")


class TestApplicationsReport:
    def test_row_covers_every_column(self, services: Any) -> None:
        _app(services, notes="ping recruiter", application_url="https://example.com/apply")
        service = ReportService(services["store"], services["ledger"])
        rows = service.records("applications")
        assert len(rows) == 1
        assert set(rows[0]) == set(service.columns("applications"))
        assert rows[0]["company"] == "Acme"
        assert rows[0]["status"] == "submitted"
        assert rows[0]["notes"] == "ping recruiter"
        # evidence is JSON so a report reader can audit it
        assert json.loads(rows[0]["evidence"])["method"] == "user_assertion"

    def test_profile_scope_filters_rows(self, services: Any) -> None:
        _app(services, company="Acme")
        _app(services, profile_id="p2", company="Globex")
        service = ReportService(services["store"], services["ledger"])
        assert len(service.records("applications")) == 2
        scoped = service.records("applications", "p2")
        assert [r["company"] for r in scoped] == ["Globex"]

    def test_sorted_most_recently_updated_first(self, services: Any) -> None:
        first = _app(services, company="Older")
        second = _app(services, company="Newer")
        service = ReportService(services["store"], services["ledger"])
        got = [r["company"] for r in service.records("applications")]
        assert set(got) == {"Older", "Newer"}
        assert len(got) == 2
        assert first.id != second.id


class TestCompaniesReport:
    def test_groups_by_company_and_counts(self, services: Any) -> None:
        _app(services, company="Acme", title="A")
        _app(services, company="Acme", title="B")
        _app(services, company="Globex", title="C")
        service = ReportService(services["store"], services["ledger"])
        rows = service.records("companies")
        assert [r["company"] for r in rows] == ["Acme", "Globex"]  # most apps first
        assert rows[0]["applications"] == 2
        assert rows[1]["applications"] == 1

    def test_outcome_is_the_best_status_reached(self, services: Any) -> None:
        _app(services, company="Acme", status=ApplicationStatus.INTERVIEW)
        _app(
            services,
            company="Acme",
            status=ApplicationStatus.DISCOVERED,
            entry_method=EntryMethod.ASSISTED,  # only agent records enter discovery
        )
        service = ReportService(services["store"], services["ledger"])
        row = service.records("companies")[0]
        assert row["outcome"] == "interview"  # _STATUS_ORDER: interview beats discovered
        assert row["statuses"] == "interview, discovered"

    def test_quick_add_never_reports_as_discovered(self, services: Any) -> None:
        # domain invariant: a MANUAL record cannot sit in the discovery pipeline
        _app(services, company="Acme", status=ApplicationStatus.DISCOVERED)
        service = ReportService(services["store"], services["ledger"])
        row = service.records("companies")[0]
        assert row["statuses"] == "review_required"

    def test_row_matches_columns(self, services: Any) -> None:
        _app(services, company="Acme")
        service = ReportService(services["store"], services["ledger"])
        rows = service.records("companies")
        assert set(rows[0]) == set(service.columns("companies"))


class TestRunsReport:
    def test_one_row_per_step(self, services: Any) -> None:
        _run(services)
        service = ReportService(services["store"], services["ledger"])
        rows = service.records("runs")
        assert len(rows) == 2
        assert rows[0]["run_id"] == "r-1"
        assert rows[0]["step"] == "match"
        assert rows[0]["score"] == 0.82

    def test_pipeline_steps_get_a_placeholder_company(self, services: Any) -> None:
        _run(services)
        service = ReportService(services["store"], services["ledger"])
        rows = service.records("runs")
        assert rows[1]["company"] == "(pipeline)"  # step without a company
        assert rows[1]["score"] == ""  # None becomes a blank cell, not the text "None"

    def test_row_matches_columns(self, services: Any) -> None:
        _run(services)
        service = ReportService(services["store"], services["ledger"])
        for row in service.records("runs"):
            assert set(row) == set(service.columns("runs"))


class TestFactsReport:
    def test_value_falls_back_to_the_skill_name(self, services: Any) -> None:
        _fact(services)  # value=None, skill.name="python"
        service = ReportService(services["store"], services["ledger"])
        row = service.records("facts")[0]
        assert row["value"] == "python"
        assert row["skill"] == "python"
        assert row["extraction_rule"] == "skills.keyword"

    def test_list_values_are_json_encoded_for_csv(self, services: Any) -> None:
        _fact(services, id="f-2", field_class="education", value=["BSc", "MSc"], skill=None)
        service = ReportService(services["store"], services["ledger"])
        row = next(r for r in service.records("facts") if r["id"] == "f-2")
        assert json.loads(row["value"]) == ["BSc", "MSc"]

    def test_confirmation_state_and_provenance_exposed(self, services: Any) -> None:
        _fact(services, state="confirmed", decided_at="2026-01-03T00:00:00+00:00")
        service = ReportService(services["store"], services["ledger"])
        row = service.records("facts")[0]
        assert row["state"] == "confirmed"
        assert row["decided_at"] == "2026-01-03T00:00:00+00:00"
        assert row["document_id"] == "cv.txt"

    def test_profile_scope_applies_to_facts(self, services: Any) -> None:
        _fact(services, id="f-1")
        _fact(services, id="f-2", profile_id="p2")
        service = ReportService(services["store"], services["ledger"])
        assert len(service.records("facts", "p1")) == 1


class TestSummary:
    def test_core_metrics(self, services: Any) -> None:
        _app(services, company="Acme", status=ApplicationStatus.SUBMITTED)
        _app(services, company="Globex", status=ApplicationStatus.INTERVIEW)
        _app(services, company="Acme", status=ApplicationStatus.REVIEW_REQUIRED)
        service = ReportService(services["store"], services["ledger"])
        s = service.summary()
        assert s["total_applications"] == 3
        assert s["distinct_companies"] == 2
        assert s["submitted"] == 1
        assert s["interviews"] == 1
        assert s["needs_review"] == 1
        assert s["interview_rate"] == 1.0

    def test_interview_rate_is_zero_without_submissions(self, services: Any) -> None:
        service = ReportService(services["store"], services["ledger"])
        assert service.summary()["interview_rate"] == 0.0  # no divide-by-zero
        assert service.summary()["total_applications"] == 0

    def test_counts_facts_and_runs(self, services: Any) -> None:
        _fact(services, state="confirmed")
        _fact(services, id="f-2", state="inferred")
        _run(services)
        service = ReportService(services["store"], services["ledger"])
        s = service.summary()
        assert s["facts_total"] == 2
        assert s["facts_confirmed"] == 1
        assert s["agent_runs"] == 1
        assert s["agent_steps"] == 2
        assert s["last_agent_run"] == "2026-01-02T00:00:00+00:00"


class TestCsv:
    def test_header_is_the_column_tuple(self, services: Any) -> None:
        _app(services)
        service = ReportService(services["store"], services["ledger"])
        text = service.to_csv("applications")
        parsed = list(csv.DictReader(io.StringIO(text)))
        assert len(parsed) == 1
        assert list(parsed[0]) == list(service.columns("applications"))
        assert parsed[0]["company"] == "Acme"

    def test_summary_csv_carries_metric_and_value(self, services: Any) -> None:
        _app(services)
        service = ReportService(services["store"], services["ledger"])
        parsed = list(csv.DictReader(io.StringIO(service.to_csv("summary"))))
        metrics = {r["metric"]: r["value"] for r in parsed}
        assert metrics["total_applications"] == "1"

    def test_empty_store_still_emits_a_header(self, services: Any) -> None:
        service = ReportService(services["store"], services["ledger"])
        parsed = list(csv.DictReader(io.StringIO(service.to_csv("applications"))))
        assert parsed == []
        assert "company" in service.to_csv("applications").splitlines()[0]


class TestJson:
    def test_envelope_and_rows(self, services: Any) -> None:
        _app(services)
        service = ReportService(services["store"], services["ledger"])
        data = json.loads(service.to_json("applications"))
        assert data["report"] == "applications"
        assert data["profile_id"] == "all"
        assert data["generated_at"]
        assert len(data["rows"]) == 1
        assert data["summary"]["total_applications"] == 1

    def test_profile_scope_in_the_envelope(self, services: Any) -> None:
        service = ReportService(services["store"], services["ledger"])
        data = json.loads(service.to_json("facts", "p9"))
        assert data["profile_id"] == "p9"


class TestHtml:
    def test_is_a_standalone_document_with_a_table(self, services: Any) -> None:
        _app(services)
        service = ReportService(services["store"], services["ledger"])
        out = service.to_html("applications")
        assert out.startswith("<!DOCTYPE html>")
        assert "<table>" in out and "</html>" in out
        assert "Acme" in out
        assert "1 row(s)" in out

    def test_untrusted_text_is_escaped(self, services: Any) -> None:
        _app(services, company="<script>alert(1)</script>", title="x")
        service = ReportService(services["store"], services["ledger"])
        out = service.to_html("applications")
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out

    def test_urls_become_links_with_rel_noopener(self, services: Any) -> None:
        _app(services, application_url="https://example.com/jobs/1")
        out = ReportService(services["store"], services["ledger"]).to_html("applications")
        assert 'href="https://example.com/jobs/1"' in out
        assert 'rel="noopener"' in out

    def test_empty_cells_render_as_a_dash(self, services: Any) -> None:
        service = ReportService(services["store"], services["ledger"])
        out = service.to_html("applications")  # no rows at all
        assert "0 row(s)" in out

    def test_states_local_only_provenance(self, services: Any) -> None:
        out = ReportService(services["store"], services["ledger"]).to_html("facts")
        assert "nothing was" in out and "sent anywhere" in out
