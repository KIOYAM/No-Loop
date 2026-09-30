"""Annotated resume-import pipeline (LOOP-5 + user request 2026-09-29).

Runs the whole import as an observable sequence of stages so the browser can
render a live, animated timeline over SSE — no polling, no spinner-only UX.

Design goals, in priority order:

1. **Speed** — the deterministic pass finishes in single-digit milliseconds and
   the UI already has facts to review before any network call happens. The
   optional AI pass is ONE request: trimmed input, temperature 0, small output
   budget, hard timeout, and it can never block or fail the import.
2. **Quality** — AI output is merged as *inferred* facts with sub-1.0
   confidence and a ``llm:<provider>`` extraction rule; the user still confirms
   (S2 anti-fabrication).
3. **Honesty** — every stage reports ``done | skipped | failed`` with a human
   reason (R-TRUTH-3); a missing key is a visible "skipped", never a silent one.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.adapters.profile_autofill import suggest_profile_fields
from app.domain.facts import FactProvenance, ResumeFact, SkillClaim
from app.services.ai_registry import AIRegistry
from app.services.profile_service import ResumeService

__all__ = ["STAGE_ORDER", "STAGE_META", "PipelineResult", "ResumePipeline"]

#: Ordered stage ids with their progress weight (0-100) for the progress bar.
STAGE_ORDER: tuple[tuple[str, int], ...] = (
    ("upload", 8),
    ("validate", 16),
    ("dedupe", 24),
    ("detect", 32),
    ("extract", 46),
    ("parse", 58),
    ("persist", 66),
    ("autofill", 76),
    ("ai", 90),
    ("profile", 96),
    ("done", 100),
)

STAGE_META: dict[str, dict[str, str]] = {
    "upload": {"label": "Receiving file", "detail": "Reading the upload into memory"},
    "validate": {"label": "Validating", "detail": "Type, size and integrity checks"},
    "dedupe": {"label": "Duplicate check", "detail": "Content hash vs your import history"},
    "detect": {"label": "Format detection", "detail": "Extension, magic bytes, encryption"},
    "extract": {"label": "Text extraction", "detail": "PDF / DOCX / TXT → plain text"},
    "parse": {"label": "Fact extraction", "detail": "Deterministic rules over the text"},
    "persist": {"label": "Saving", "detail": "Version history + fact ledger"},
    "autofill": {"label": "Profile autofill", "detail": "Filling empty profile fields"},
    "ai": {"label": "AI enhancement", "detail": "Optional LLM pass for roles & education"},
    "profile": {"label": "Updating profile", "detail": "Merging suggestions into your profile"},
    "done": {"label": "Complete", "detail": "Everything stored locally"},
}

_PROGRESS = dict(STAGE_ORDER)
_AI_INPUT_HEAD = 9000
_AI_INPUT_TAIL = 3000
_AI_TIMEOUT_S = 15.0
_AI_MAX_TOKENS = 700

_AI_SYSTEM = (
    "You are a resume parser. Output JSON only — no prose, no markdown fences. "
    "Never write anything that is not literally present in the given text."
)
_AI_PROMPT = (
    "Extract from the resume below and return ONE JSON object with these keys:\n"
    '  "job_titles": [string], "employers": [string], "education": [string],\n'
    '  "certifications": [string], "languages": [string], "skills": [string],\n'
    '  "location": string, "summary": string (max 400 chars)\n'
    "Use only information literally present in the text; use [] when empty.\n\n"
    "RESUME TEXT:\n{chunk}"
)

#: AI payload key → fact field_class (skills need a SkillClaim instead).
_FIELD_CLASS = {
    "job_titles": "title",
    "employers": "employer",
    "education": "education",
    "certifications": "certification",
    "languages": "language",
    "summary": "summary",
    "location": "location",
}

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass
class PipelineResult:
    """Everything the UI needs to finish the animation and show a summary."""

    ok: bool
    profile_id: str
    filename: str
    version: int | None = None
    facts_created: int = 0
    ai_facts_created: int = 0
    autofill: dict[str, Any] = field(default_factory=dict)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_reason: str | None = None
    user_action: str | None = None
    ai_provider: str | None = None
    duration_ms: int = 0
    #: MASTER_SPEC §3 field-group coverage of the deterministic pass.
    coverage: dict[str, Any] = field(default_factory=dict)
    #: "what an ATS sees" score + flags (parseability report).
    parseability: dict[str, Any] = field(default_factory=dict)
    document_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile_id": self.profile_id,
            "filename": self.filename,
            "version": self.version,
            "facts_created": self.facts_created,
            "ai_facts_created": self.ai_facts_created,
            "autofill": self.autofill,
            "suggestions": self.suggestions,
            "stages": self.stages,
            "warnings": self.warnings,
            "error_reason": self.error_reason,
            "user_action": self.user_action,
            "ai_provider": self.ai_provider,
            "duration_ms": self.duration_ms,
            "coverage": self.coverage,
            "parseability": self.parseability,
            "document_id": self.document_id,
        }


def _run_async(coro: Any) -> Any:
    """``asyncio.run`` outside a loop; a worker thread inside one (test-friendly)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _trim(text: str) -> str:
    """One-request budget: keep the head (identity/skills) and tail (recent roles)."""
    if len(text) <= _AI_INPUT_HEAD + _AI_INPUT_TAIL:
        return text
    return text[:_AI_INPUT_HEAD] + "\n...\n" + text[-_AI_INPUT_TAIL:]


