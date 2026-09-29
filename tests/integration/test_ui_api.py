"""Integration tests: JSON API surface of the local UI server.

Routes are dispatched through the real route table (`_JSON_GET` / `_JSON_POST`)
so a renamed or missing endpoint fails here rather than in the browser. No
sockets are opened; the SSE broker is asserted on directly.
"""

from __future__ import annotations

import csv
import io
import json
import queue
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.ui import server as ui_server
from app.ui.server import UILauncher

RESUME_TEXT = """Ada Lovelace
London, UK | ada@example.com

Summary
Backend engineer with 7 years building Python services and data pipelines.

Skills
Python, FastAPI, Docker, PostgreSQL, Kubernetes
"""


@pytest.fixture()
def launcher(tmp_path: Any) -> UILauncher:
    data = tmp_path / "api-data"
    data.mkdir()
    ln = UILauncher(data_dir=str(data))
    services = ln._services()
    app = Application(
        profile_id="p1",
        entry_method=EntryMethod.MANUAL,
        company="Acme",
        title="Python Developer",
        submission_evidence={"method": "user_assertion"},
        status=ApplicationStatus.SUBMITTED,
    )
    services["ledger"].create(app)
    services["store"].upsert("applications", app.id, app.model_dump(mode="json"))
    services["store"].upsert(
        "profiles", "p1", {"id": "p1", "name": "Dev", "contact_email": "dev@example.com"}
    )
    ln._cache = services
    return ln


def _get(launcher: UILauncher, path: str) -> Any:
    """Dispatch a GET through the registered route table."""
    ui_server._register_routes()
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    for pattern, handler in ui_server._JSON_GET:
        match = pattern.match(parsed.path)
        if match:
            return handler(launcher, match, {}, query)
    raise AssertionError(f"no GET route registered for {parsed.path}")


def _post(launcher: UILauncher, path: str, body: dict[str, Any] | None = None) -> Any:
    ui_server._register_routes()
    for pattern, handler in ui_server._JSON_POST:
        match = pattern.match(path)
        if match:
            return handler(launcher, match, body or {})
    raise AssertionError(f"no POST route registered for {path}")


def _download(launcher: UILauncher, **query: str) -> tuple[str, str, bytes]:
    return ui_server._report_download(launcher, {k: [v] for k, v in query.items()})


class TestStateAndMeta:
    def test_snapshot_exposes_the_live_summary(self, launcher: UILauncher) -> None:
        snap = _get(launcher, "/api/state")["snapshot"]
        for key in ("kanban", "profiles", "pipeline_counts", "counts", "server_time"):
            assert key in snap, key
        assert snap["counts"]["applications"] == 1

    def test_meta_drives_the_front_end(self, launcher: UILauncher) -> None:
        meta = _get(launcher, "/api/meta")
        assert meta["stages"][0]["id"] == "upload"
        assert meta["stages"][-1]["id"] == "done"
        assert meta["run_steps"], "the agent timeline needs steps"
        assert meta["columns"], "the board needs columns"
        assert "applications" in meta["reports"]["kinds"]
        assert "csv" in meta["reports"]["formats"]
        # every stage carries the label/detail the animation renders
        for stage in meta["stages"]:
            assert stage["label"] and stage["detail"]

    def test_profiles_list_is_served(self, launcher: UILauncher) -> None:
        listed = _get(launcher, "/api/profiles")
        assert listed["profiles"][0]["name"] == "Dev"


class TestAiSettingsApi:
    def test_status_reports_choices_presets_and_config(self, launcher: UILauncher) -> None:
        ai = _get(launcher, "/api/ai/status")["ai"]
        assert set(ai["provider_choices"]) >= {"auto", "gemini", "local", "rule"}
        assert ai["config"]["provider"] in ai["provider_choices"]
        keys = {p["key"] for p in ai["presets"]}
        assert {"llamacpp", "ollama", "lmstudio", "vllm"} <= keys
        # every preset is display-only advice, never an installed runtime
        for preset in ai["presets"]:
            assert preset["endpoint"].startswith("http")

    def test_local_endpoint_and_model_roundtrip(self, launcher: UILauncher) -> None:
        saved = _post(
            launcher,
            "/api/settings/ai",
            {"local_endpoint": "http://127.0.0.1:11434", "local_model": "qwen2.5-3b"},
        )
        assert saved["ok"] is True
        ai = _get(launcher, "/api/ai/status")["ai"]
        assert ai["config"]["local_endpoint"] == "http://127.0.0.1:11434"
        assert ai["config"]["local_model"] == "qwen2.5-3b"
        assert ai["providers"]["local"]["configured"] is True

    def test_a_file_path_is_accepted_as_the_endpoint(self, launcher: UILauncher) -> None:
        _post(launcher, "/api/settings/ai", {"local_endpoint": r"D:\models\qwen.gguf"})
        ai = _get(launcher, "/api/ai/status")["ai"]
        assert ai["providers"]["local"]["path"] == r"D:\models\qwen.gguf"

    def test_unknown_provider_is_rejected_not_silently_ignored(self, launcher: UILauncher) -> None:
        result = _post(launcher, "/api/settings/ai", {"provider": "hal-9000"})
        assert result["ok"] is False
        assert result["error"]

    def test_gemini_key_is_write_only(self, launcher: UILauncher) -> None:
        assert _post(launcher, "/api/settings/gemini-key", {"api_key": "AIza-secret"})["ok"]
        status = str(_get(launcher, "/api/ai/status"))
        assert "AIza-secret" not in status  # never echoed back to the browser


