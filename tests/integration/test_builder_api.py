"""Integration tests for the resume builder API (`No_Loop_docs/RESUME_BUILDER_PLAN.md`).

Dispatched through the real route tables (`_JSON_GET` / `_JSON_POST`), no
sockets. The contract under test: the canvas round-trips through binding paths,
the server — not the browser — decides what counts as an override, AI is
propose-only, and every export is produced from one merged document.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.domain.facts import FactProvenance, FactState, ResumeFact, SkillClaim
from app.ui import server as ui_server
from app.ui.server import UILauncher

JD = (
    "Senior Backend Engineer. You will build payments services in Go and Kafka, "
    "own SLAs, and mentor engineers. Terraform experience is required."
)


def _fact(
    field_class: str,
    value: Any,
    *,
    skill: str | None = None,
    state: FactState = FactState.CONFIRMED,
    user_entry: bool = True,
    confidence: float = 1.0,
) -> ResumeFact:
    return ResumeFact(
        profile_id="p1",
        field_class=field_class,
        value=value,
        skill=SkillClaim(name=skill) if skill else None,
        confidence=confidence,
        state=state,
        provenance=FactProvenance(
            document_id=None if user_entry else "doc-fixture-1",
            user_entry=user_entry,
        ),
    )


@pytest.fixture()
def launcher(tmp_path: Any) -> UILauncher:
    data = tmp_path / "api-data"
    data.mkdir()
    ln = UILauncher(data_dir=str(data))
    services = ln._services()
    store = services["store"]

    store.upsert(
        "profiles",
        "p1",
        {
            "id": "p1",
            "name": "Ada Lovelace",
            "contact_email": "ada@example.com",
            "contact_phone": "+44 20 7946 0000",
            "location": "London, UK",
        },
    )
    facts = [
        _fact("skill", None, skill="Python"),
        _fact("skill", None, skill="Go"),
        _fact("employer", "Acme"),
        _fact("title", "Backend Engineer"),
        _fact("date_range", "2021 - Present"),
        _fact("experience_bullet", "Worked on payments"),
        _fact("degree", "BSc Computer Science"),
        _fact("education", "UCL"),
        _fact("certification", "AWS Solutions Architect"),
        _fact("project", "Ledger"),
        # still inferred: the canvas must never show it
        _fact(
            "title", "Unconfirmed role", state=FactState.INFERRED, user_entry=False, confidence=0.6
        ),
    ]
    for fact in facts:
        store.upsert("facts", fact.id, fact.model_dump(mode="json"))

    store.upsert(
        "jobs", "j1", {"id": "j1", "title": "Senior Backend Engineer", "description_text": JD}
    )
    app = Application(
        profile_id="p1",
        entry_method=EntryMethod.MANUAL,
        company="Acme",
        title="Senior Backend Engineer",
        submission_evidence={"method": "user_assertion"},
        status=ApplicationStatus.SUBMITTED,
        job_id="j1",
    )
    services["ledger"].create(app)
    store.upsert("applications", app.id, app.model_dump(mode="json"))
    ln._cache = services
    ln.builder_application_id = app.id  # type: ignore[attr-defined]
    return ln


def _get(launcher: UILauncher, path: str) -> Any:
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


def _bootstrap(launcher: UILauncher, application_id: str | None = None) -> dict[str, Any]:
    path = "/api/builder/bootstrap?profile_id=p1"
    if application_id:
        path += f"&application_id={application_id}"
    return _get(launcher, path)


class TestBootstrap:
    def test_returns_a_bound_skeleton_of_confirmed_facts(self, launcher: UILauncher) -> None:
        boot = _bootstrap(launcher)
        assert boot["ok"] is True
        skeleton = boot["skeleton"]
        assert 'data-nl-path="contact.name">Ada Lovelace<' in skeleton
        assert 'data-nl-path="experience[0].bullets[0]">Worked on payments<' in skeleton
        assert 'data-nl-path="skills[1]">Go<' in skeleton
        assert 'data-nl-path="certifications[0]">AWS Solutions Architect<' in skeleton
        # unconfirmed facts never reach the canvas
        assert "Unconfirmed role" not in skeleton
        assert boot["structure"]["experience"] is True
        assert boot["pending_facts"] == 1

    def test_reports_the_ai_the_user_chose_without_pretending(self, launcher: UILauncher) -> None:
        ai = _bootstrap(launcher)["ai"]
        assert ai["active"] == "rule"  # no key in this fixture
        assert ai["can_generate"] is False

    def test_scopes_the_variant_to_the_application_and_reads_its_jd(
        self, launcher: UILauncher
    ) -> None:
        app_id = launcher.builder_application_id  # type: ignore[attr-defined]
        boot = _bootstrap(launcher, application_id=app_id)
        assert boot["variant_key"] == f"p1:{app_id}"
        assert boot["application"]["company"] == "Acme"
        assert "Terraform" in boot["jd_text"]
        assert boot["ats_score"] is not None and 0.0 <= boot["ats_score"] <= 1.0

    def test_missing_profile_is_an_honest_error(self, launcher: UILauncher) -> None:
        assert _get(launcher, "/api/builder/bootstrap?profile_id=nope") == {
            "ok": False,
            "error": "profile not found",
        }
        assert _get(launcher, "/api/builder/bootstrap")["ok"] is False


class TestSaveVariant:
    def test_only_paths_the_human_changed_become_overrides(self, launcher: UILauncher) -> None:
        skeleton = _bootstrap(launcher)["skeleton"]
        edited = skeleton.replace("Worked on payments", "Owned the payments API migration to Kafka")
        assert edited != skeleton

        saved = _post(
            launcher, "/api/builder/variant", {"profile_id": "p1", "html": edited, "css": "body{}"}
        )
        assert saved["ok"] is True
        assert saved["override_count"] == 1
        assert saved["overrides"] == {
            "experience[0].bullets[0]": "Owned the payments API migration to Kafka"
        }

        # ...and the untouched facts stayed facts, not user text
        reloaded = _bootstrap(launcher)
        assert reloaded["override_count"] == 1
        assert "Owned the payments API migration to Kafka" in reloaded["skeleton"]

    def test_identical_text_is_not_recorded_as_an_override(self, launcher: UILauncher) -> None:
        skeleton = _bootstrap(launcher)["skeleton"]
        saved = _post(launcher, "/api/builder/variant", {"profile_id": "p1", "html": skeleton})
        assert saved["ok"] is True
        assert saved["override_count"] == 0
        assert saved["overrides"] == {}

    def test_section_order_is_read_from_the_canvas(self, launcher: UILauncher) -> None:
        skeleton = _bootstrap(launcher)["skeleton"]
        moved = (
            skeleton.replace('data-nl-section="experience"', "TMP")
            .replace('data-nl-section="skills"', 'data-nl-section="experience"')
            .replace("TMP", 'data-nl-section="skills"')
        )
        _post(launcher, "/api/builder/variant", {"profile_id": "p1", "html": moved})
        reloaded = _bootstrap(launcher)
        assert reloaded["sections"][:3] == ["header", "experience", "skills"]

    def test_saving_requires_a_profile(self, launcher: UILauncher) -> None:
        assert _post(launcher, "/api/builder/variant", {"html": "<div/>"})["ok"] is False

    def test_a_hand_added_section_never_breaks_the_boot(self, launcher: UILauncher) -> None:
        """A section the doc knows nothing about is reported, not crashed on."""
        skeleton = _bootstrap(launcher)["skeleton"]
        custom = (
            skeleton[: skeleton.rfind("</div>")]
            + '<section class="nl-section" data-nl-section="awards">'
            + '<h2 class="nl-h2">Awards</h2><p>Young Engineer of the Year</p></section>'
            + "</div>"
        )
        _post(launcher, "/api/builder/variant", {"profile_id": "p1", "html": custom})
        reloaded = _bootstrap(launcher)
        assert reloaded["ok"] is True
        assert "awards" in reloaded["sections"]
        assert reloaded["structure"]["awards"] is False
        # ...and the doc-backed sections are still all there
        assert reloaded["structure"]["experience"] is True


class TestApplyIsHumanInTheLoop:
    def test_applied_suggestion_becomes_an_override_with_an_audit_trail(
        self, launcher: UILauncher
    ) -> None:
        applied = _post(
            launcher,
            "/api/builder/apply",
            {
                "profile_id": "p1",
                "path": "summary",
                "proposed": "Backend engineer with payments experience.",
                "reason": "Positions the profile for the target role.",
                "provider": "rule",
            },
        )
        assert applied["ok"] is True
        assert applied["overrides"]["summary"] == "Backend engineer with payments experience."

        boot = _bootstrap(launcher)
        assert boot["override_count"] == 1
        assert "Backend engineer with payments experience." in boot["skeleton"]

        listed = _get(launcher, "/api/builder/list?profile_id=p1")
        assert listed["variants"][0]["applied_count"] == 1
        assert listed["variants"][0]["override_count"] == 1

    def test_applying_empty_text_is_refused(self, launcher: UILauncher) -> None:
        assert (
            _post(launcher, "/api/builder/apply", {"profile_id": "p1", "path": "summary"})["ok"]
            is False
        )
        assert (
            _post(launcher, "/api/builder/apply", {"profile_id": "p1", "proposed": "x"})["ok"]
            is False
        )


class TestSuggestIsProposeOnly:
    def test_without_a_key_the_panel_still_fills_from_local_analysis(
        self, launcher: UILauncher
    ) -> None:
        result = _post(launcher, "/api/builder/suggest", {"profile_id": "p1", "jd_text": JD})
        assert result["ok"] is True
        assert result["mode"] == "local"
        assert result["provider"] == "rule"
        assert result["suggestions"], "the panel must never be dead without a key"
        assert all("path" in s and "reason" in s for s in result["suggestions"])
        reasons = " ".join(s["reason"] for s in result["suggestions"])
        assert "do NOT claim" in reasons
        # propose-only: nothing was written to the variant
        assert _bootstrap(launcher)["override_count"] == 0

    def test_suggest_requires_a_profile(self, launcher: UILauncher) -> None:
        assert _post(launcher, "/api/builder/suggest", {"profile_id": "nope"})["ok"] is False


class TestExports:
    @pytest.mark.parametrize("fmt", ["html", "text", "pdf", "docx"])
    def test_every_export_is_built_from_the_merged_document(
        self, launcher: UILauncher, fmt: str
    ) -> None:
        _post(
            launcher,
            "/api/builder/apply",
            {
                "profile_id": "p1",
                "path": "summary",
                "proposed": "Payments-focused backend engineer.",
                "reason": "test",
                "provider": "rule",
            },
        )
        result = _post(launcher, "/api/builder/export", {"profile_id": "p1", "format": fmt})
        assert result["ok"] is True, result
        assert result["bytes"] > 0
        assert result["filename"].endswith(".txt" if fmt == "text" else f".{fmt}")
        payload = base64.b64decode(result["content_base64"])
        if fmt == "pdf":
            assert payload.startswith(b"%PDF")
        elif fmt == "docx":
            assert payload.startswith(b"PK")  # zipped OOXML
        else:
            # the human's text survives into the formats that stay readable
            assert "Payments-focused backend engineer." in payload.decode("utf-8")

    def test_html_export_is_a_standalone_page(self, launcher: UILauncher) -> None:
        skeleton = _bootstrap(launcher)["skeleton"]
        result = _post(
            launcher,
            "/api/builder/export",
            {"profile_id": "p1", "format": "html", "html": skeleton, "css": ".nl-name{color:red}"},
        )
        page = base64.b64decode(result["content_base64"]).decode("utf-8")
        assert page.startswith("<!doctype html>")
        assert ".nl-name{color:red}" in page
        assert 'data-nl-path="contact.name"' in page

    def test_unknown_format_is_refused(self, launcher: UILauncher) -> None:
        assert (
            _post(launcher, "/api/builder/export", {"profile_id": "p1", "format": "rtf"})["ok"]
            is False
        )


class TestVariantsArePerApplication:
    def test_edits_for_one_job_do_not_leak_into_the_profile_default(
        self, launcher: UILauncher
    ) -> None:
        app_id = launcher.builder_application_id  # type: ignore[attr-defined]
        _post(
            launcher,
            "/api/builder/apply",
            {
                "profile_id": "p1",
                "application_id": app_id,
                "path": "summary",
                "proposed": "Tailored for Acme.",
                "reason": "company fit",
                "provider": "gemini-2.5-flash",
            },
        )
        assert _bootstrap(launcher)["override_count"] == 0  # default variant untouched
        scoped = _bootstrap(launcher, application_id=app_id)
        assert scoped["override_count"] == 1
        assert "Tailored for Acme." in scoped["skeleton"]

        listed = _get(launcher, "/api/builder/list?profile_id=p1")
        assert len(listed["variants"]) == 1
        assert listed["variants"][0]["application_id"] == app_id
        assert listed["variants"][0]["company"] == "Acme"
