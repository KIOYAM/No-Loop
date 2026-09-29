"""Resume import orchestration service (LOOP-5; user request: full edge-case
handling + memory of the user's data across the whole search/apply process).

Responsibilities:
- decode + edge-case handling (resume_edgecases)
- duplicate detection (content hash + normalized-text hash)
- version history per profile (every import is versioned, never lost)
- fact extraction into the ledger (inferred → user confirms)
- structured import result with honest errors (R-TRUTH-3)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.adapters.extractors import get_extractor
from app.adapters.resume_edgecases import (
    content_hash,
    decode_bytes,
    looks_like_docx,
    looks_like_encrypted_pdf,
    normalized_hash,
)
from app.adapters.settings_store import SettingsStore
from app.adapters.storage import JsonStore
from app.domain.errors import ValidationError

__all__ = ["ImportResult", "ResumeService"]

_MAX_BYTES = 10 * 1024 * 1024

#: Progress callback signature: (stage_id, status, human-readable detail).
StageCallback = Callable[[str, str, str], None]


@dataclass
class ImportResult:
    ok: bool
    profile_id: str
    version: int | None = None
    facts_created: int = 0
    duplicate_of_version: int | None = None
    encoding: str | None = None
    warnings: list[str] = field(default_factory=list)
    error_reason: str | None = None
    user_action: str | None = None
    text: str | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data.pop("text", None)  # raw resume text never leaves the service layer
        return data


class ResumeService:
    """All resume imports flow through here (single entry, full memory)."""

    def __init__(self, store: JsonStore, settings: SettingsStore) -> None:
        self.store = store
        self.settings = settings

    # -- public API ---------------------------------------------------------

    def import_resume(
        self,
        *,
        profile_id: str,
        filename: str,
        data: bytes,
        on_stage: StageCallback | None = None,
    ) -> ImportResult:
        def stage(sid: str, status: str, detail: str = "") -> None:
            if on_stage is not None:
                on_stage(sid, status, detail)

        stage("validate", "running", "checking file type, size and integrity")
        if len(data) > _MAX_BYTES:
            return self._fail("file exceeds the 10 MB limit", "Split or compress the file.")
        if not data:
            return self._fail("file is empty", "Check the file and retry.")
        stage("validate", "done", f"{len(data) // 1024} KB · {filename}")

        stage("dedupe", "running", "hashing content to detect a duplicate import")
        content_key = content_hash(data)
        duplicate = self._find_duplicate(profile_id, content_key)
        if duplicate is not None:
            stage("dedupe", "skipped", f"identical to version {duplicate}")
            return ImportResult(
                ok=True,
                profile_id=profile_id,
                duplicate_of_version=duplicate,
                warnings=["identical file already imported — no new version created"],
            )
        stage("dedupe", "done", "unique file — new version will be created")

        # encrypted-PDF detection BEFORE generic extraction (clear error, not a parse crash)
        stage("detect", "running", "sniffing format and encryption")
        if filename.lower().endswith(".pdf") and looks_like_encrypted_pdf(data):
            stage("detect", "failed", "password-protected PDF")
            return self._fail(
                "this PDF is password-protected/encrypted",
                "Export an unprotected copy (or remove the password) and retry.",
            )

        if filename.lower().endswith(".docx") and not looks_like_docx(data):
            stage("detect", "failed", "bad DOCX header")
            return self._fail(
                "file is not a valid DOCX (bad header)", "Re-save as .docx from Word."
            )
        stage("detect", "done", filename.rsplit(".", 1)[-1].upper())

        # text acquisition: TXT decodes directly; PDF/DOCX go through extractors
        stage("extract", "running", "extracting raw text")
        if filename.lower().endswith((".txt", ".md")):
            try:
                text, encoding = decode_bytes(data)
            except ValueError as exc:
                stage("extract", "failed", str(exc))
                return self._fail(str(exc), "Check the file contents.")
            if not text.strip():
                stage("extract", "failed", "no readable text")
                return self._fail("no readable text in file", "Check the file contents.")
        else:
            extractor = get_extractor(filename)
            if extractor is None:
                stage("extract", "failed", "unsupported format")
                return self._fail(
                    f"unsupported format: {filename.rsplit('.', 1)[-1]}",
                    "Supported: .txt, .md, .docx, .pdf (text-layer).",
                )
            result = extractor.extract(data)  # type: ignore[attr-defined]
            if not result.ok:
                stage("extract", "failed", result.error_reason or "extraction failed")
                return self._fail(result.error_reason or "extraction failed", result.user_action)
            text, encoding = result.text, "extractor"

        if not text.strip():
            stage("extract", "failed", "scanned/image document")
            return self._fail(
                "no text found — this looks like a scanned/image document",
                "Export a text PDF or paste your resume text (paste flow).",
            )
        stage("extract", "done", f"{len(text):,} characters · {encoding}")

        # facts (inferred; user confirms next)
        from app.adapters.facts_from_resume import parse_resume_text

        stage("parse", "running", "rule-based fact extraction")
        outcome = parse_resume_text(profile_id, text, document_id=filename)
        warnings = list(outcome.ambiguities)
        stage(
            "parse",
            "done",
            f"{len(outcome.facts)} inferred facts · sections: "
            f"{', '.join(outcome.detected_sections) or 'none detected'}",
        )

        # version history (full memory of the user's documents)
        stage("persist", "running", "writing version history + fact ledger")
        version = self._next_version(profile_id)
        self.store.upsert(
            "resume_versions",
            f"{profile_id}:{version}",
            {
                "profile_id": profile_id,
                "version": version,
                "filename": filename,
                "content_hash": content_key,
                "normalized_hash": normalized_hash(text),
                "encoding": encoding,
                "chars": len(text),
                "imported_at": version and None,  # timestamp added by storage layer consumer
            },
        )
        for fact in outcome.facts:
            self.store.upsert("facts", fact.id, fact.model_dump(mode="json"))

        # remember contact on the profile (memory across the whole process)
        self._remember_contact(
            profile_id, outcome.contact_email, outcome.contact_phone, outcome.links
        )
        stage("persist", "done", f"version {version} stored")

        return ImportResult(
            ok=True,
            profile_id=profile_id,
            version=version,
            facts_created=len(outcome.facts),
            encoding=encoding,
            warnings=warnings,
            text=text,
        )

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _fail(reason: str, action: str) -> ImportResult:
        return ImportResult(ok=False, profile_id="", error_reason=reason, user_action=action)

    def _find_duplicate(self, profile_id: str, content_key: str) -> int | None:
        for record in self.store.all("resume_versions").values():
            if record.get("profile_id") == profile_id and record.get("content_hash") == content_key:
                return int(record.get("version", 0))
        return None

    def _next_version(self, profile_id: str) -> int:
        highest = 0
        for record in self.store.all("resume_versions").values():
            if record.get("profile_id") == profile_id:
                highest = max(highest, int(record.get("version", 0)))
        return highest + 1

    def _remember_contact(
        self, profile_id: str, email: str | None, phone: str | None, links: list[str]
    ) -> None:
        data = self.store.get("profiles", profile_id)
        if not data:
            raise ValidationError(stage="resume.import", reason=f"unknown profile {profile_id}")
        from app.domain.profile import CandidateProfile

        profile = CandidateProfile.model_validate(data)
        updates: dict[str, Any] = {}
        if email and not profile.contact_email:
            updates["contact_email"] = email
        if phone and not profile.contact_phone:
            updates["contact_phone"] = phone
        for link in links:
            if "github.com" in link and "github" not in profile.links:
                updates.setdefault("links", {**profile.links, "github": link})
        if updates:
            updated = profile.model_copy(update=updates)
            self.store.upsert("profiles", profile.id, updated.model_dump(mode="json"))

    # -- assisted-flow persistence (memory across search+apply) --------------

    def record_assisted_package(self, profile_id: str, package: dict[str, Any]) -> str:
        """Persist a prepared assisted-flow package so the user never re-answers."""
        import uuid

        package_id = str(uuid.uuid4())
        self.store.upsert(
            "assisted_packages",
            package_id,
            {"profile_id": profile_id, **package},
        )
        return package_id