#: Sections the AI pass must see even when they sit in the trimmed middle.
_AI_PRIORITY = (
    "experience",
    "skills",
    "education",
    "certifications",
    "projects",
    "achievements",
    "summary",
)


def _select_window(text: str, sections: list[dict[str, Any]] | None = None) -> str:
    """Build the model input, *including the middle of long resumes*.

    The old head-9k/tail-3k trim silently hid whatever landed in the middle —
    for long resumes that is usually the experience section, i.e. the fields
    the AI pass exists to recover. Sections are pulled from the region that
    neither the head nor the tail already covers, within the same budget.
    """
    budget = _AI_INPUT_HEAD + _AI_INPUT_TAIL
    if len(text) <= budget or not sections:
        return _trim(text)
    head = text[:_AI_INPUT_HEAD]
    tail = text[-_AI_INPUT_TAIL:]
    head_end = len(head)
    tail_start = len(text) - len(tail)
    room = max(0, budget - len(head) - len(tail) - 32)
    by_name = {str(s.get("name")): s for s in sections}
    pieces: list[str] = []
    used = 0
    for name in _AI_PRIORITY:
        section = by_name.get(name)
        if not section:
            continue
        try:
            start = max(int(section.get("body_start", 0)), head_end)
            end = min(int(section.get("end", 0)), tail_start)
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        chunk = text[start:end].strip()
        if not chunk:
            continue
        if used + len(chunk) + 2 > room:
            chunk = chunk[: max(0, room - used - 2)]
            if len(chunk) < 80:
                break
            pieces.append(chunk)
            used += len(chunk)
            break
        pieces.append(chunk)
        used += len(chunk) + 2
    if not pieces:
        return _trim(text)
    return f"{head}\n...\n" + "\n\n".join(pieces) + "\n...\n" + tail