class TestAiTestAndProbe:
    def test_test_returns_a_shaped_result_the_ui_can_render(self, launcher: UILauncher) -> None:
        result = _post(launcher, "/api/ai/test")["test"]
        assert "ok" in result
        assert result.get("provider") or result.get("message") or result.get("error")

    def test_local_probe_reports_reachability_not_an_exception(self, launcher: UILauncher) -> None:
        probe = _post(launcher, "/api/ai/local-probe")["probe"]
        assert isinstance(probe["reachable"], bool)
        assert "endpoint" in probe
        # with no local server configured/running this must be an honest False
        if not probe["reachable"]:
            assert probe["error"]


class TestDiagnostics:
    def test_hardware_probe_runs_locally(self, launcher: UILauncher) -> None:
        result = _get(launcher, "/api/system/diagnose")
        assert result["ok"] is True
        hardware = result["hardware"]
        assert hardware["os"]
        assert hardware["cores"] >= 1
        assert hardware["ram_total_gb"] > 0


class TestReportPreviewAndSummary:
    def test_preview_returns_columns_and_rows(self, launcher: UILauncher) -> None:
        preview = _get(launcher, "/api/reports/preview?report=applications")
        assert preview["ok"] is True
        assert "company" in preview["columns"]
        assert preview["rows"][0]["company"] == "Acme"

    def test_preview_caps_row_count(self, launcher: UILauncher) -> None:
        preview = _get(launcher, "/api/reports/preview?report=facts")
        assert len(preview["rows"]) <= 200

    def test_unknown_report_is_a_client_error_not_a_crash(self, launcher: UILauncher) -> None:
        preview = _get(launcher, "/api/reports/preview?report=nope")
        assert preview["ok"] is False
        assert "unknown report" in preview["error"]

    def test_summary_endpoint(self, launcher: UILauncher) -> None:
        summary = _get(launcher, "/api/reports/summary")["summary"]
        assert summary["total_applications"] == 1
        assert summary["distinct_companies"] == 1

    def test_profile_scope_is_honoured(self, launcher: UILauncher) -> None:
        scoped = _get(launcher, "/api/reports/summary?profile_id=other")
        assert scoped["summary"]["total_applications"] == 0


class TestReportDownload:
    @pytest.mark.parametrize(
        "fmt,mime",
        [("csv", "text/csv"), ("json", "application/json"), ("html", "text/html")],
    )
    def test_every_format_downloads(self, launcher: UILauncher, fmt: str, mime: str) -> None:
        filename, content_type, body = _download(launcher, report="applications", format=fmt)
        assert content_type == mime
        assert filename.startswith("noloop-applications-")
        assert filename.endswith(f".{fmt}")
        assert isinstance(body, bytes) and body
        assert body.decode("utf-8")  # must be decodable as UTF-8

    def test_csv_parses_back_into_the_rows(self, launcher: UILauncher) -> None:
        _filename, _mime, body = _download(launcher, report="applications", format="csv")
        parsed = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
        assert parsed[0]["company"] == "Acme"

    def test_json_is_a_valid_envelope(self, launcher: UILauncher) -> None:
        _filename, _mime, body = _download(launcher, report="summary", format="json")
        data = json.loads(body.decode("utf-8"))
        assert data["report"] == "summary"
        assert data["summary"]["total_applications"] == 1
        # summary rows line up with their columns (regression: empty-cell CSV)
        assert all(set(row) == {"metric", "value"} for row in data["rows"])

    def test_html_is_a_standalone_document(self, launcher: UILauncher) -> None:
        _filename, _mime, body = _download(launcher, report="applications", format="html")
        html_out = body.decode("utf-8")
        assert html_out.startswith("<!DOCTYPE html>")
        assert "Acme" in html_out and "</html>" in html_out

    @pytest.mark.parametrize("kind", ["applications", "companies", "runs", "facts", "summary"])
    def test_all_kinds_download_as_csv(self, launcher: UILauncher, kind: str) -> None:
        _filename, _mime, body = _download(launcher, report=kind, format="csv")
        assert body.decode("utf-8").splitlines()[0]

    def test_unknown_report_rejected(self, launcher: UILauncher) -> None:
        with pytest.raises(ValueError, match="unknown report"):
            _download(launcher, report="payroll", format="csv")

    def test_unknown_format_rejected(self, launcher: UILauncher) -> None:
        with pytest.raises(ValueError, match="unknown format"):
            _download(launcher, report="applications", format="exe")

    def test_profile_scope_reaches_the_file(self, launcher: UILauncher) -> None:
        _filename, _mime, body = _download(
            launcher, report="applications", format="json", profile_id="nobody"
        )
        data = json.loads(body.decode("utf-8"))
        assert data["rows"] == []
        assert data["profile_id"] == "nobody"


