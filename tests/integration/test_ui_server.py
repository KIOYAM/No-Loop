"""Integration tests: local UI server (no real sockets; handler logic direct)."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.ui.server import EventBroker, UILauncher


@pytest.fixture()
def launcher(tmp_path):
    data = tmp_path / "ui-data"
    data.mkdir()
    ln = UILauncher(data_dir=str(data))
    services = ln._services()
    app = Application(
        profile_id="prof-1",
        entry_method=EntryMethod.MANUAL,
        company="Acme",
        title="Python Developer",
        submission_evidence={"method": "user_assertion"},
        status=ApplicationStatus.REVIEW_REQUIRED,
    )
    services["ledger"].create(app)
    services["store"].upsert("profiles", "prof-1", {"id": "prof-1", "name": "Dev"})
    services["store"].upsert("applications", app.id, app.model_dump(mode="json"))
    ln._cache = services  # pre-seed cache
    return ln


class TestSnapshot:
    def test_snapshot_has_kanban_pipeline_gemini(self, launcher: Any) -> None:
        snap = launcher.snapshot()
        assert len(snap["kanban"]) == 1
        assert snap["kanban"][0]["company"] == "Acme"
        assert snap["pipeline_counts"]["review"] == 1
        assert snap["gemini"]["configured"] is False

    def test_profiles_listed(self, launcher: Any) -> None:
        snap = launcher.snapshot()
        assert snap["profiles"][0]["name"] == "Dev"


class TestGeminiKeyHandling:
    def test_key_saved_but_never_echoed(self, launcher: Any) -> None:
        result = launcher.handle_save_gemini_key({"api_key": "AIza-secret"})
        assert result["ok"] is True
        assert "AIza-secret" not in str(result)  # write-only from the UI's view
        snap = launcher.snapshot()
        assert snap["gemini"]["configured"] is True
        # value retrievable only server-side
        assert launcher._services()["settings"].get_secret("gemini_api_key") == "AIza-secret"

    def test_empty_key_rejected(self, launcher: Any) -> None:
        result = launcher.handle_save_gemini_key({"api_key": "   "})
        assert result["ok"] is False

    def test_save_publishes_event(self, launcher: Any) -> None:
        received = []
        q = launcher.broker.subscribe()
        threading.Thread(target=lambda: received.append(q.get(timeout=2)), daemon=True).start()
        launcher.handle_save_gemini_key({"api_key": "k2"})
        assert received, "settings change must push an SSE event"


class TestKanbanMoves:
    def test_legal_move_persists_and_publishes(self, launcher: Any) -> None:
        app_id = launcher.snapshot()["kanban"][0]["id"]
        result = launcher.handle_move_card({"application_id": app_id, "to_status": "submitted"})
        assert result["ok"] is True
        snap = launcher.snapshot()
        assert snap["kanban"][0]["status"] == "submitted"

    def test_illegal_move_rejected_by_domain(self, launcher: Any) -> None:
        # discovered -> submitted is illegal; domain must refuse (no UI bypass)
        app = Application(
            profile_id="prof-1", entry_method=EntryMethod.ASSISTED, company="B", title="T"
        )  # starts DISCOVERED
        services = launcher._services()
        services["ledger"].create(app)
        services["store"].upsert("applications", app.id, app.model_dump(mode="json"))
        result = launcher.handle_move_card({"application_id": app.id[:8], "to_status": "submitted"})
        assert result["ok"] is False
        assert "illegal transition" in result["error"]

    def test_submitted_requires_evidence_even_from_kanban(self, launcher: Any) -> None:
        # A DISCOVERED record moved through legal path still needs evidence at SUBMITTED.
        app = Application(
            profile_id="prof-1", entry_method=EntryMethod.ASSISTED, company="C", title="T"
        )
        services = launcher._services()
        services["ledger"].create(app)
        services["store"].upsert("applications", app.id, app.model_dump(mode="json"))
        app_id = app.id[:8]
        ok1 = launcher.handle_move_card({"application_id": app_id, "to_status": "shortlisted"})
        ok2 = launcher.handle_move_card({"application_id": app_id, "to_status": "ready"})
        ok3 = launcher.handle_move_card({"application_id": app_id, "to_status": "drafted"})
        ok4 = launcher.handle_move_card({"application_id": app_id, "to_status": "review_required"})
        assert all(r["ok"] for r in (ok1, ok2, ok3, ok4))
        ok5 = launcher.handle_move_card({"application_id": app_id, "to_status": "submitted"})
        assert ok5["ok"] is True  # kanban supplies user-confirmation evidence automatically
        snap = launcher.snapshot()
        card = next(c for c in snap["kanban"] if c["id"] == app_id)
        assert card["status"] == "submitted"

    def test_unknown_application_rejected(self, launcher: Any) -> None:
        result = launcher.handle_move_card({"application_id": "zzzz", "to_status": "ready"})
        assert result["ok"] is False


class TestEventBroker:
    def test_publish_fans_out(self) -> None:
        broker = EventBroker()
        q1, q2 = broker.subscribe(), broker.subscribe()
        broker.publish("state_changed", {"x": 1})
        assert "state_changed" in q1.get_nowait()
        assert "state_changed" in q2.get_nowait()

    def test_slow_client_dropped_not_blocked(self) -> None:
        broker = EventBroker()
        broker.subscribe()
        for _ in range(300):  # overflow the queue
            broker.publish("e", {"i": _})
        assert broker.subscriber_count == 0  # slow subscriber removed
        q2 = broker.subscribe()
        broker.publish("e", {"i": 999})
        assert q2.get_nowait()  # healthy subscriber unaffected