class ResumePipeline:
    """Observable import: deterministic first, optional AI second, always honest."""

    def __init__(
        self,
        store: Any,
        settings: Any,
        registry: AIRegistry | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.registry = registry or AIRegistry(settings)
        self.service = ResumeService(store, settings)

    # -- stage bookkeeping -------------------------------------------------

    def _blank_stages(self) -> list[dict[str, Any]]:
        return [
            {
                "id": sid,
                "label": STAGE_META[sid]["label"],
                "description": STAGE_META[sid]["detail"],
                "status": "pending",
                "detail": "",
                "ms": None,
                "progress": weight,
            }
            for sid, weight in STAGE_ORDER
        ]

    @staticmethod
    def _emit(
        emit: ProgressCallback | None,
        *,
        job_id: str,
        stage: str,
        status: str,
        detail: str,
        elapsed_ms: int,
        profile_id: str,
    ) -> None:
        if emit is None:
            return
        emit(
            {
                "kind": "resume",
                "job_id": job_id,
                "profile_id": profile_id,
                "stage": stage,
                "label": STAGE_META.get(stage, {}).get("label", stage),
                "status": status,
                "detail": detail,
                "progress": _PROGRESS.get(stage, 0),
                "elapsed_ms": elapsed_ms,
            }
        )

    # -- the run -----------------------------------------------------------

    def run(
        self,
        *,
        profile_id: str,
        filename: str,
        data: bytes,
        use_ai: bool = True,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        job = job_id or f"import-{int(time.time() * 1000)}"
        started = time.perf_counter()
        stages = self._blank_stages()
        index = {s["id"]: s for s in stages}
        marks: dict[str, float] = {}
        warnings: list[str] = []

        def begin(stage_id: str) -> None:
            marks[stage_id] = time.perf_counter()
            index[stage_id]["status"] = "running"
            self._emit(
                on_progress,
                job_id=job,
                stage=stage_id,
                status="running",
                detail=STAGE_META[stage_id]["detail"],
                elapsed_ms=0,
                profile_id=profile_id,
            )

        def finish(stage_id: str, status: str, detail: str) -> None:
            elapsed = int((time.perf_counter() - marks.get(stage_id, time.perf_counter())) * 1000)
            entry = index[stage_id]
            entry["status"] = status
            entry["detail"] = detail
            entry["ms"] = elapsed
            self._emit(
                on_progress,
                job_id=job,
                stage=stage_id,
                status=status,
                detail=detail,
                elapsed_ms=elapsed,
                profile_id=profile_id,
            )

        def fail(stage_id: str, reason: str, action: str | None = None) -> PipelineResult:
            finish(stage_id, "failed", reason)
            for entry in stages:  # anything still pending is explicitly skipped
                if entry["status"] == "pending":
                    entry["status"] = "skipped"
                    entry["detail"] = "not reached"
            index["done"]["status"] = "failed"
            index["done"]["detail"] = reason
            return PipelineResult(
                ok=False,
                profile_id=profile_id,
                filename=filename,
                stages=stages,
                warnings=warnings,
                error_reason=reason,
                user_action=action,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        # 1. upload --------------------------------------------------------
        begin("upload")
        if not data:
            return fail("upload", "file is empty", "Choose a file and retry.")
        if len(data) > 10 * 1024 * 1024:
            return fail("upload", "file exceeds the 10 MB limit", "Split or compress the file.")
        finish("upload", "done", f"{len(data) // 1024} KB · {filename}")

        # 2-7. deterministic import (stages reported by the service) -------
        def service_stage(stage_id: str, status: str, detail: str) -> None:
            if status == "running":
                begin(stage_id)
            else:
                finish(stage_id, status, detail)

        try:
            outcome = self.service.import_resume(
                profile_id=profile_id,
                filename=filename,
                data=data,
                on_stage=service_stage,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced honestly to the UI
            return fail("parse", f"import crashed: {exc.__class__.__name__}", "Retry the import.")

        if not outcome.ok:
            failed_stage = next(
                (s["id"] for s in reversed(stages) if s["status"] == "running"), "validate"
            )
            return fail(
                failed_stage,
                outcome.error_reason or "import failed",
                outcome.user_action,
            )
        if outcome.duplicate_of_version is not None:
            warnings.append(f"identical to version {outcome.duplicate_of_version}")
        warnings.extend(outcome.warnings)

        # The service can return before extract/parse/persist (duplicate import).
        # A timeline must never be left showing a stuck "pending" step, so any
        # stage the service did not reach is closed out with a visible reason.
        if outcome.duplicate_of_version is not None:
            early_reason = f"skipped — identical to version {outcome.duplicate_of_version}"
        else:
            early_reason = "not reached"
        for entry in stages:
            if entry["id"] == "autofill":
                break  # only the service-owned stages (upload … persist) are closed here
            if entry["status"] == "pending":
                entry["status"] = "skipped"
                entry["detail"] = early_reason
                self._emit(
                    on_progress,
                    job_id=job,
                    stage=entry["id"],
                    status="skipped",
                    detail=early_reason,
                    elapsed_ms=0,
                    profile_id=profile_id,
                )

        # 8. deterministic profile autofill --------------------------------
        begin("autofill")
        text = outcome.text or ""
        auto = suggest_profile_fields(text)
        warnings.extend(auto.warnings)
        if text.strip():
            finish(
                "autofill",
                "done",
                f"{auto.count} field suggestions · {len(auto.warnings)} need your attention",
            )
        else:
            # a duplicate import returns no text — do not claim work was done
            finish("autofill", "skipped", "no text to work with (duplicate import)")

        # 9. optional AI enhancement (never blocks the import) --------------
        begin("ai")
        ai_facts: list[ResumeFact] = []
        ai_provider: str | None = None
        if not use_ai:
            finish("ai", "skipped", "AI pass turned off for this import")
        else:
            ai_facts, ai_provider, ai_note, ai_status = self._ai_enhance(
                profile_id=profile_id,
                text=text,
                filename=filename,
                sections=list(outcome.structure.get("sections", []) or []),
            )
            for fact in ai_facts:
                self.store.upsert("facts", fact.id, fact.model_dump(mode="json"))
            finish("ai", ai_status, ai_note)

        # 10. merge suggestions into the profile (fill-only) ---------------
        begin("profile")
        applied = self._apply_autofill(
            profile_id, auto.applied(_profile_fields(self.store, profile_id))
        )
        if applied:
            finish("profile", "done", f"{len(applied)} profile field(s) filled")
        elif text.strip():
            finish("profile", "done", "profile already complete")
        else:
            finish("profile", "skipped", "no suggestions to merge (duplicate import)")

        # 11. done ----------------------------------------------------------
        begin("done")
        duration = int((time.perf_counter() - started) * 1000)
        finish(
            "done",
            "done",
            f"{outcome.facts_created} rule facts + {len(ai_facts)} AI facts in {duration} ms",
        )

        return PipelineResult(
            ok=True,
            profile_id=profile_id,
            filename=filename,
            version=outcome.version,
            facts_created=outcome.facts_created,
            ai_facts_created=len(ai_facts),
            autofill=applied,
            suggestions=auto.to_dict()["suggestions"],
            stages=stages,
            warnings=warnings,
            ai_provider=ai_provider,
            duration_ms=duration,
            coverage=dict(outcome.coverage or {}),
            parseability=dict(outcome.parseability or {}),
            document_id=outcome.document_id,
        )

    # -- AI pass -----------------------------------------------------------

    def _ai_enhance(
        self,
        *,
        profile_id: str,
        text: str,
        filename: str,
        sections: list[dict[str, Any]] | None = None,
    ) -> tuple[list[ResumeFact], str | None, str, str]:
        """One bounded request. Returns (facts, provider, note, status)."""
        if len(text) < 120:
            return [], None, "text too short for an AI pass", "skipped"
        prompt = _AI_PROMPT.format(chunk=_select_window(text, sections))
        try:
            raw, provider = _run_async(
                self.registry.complete_async(
                    prompt,
                    system=_AI_SYSTEM,
                    max_tokens=_AI_MAX_TOKENS,
                    temperature=0.0,
                    json_mode=True,
                    timeout_s=_AI_TIMEOUT_S,
                )
            )
        except Exception as exc:  # noqa: BLE001 - degrade visibly, never fail the import
            return [], None, f"AI unavailable — kept rule-based facts ({exc})", "skipped"

        parsed = _load_json(raw)
        if parsed is None:
            return [], provider, "AI returned unparseable JSON — kept rule-based facts", "skipped"

        rule_values = _rule_value_index(self.store, profile_id, filename)
        facts = _facts_from_ai(
            profile_id,
            parsed,
            document_id=filename,
            provider=provider,
            source_text=text,
            rule_values=rule_values,
        )
        fields = sum(1 for f in facts if f.field_class != "skill")
        skills = sum(1 for f in facts if f.field_class == "skill")
        if not facts:
            return (
                [],
                provider,
                "AI found nothing new (or nothing it could ground in the text)",
                "skipped",
            )
        return (
            facts,
            provider,
            f"+{fields} profile facts, +{skills} skills from {provider} (grounded)",
            "done",
        )

    def _apply_autofill(self, profile_id: str, applied: dict[str, Any]) -> dict[str, Any]:
        """Persist fill-only suggestions onto the candidate profile.

        Every field is merged one at a time through pydantic validation so a
        single bad heuristic can never reject the whole update, and an
        already-populated field is never overwritten.
        """
        data = self.store.get("profiles", profile_id)
        if not data:
            return {}
        from pydantic import ValidationError

        from app.domain.profile import CandidateProfile

        profile = CandidateProfile.model_validate(data)
        merged = dict(data)
        saved: dict[str, Any] = {}

        for key, value in applied.items():
            if key not in _PROFILE_FIELDS:
                continue
            if key == "links":
                value = {**profile.links, **value}
            trial = {**merged, key: value}
            try:
                CandidateProfile.model_validate(trial)
            except ValidationError:
                continue
            merged = trial
            saved[key] = value

        parked = {
            key: applied[key] for key in ("summary", *_SUGGESTION_LIST_FIELDS) if key in applied
        }
        if parked:
            extra = dict(merged.get("extra") or {})
            changed = False
            for key, value in parked.items():
                if key == "summary":
                    if not extra.get("summary"):
                        extra["summary"] = value
                        changed = True
                else:
                    bucket = extra.get("resume_suggestions")
                    if not isinstance(bucket, dict) or not bucket.get(key):
                        extra["resume_suggestions"] = {**(bucket or {}), key: value}
                        changed = True
            if changed:
                trial = {**merged, "extra": extra}
                try:
                    CandidateProfile.model_validate(trial)
                except ValidationError:
                    pass
                else:
                    merged = trial
                    saved["extra"] = parked

        if not saved:
            return {}
        updated = CandidateProfile.model_validate(merged)
        self.store.upsert("profiles", profile.id, updated.model_dump(mode="json"))
        return saved


_PROFILE_FIELDS = frozenset(
    {
        "contact_name",
        "contact_email",
        "contact_phone",
        "location",
        "links",
        "summary",
    }
)

#: Suggestions that are not scalar profile fields → parked in profile.extra.
_SUGGESTION_LIST_FIELDS = frozenset({"education", "job_titles", "employers"})


def _profile_fields(store: Any, profile_id: str) -> dict[str, Any]:
    return dict(store.get("profiles", profile_id) or {})


def _load_json(raw: str) -> dict[str, Any] | None:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lstrip().lower().startswith("json"):
            candidate = candidate.lstrip()[4:]
    try:
        data = json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(candidate[start : end + 1])
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def _normalize(value: str) -> str:
    return " ".join(str(value).lower().split())


def _grounded(value: str, source_text: str, kind: str = "value") -> bool:
    """Anti-fabrication: the claim must literally occur in the source text.

    Values may be *matched*, never paraphrased — an LLM that rewords a bullet
    into something the resume does not say is exactly the failure mode the
    no-fabrication rule exists to prevent (skill 03).
    """
    from rapidfuzz import fuzz

    needle = _normalize(value)
    haystack = _normalize(source_text)
    if not needle:
        return False
    if needle in haystack:
        return True
    if kind == "summary":
        # a summary is allowed to rephrase, but must keep its content words
        tokens = [t for t in needle.split() if len(t) > 3]
        if not tokens:
            return False
        kept = sum(1 for t in tokens if t in haystack)
        return kept / len(tokens) >= 0.7
    if len(needle) < 6:
        return False
    return fuzz.partial_ratio(needle, haystack) >= 92


def _rule_value_index(store: Any, profile_id: str, document_id: str) -> set[str]:
    """Normalized values the deterministic pass already found (agreement signal)."""
    values: set[str] = set()
    for record in store.all("facts").values():
        if record.get("profile_id") != profile_id:
            continue
        provenance = record.get("provenance") or {}
        if provenance.get("document_id") != document_id:
            continue
        value = record.get("value")
        if value is not None and not isinstance(value, (dict, list)):
            values.add(_normalize(str(value)))
        skill = record.get("skill") or {}
        name = skill.get("normalized_name") or skill.get("name")
        if name:
            values.add(_normalize(str(name)))
    return values


def _facts_from_ai(
    profile_id: str,
    payload: dict[str, Any],
    *,
    document_id: str,
    provider: str,
    source_text: str | None = None,
    rule_values: set[str] | None = None,
) -> list[ResumeFact]:
    """Map the AI's JSON onto inferred facts (confidence < 1.0 by construction).

    When ``source_text`` is given every value is **grounded** against it and
    ungrounded values are dropped; confidence then encodes agreement —
    0.9 when the rule pass found the same value, 0.7 when only the model did.
    Without ``source_text`` the legacy taxonomy-only behaviour is kept (the
    deterministic contract used by tests and by paste-only imports).
    """
    from app.adapters import skill_taxonomy

    facts: list[ResumeFact] = []
    rule = f"llm:{provider}"
    agreed = rule_values or set()

    def confidence_for(value: str) -> float:
        if source_text is None:
            return 0.8
        return 0.9 if _normalize(value) in agreed else 0.7

    for key, field_class in _FIELD_CLASS.items():
        raw = payload.get(key)
        values = [raw] if key in ("location", "summary") and isinstance(raw, str) else []
        if isinstance(raw, list):
            values = [str(v).strip() for v in raw if str(v).strip()]
        for value in values:
            if field_class == "location" and len(value) > 80:
                continue
            if field_class == "summary" and len(value) < 40:
                continue
            if source_text is not None and not _grounded(
                value, source_text, "summary" if field_class == "summary" else "value"
            ):
                continue  # never store a claim the resume does not contain
            facts.append(
                ResumeFact(
                    profile_id=profile_id,
                    field_class=field_class,
                    value=value[:600],
                    confidence=confidence_for(value),
                    provenance=FactProvenance(document_id=document_id, extraction_rule=rule),
                )
            )

    skills = payload.get("skills")
    if isinstance(skills, list):
        known = {s.lower() for s in skill_taxonomy.known_surface_names()}
        for item in skills:
            name = str(item).strip()[:120]
            if not name:
                continue
            is_known = name.lower() in known
            if source_text is None:
                if not is_known:
                    continue  # taxonomy discipline without a source to check against
            elif not _grounded(name, source_text):
                continue  # open vocabulary, but only when the text has it
            canonical = skill_taxonomy.canonical(name)
            facts.append(
                ResumeFact(
                    profile_id=profile_id,
                    field_class="skill",
                    skill=SkillClaim(name=name, normalized_name=canonical),
                    confidence=confidence_for(canonical if is_known else name),
                    provenance=FactProvenance(document_id=document_id, extraction_rule=rule),
                )
            )
    return facts
