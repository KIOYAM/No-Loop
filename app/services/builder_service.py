"""Resume canvas service — bootstrap, save, AI propose, apply, export.

Thin orchestration over three pure modules:

- :mod:`app.services.builder_template` — bound skeleton, override diff, merge,
  HTML export (no I/O, unit tested).
- :mod:`app.services.builder_ai` — the propose-only AI contract and its
  grounding gate (no I/O, unit tested).
- :class:`app.services.resume_builder.ResumeAssembler` — the semantic doc, i.e.
  the same structure the rest of the app renders and scores.

Storage uses two JsonStore collections, same as every other feature:

``resume_templates``
    a reusable look: GrapesJS project + CSS + default section order.
``resume_variants``
    one per ``profile_id`` and optionally per ``profile_id:application_id``:
    project, CSS, human overrides (``{path: text}``) and an audit trail of
    applied suggestions.

Raw resume text is never stored here — only the assembled ``doc``, which the
user can see and edit, plus the overrides they authored.
"""

from __future__ import annotations

import base64
import time
from datetime import UTC, datetime
from typing import Any

from app.services.builder_ai import (
    SUGGEST_SYSTEM,
    build_prompt,
    local_suggestions,
    parse_suggestions,
    validate_suggestions,
)
from app.services.builder_template import (
    DEFAULT_RESUME_CSS,
    DEFAULT_SECTIONS,
    diff_overrides,
    html_export,
    merge_doc,
    render_skeleton,
    section_order,
    text_export,
)

__all__ = ["BuilderService", "BuilderError"]


class BuilderError(Exception):
    """User-facing failure (message is safe to show verbatim)."""


def _variant_key(profile_id: str, application_id: str | None) -> str:
    return f"{profile_id}:{application_id}" if application_id else profile_id