class TestResumeImport:
    def test_missing_profile_is_a_clear_client_error(self, launcher: UILauncher) -> None:
        result = _post(launcher, "/api/resume/import", {"filename": "cv.txt", "text": "x"})
        assert result["ok"] is False
        assert "profile_id" in result["error"]

    def test_missing_content_rejected(self, launcher: UILauncher) -> None:
        result = _post(launcher, "/api/resume/import", {"profile_id": "p1"})
        assert result["ok"] is False
        assert "content" in result["error"]

    def test_returns_immediately_with_a_job_id(self, launcher: UILauncher) -> None:
        result = _post(
            launcher,
            "/api/resume/import",
            {"profile_id": "p1", "filename": "cv.txt", "text": RESUME_TEXT, "use_ai": False},
        )
        assert result["ok"] is True
        assert result["job_id"].startswith("import-")
        assert result["filename"] == "cv.txt"

    def test_background_import_publishes_stage_events_and_finishes(
        self, launcher: UILauncher
    ) -> None:
        events = launcher.broker.subscribe()
        try:
            job_id = _post(
                launcher,
                "/api/resume/import",
                {"profile_id": "p1", "filename": "cv.txt", "text": RESUME_TEXT, "use_ai": False},
            )["job_id"]
            result, _frames = _drain_until_done(events, job_id)
        finally:
            launcher.broker.unsubscribe(events)

        assert result["ok"] is True
        assert result["facts_created"] > 0
        assert all(s["status"] in ("done", "skipped", "failed") for s in result["stages"])

    def test_stage_events_stream_over_sse_shape(self, launcher: UILauncher) -> None:
        events = launcher.broker.subscribe()
        try:
            job_id = _post(
                launcher,
                "/api/resume/import",
                {"profile_id": "p1", "filename": "cv.txt", "text": RESUME_TEXT, "use_ai": False},
            )["job_id"]
            _result, frames = _drain_until_done(events, job_id)
        finally:
            launcher.broker.unsubscribe(events)
        # the browser parses these as SSE frames
        progress = [f for f in frames if f.startswith("event: progress\n")]
        assert progress, "the animated timeline is driven by progress frames"
        assert any("upload" in f or "validate" in f for f in progress)


def _drain_until_done(
    events: queue.Queue[str], job_id: str, timeout: float = 20.0
) -> tuple[dict[str, Any], list[str]]:
    """Read SSE frames until the matching task_done arrives.

    Returns ``(result, frames)`` so a test can assert on both the outcome and
    the transport the browser actually consumes.
    """
    collected: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = events.get(timeout=0.5)
        except queue.Empty:
            continue
        collected.append(message)
        if "task_done" not in message or job_id not in message:
            continue
        payload = json.loads(message.split("data: ", 1)[1].strip())
        if payload.get("job_id") == job_id:
            return payload["result"], collected
    raise AssertionError(f"import {job_id} never published task_done")


class TestBoardMoves:
    def test_legal_move_is_accepted(self, launcher: UILauncher) -> None:
        app_id = launcher.snapshot()["kanban"][0]["id"]
        result = _post(
            launcher,
            "/api/board/move",
            {"application_id": app_id, "to_status": "interview", "at": "2026-01-01T00:00:00Z"},
        )
        assert result["ok"] is True
        assert launcher.snapshot()["kanban"][0]["status"] == "interview"

    def test_illegal_move_is_refused_with_a_reason(self, launcher: UILauncher) -> None:
        app_id = launcher.snapshot()["kanban"][0]["id"]
        result = _post(
            launcher,
            "/api/board/move",
            {"application_id": app_id, "to_status": "discovered", "at": "2026-01-01T00:00:00Z"},
        )
        assert result["ok"] is False
        assert "illegal transition" in result["error"]