class BuilderService:
    """Everything the builder endpoint needs, in one place."""

    def __init__(self, store: Any, settings: Any) -> None:
        self._store = store
        self._settings = settings

    # -- context ----------------------------------------------------------

    def _profile_and_facts(self, profile_id: str) -> tuple[Any, list[Any]] | None:
        from app.domain.facts import ResumeFact
        from app.domain.profile import CandidateProfile

        raw = self._store.get("profiles", profile_id)
        if not raw:
            return None
        prof = CandidateProfile.model_validate(raw)
        facts = [
            ResumeFact.model_validate(f)
            for f in self._store.all("facts").values()
            if f.get("profile_id") == profile_id and f.get("state") == "confirmed"
        ]
        return prof, facts

    def _pending_facts(self, profile_id: str) -> int:
        return sum(
            1
            for f in self._store.all("facts").values()
            if f.get("profile_id") == profile_id and f.get("state") == "inferred"
        )

    def _kb_entries(self, profile_id: str) -> list[Any]:
        from app.domain.knowledge import KBEntry

        return [
            KBEntry.model_validate(e)
            for e in self._store.all("kb_entries").values()
            if e.get("profile_id") == profile_id
        ]

    def _application(self, application_id: str | None) -> dict[str, Any] | None:
        if not application_id:
            return None
        raw = self._store.get("applications", application_id)
        if raw:
            return dict(raw)
        # the UI shows truncated ids in places; fall back to a prefix match
        for key, value in self._store.all("applications").items():
            if key.startswith(application_id):
                return dict(value)
        return None

    def _jd_text(self, application: dict[str, Any] | None) -> str:
        if not application:
            return ""
        job_id = str(application.get("job_id") or "")
        if not job_id:
            return ""
        job = self._store.get("jobs", job_id) or next(
            (v for k, v in self._store.all("jobs").items() if k.startswith(job_id)),
            None,
        )
        return str((job or {}).get("description_text") or "")

    def _doc(self, profile_id: str) -> tuple[Any, Any, dict[str, Any]]:
        from app.services.resume_builder import ResumeAssembler

        loaded = self._profile_and_facts(profile_id)
        if loaded is None:
            raise BuilderError("profile not found")
        prof, facts = loaded
        assembler = ResumeAssembler(facts, prof)
        # Deliberately NO jd_text / KB selection here: the builder doc must be
        # identical on every load, or saved paths would drift under the user.
        # JD-aware content arrives as *suggestions*, which the human applies.
        return prof, assembler, assembler.build()

    def _variant(self, profile_id: str, application_id: str | None) -> dict[str, Any]:
        raw = self._store.get("resume_variants", _variant_key(profile_id, application_id))
        return dict(raw) if raw else {}

    def _template(self, template_id: str | None) -> dict[str, Any]:
        raw = self._store.get("resume_templates", template_id or "")
        return dict(raw) if raw else {}

    # -- read -------------------------------------------------------------

    def bootstrap(
        self,
        profile_id: str,
        application_id: str | None = None,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Everything the editor needs for one paint, in a single round trip."""
        from app.services.ai_registry import AIRegistry
        from app.services.resume_builder import ats_score

        _prof, assembler, doc = self._doc(profile_id)
        application = self._application(application_id)
        jd_text = self._jd_text(application)
        variant = self._variant(profile_id, application_id)
        template = self._template(variant.get("template_id"))
        overrides: dict[str, str] = dict(variant.get("overrides") or {})
        merged = merge_doc(doc, overrides)
        sections = list(variant.get("sections") or template.get("sections") or DEFAULT_SECTIONS)
        project = variant.get("project") if not refresh else None

        ai = AIRegistry(self._settings)
        active = ai.active_key()
        # Sections are whatever the canvas holds — including ones the user
        # added by hand — so the presence map must tolerate unknown names.
        present = {
            "header": merged.get("contact"),
            "summary": merged.get("summary"),
            "skills": merged.get("skills"),
            "experience": merged.get("experience"),
            "projects": merged.get("projects"),
            "education": merged.get("education"),
            "certifications": merged.get("certifications"),
        }
        return {
            "ok": True,
            "profile_id": profile_id,
            "application_id": application_id,
            "variant_key": _variant_key(profile_id, application_id),
            "doc": doc,
            "overrides": overrides,
            "override_count": len(overrides),
            "skeleton": render_skeleton(merged, sections),
            "project": project,
            "css": variant.get("css") or template.get("css") or DEFAULT_RESUME_CSS,
            "sections": sections,
            "structure": {name: bool(present.get(name)) for name in sections},
            "application": (
                {
                    "id": application.get("id"),
                    "company": application.get("company"),
                    "title": application.get("title"),
                    "status": application.get("status"),
                }
                if application
                else None
            ),
            "jd_text": jd_text,
            "ats_score": (
                round(ats_score(assembler.resume_text(merged), jd_text), 4)
                if jd_text.strip()
                else None
            ),
            "pending_facts": self._pending_facts(profile_id),
            "ai": {
                "active": active,
                "label": getattr(ai.resolve(), "name", active),
                "can_generate": active in ("gemini", "local"),
            },
            "template_id": variant.get("template_id"),
            "has_project": bool(project),
        }

    def list_variants(self, profile_id: str) -> dict[str, Any]:
        """Templates + variants for the pickers (structure only, no doc text)."""
        templates = [
            {
                "id": rec.get("id"),
                "name": rec.get("name"),
                "sections": rec.get("sections") or list(DEFAULT_SECTIONS),
                "updated_at": rec.get("updated_at"),
            }
            for rec in self._store.all("resume_templates").values()
        ]
        variants = []
        for key, rec in self._store.all("resume_variants").items():
            if not key.startswith(profile_id):
                continue
            application_id = key.split(":", 1)[1] if ":" in key else None
            application = self._application(application_id)
            variants.append(
                {
                    "key": key,
                    "application_id": application_id,
                    "company": (application or {}).get("company"),
                    "title": (application or {}).get("title"),
                    "override_count": len(rec.get("overrides") or {}),
                    "applied_count": len(rec.get("applied") or []),
                    "updated_at": rec.get("updated_at"),
                }
            )
        return {"ok": True, "templates": templates, "variants": variants}

    # -- write ------------------------------------------------------------

    def save_variant(self, body: dict[str, Any]) -> dict[str, Any]:
        """Persist canvas state; the server derives overrides from the diff."""
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            raise BuilderError("profile_id is required")
        application_id = str(body.get("application_id") or "").strip() or None
        markup = str(body.get("html") or "")
        _prof, _assembler, doc = self._doc(profile_id)

        overrides = diff_overrides(markup, doc) if markup else {}
        key = _variant_key(profile_id, application_id)
        variant = self._variant(profile_id, application_id)
        applied = list(variant.get("applied") or [])
        # an override that came back to the fact value is no longer an override
        applied = [a for a in applied if overrides.get(str(a.get("path") or "")) is not None]
        now = datetime.now(UTC).isoformat()
        variant.update(
            {
                "id": key,
                "profile_id": profile_id,
                "application_id": application_id,
                "project": body.get("project") or variant.get("project"),
                "html": markup,
                "css": str(body.get("css") or variant.get("css") or DEFAULT_RESUME_CSS),
                "sections": section_order(markup)
                or variant.get("sections")
                or list(DEFAULT_SECTIONS),
                "template_id": str(body.get("template_id") or variant.get("template_id") or "")
                or None,
                "overrides": overrides,
                "applied": applied,
                "updated_at": now,
            }
        )
        self._store.upsert("resume_variants", key, variant)
        return {
            "ok": True,
            "variant_key": key,
            "overrides": overrides,
            "override_count": len(overrides),
        }

    def save_template(self, body: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            raise BuilderError("profile_id is required")
        markup = str(body.get("html") or "")
        template_id = str(body.get("id") or "").strip() or f"tpl_{int(time.time() * 1000)}"
        now = datetime.now(UTC).isoformat()
        record = {
            "id": template_id,
            "profile_id": profile_id,
            "name": str(body.get("name") or "").strip() or "Untitled look",
            "project": body.get("project"),
            "css": str(body.get("css") or DEFAULT_RESUME_CSS),
            "sections": section_order(markup) or list(DEFAULT_SECTIONS),
            "created_at": (self._store.get("resume_templates", template_id) or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        self._store.upsert("resume_templates", template_id, record)
        return {
            "ok": True,
            "template": {k: record[k] for k in ("id", "name", "sections", "updated_at")},
        }

    # -- AI (propose only) --------------------------------------------------

    async def suggest_async(self, body: dict[str, Any]) -> dict[str, Any]:
        """One bounded call to the provider the user chose. Never writes."""
        from app.services.ai_registry import AIRegistry

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            raise BuilderError("profile_id is required")
        application_id = str(body.get("application_id") or "").strip() or None
        _prof, _assembler, doc = self._doc(profile_id)
        jd_text = str(body.get("jd_text") or "") or self._jd_text(self._application(application_id))
        focus = str(body.get("focus") or "")

        variant = self._variant(profile_id, application_id)
        merged = merge_doc(doc, variant.get("overrides") or {})
        tailoring = _assembler.tailoring_suggestions(jd_text, self._kb_entries(profile_id))
        fallback = local_suggestions(
            merged,
            jd_text=jd_text,
            tailoring=tailoring,
            pending_facts=self._pending_facts(profile_id),
        )

        registry = AIRegistry(self._settings)
        try:
            text, provider = await registry.complete_async(
                build_prompt(merged, jd_text=jd_text, focus=focus),
                system=SUGGEST_SYSTEM,
                max_tokens=900,
                temperature=0.0,
                json_mode=True,
                timeout_s=25.0,
            )
        except Exception as exc:  # noqa: BLE001 - honest, visible degradation
            return {
                "ok": True,
                "mode": "local",
                "provider": registry.active_key(),
                "suggestions": fallback,
                "dropped": 0,
                "note": f"AI unavailable ({exc.__class__.__name__}: {str(exc)[:160]}); "
                "showing local analysis.",
            }

        items, parse_error = parse_suggestions(text)
        if parse_error:
            return {
                "ok": True,
                "mode": "local",
                "provider": provider,
                "suggestions": fallback,
                "dropped": 0,
                "note": f"{parse_error}; showing local analysis.",
            }
        kept, dropped = validate_suggestions(items, merged, jd_text=jd_text)
        if not kept:
            # never leave the panel empty-handed — and say so honestly
            return {
                "ok": True,
                "mode": "local",
                "provider": provider,
                "suggestions": fallback,
                "dropped": dropped,
                "note": (
                    f"Every model suggestion was rejected by the grounding gate "
                    f"({dropped} dropped); showing local analysis instead."
                    if dropped
                    else "Model returned nothing actionable; showing local analysis."
                ),
            }
        return {
            "ok": True,
            "mode": "ai",
            "provider": provider,
            "suggestions": kept,
            "dropped": dropped,
            "offered": len(items),
        }

    def apply_suggestion(self, body: dict[str, Any]) -> dict[str, Any]:
        """Human clicks Apply -> the text becomes an override + audit record."""
        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            raise BuilderError("profile_id is required")
        application_id = str(body.get("application_id") or "").strip() or None
        path = str(body.get("path") or "").strip()
        proposed = str(body.get("proposed") or "")
        if not path:
            raise BuilderError("path is required")
        if not proposed.strip():
            raise BuilderError("nothing to apply (proposed text is empty)")

        _prof, _assembler, _doc = self._doc(profile_id)
        variant = self._variant(profile_id, application_id)
        overrides = dict(variant.get("overrides") or {})
        overrides[path] = proposed
        applied = list(variant.get("applied") or [])
        applied.append(
            {
                "path": path,
                "proposed": proposed[:600],
                "reason": str(body.get("reason") or "")[:400],
                "provider": str(body.get("provider") or ""),
                "at": datetime.now(UTC).isoformat(),
            }
        )
        variant.update(
            {
                "id": _variant_key(profile_id, application_id),
                "profile_id": profile_id,
                "application_id": application_id,
                "overrides": overrides,
                "applied": applied[-50:],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        key = _variant_key(profile_id, application_id)
        self._store.upsert("resume_variants", key, variant)
        return {
            "ok": True,
            "variant_key": key,
            "path": path,
            "overrides": overrides,
            "override_count": len(overrides),
            "applied_count": len(applied),
        }

    # -- export -----------------------------------------------------------

    def export(self, body: dict[str, Any]) -> dict[str, Any]:
        """HTML from the canvas; PDF/DOCX/text from the merged doc (ADR-7)."""
        from app.services.renderer import RenderError, render_resume_docx, render_resume_pdf

        profile_id = str(body.get("profile_id") or "").strip()
        if not profile_id:
            raise BuilderError("profile_id is required")
        application_id = str(body.get("application_id") or "").strip() or None
        fmt = str(body.get("format") or "html").lower()
        if fmt not in ("html", "pdf", "docx", "text"):
            raise BuilderError("format must be html, pdf, docx or text")

        _prof, assembler, doc = self._doc(profile_id)
        variant = self._variant(profile_id, application_id)
        merged = merge_doc(doc, variant.get("overrides") or {})
        application = self._application(application_id)
        jd_text = self._jd_text(application)
        name = str((merged.get("contact") or {}).get("name") or "resume")
        base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "resume"
        suffix = f"-{application_id[:8]}" if application_id else ""

        score = None
        if jd_text.strip():
            from app.services.resume_builder import ats_score

            score = round(ats_score(assembler.resume_text(merged), jd_text), 4)

        saved_sections = variant.get("sections")
        sections = saved_sections if isinstance(saved_sections, list) and saved_sections else None

        if fmt == "html":
            markup = str(body.get("html") or variant.get("html") or "")
            css = str(body.get("css") or variant.get("css") or DEFAULT_RESUME_CSS)
            payload = html_export(
                markup or render_skeleton(merged, sections), css, title=name
            ).encode("utf-8")
            mime = "text/html; charset=utf-8"
        elif fmt == "text":
            payload = text_export(merged, sections).encode("utf-8")
            mime = "text/plain; charset=utf-8"
        elif fmt == "docx":
            try:
                payload = render_resume_docx(merged)
            except RenderError as exc:
                raise BuilderError(str(exc)) from exc
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            try:
                payload = render_resume_pdf(merged)
            except RenderError as exc:
                raise BuilderError(str(exc)) from exc
            mime = "application/pdf"

        extension = "txt" if fmt == "text" else fmt
        return {
            "ok": True,
            "format": fmt,
            "mime": mime,
            "filename": f"{base}{suffix}.{extension}",
            "content_base64": base64.b64encode(payload).decode("ascii"),
            "bytes": len(payload),
            "ats_score": score,
        }
