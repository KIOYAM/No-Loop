"""Unit tests: Job model + dedup fingerprint (LOOP-2; RESEARCH.md S8)."""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.jobs import Job, PolicyStatus, SourceRef, content_fingerprint
from pydantic import ValidationError


def make_job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = {
        "title": "Python Developer",
        "company": "Acme Corp",
        "location": "Chennai",
        "work_mode": "hybrid",
        "description_text": "FastAPI + SQLAlchemy role",
        "source": SourceRef(
            kind="public_api",
            adapter_id="adapter_a",
            native_id="abc123",
            url="https://jobs.example.com/1",
        ),
    }
    defaults.update(overrides)
    return Job(**defaults)


class TestFingerprint:
    def test_fingerprint_stable_across_whitespace_case(self) -> None:
        # Cosmetic differences must NOT create distinct identities (S8).
        a = content_fingerprint("Python Developer", "Acme", "FastAPI role")
        b = content_fingerprint("python   developer", "ACME", "FastAPI   role")
        assert a == b

    def test_fingerprint_differs_for_content(self) -> None:
        a = content_fingerprint("Python Developer", "Acme", "FastAPI role")
        b = content_fingerprint("Python Developer", "Acme", "Django role")
        assert a != b

    def test_job_auto_fingerprints(self) -> None:
        job = make_job()
        assert job.fingerprint is not None
        assert job.fingerprint == content_fingerprint(job.title, job.company, job.description_text)


class TestSourceRef:
    def test_url_scheme_allowlist(self) -> None:
        # R-SEC-2: only http(s) source URLs enter the domain.
        with pytest.raises(ValidationError, match="http"):
            SourceRef(kind="url_import", adapter_id="adapter_a", url="file:///etc/passwd")

    def test_kind_is_generic_taxonomy_not_vendor(self) -> None:
        # R-ARCH-3: the domain sees generic kinds; adapters own vendor names.
        ref = SourceRef(kind="ats_board", adapter_id="adapter_b", native_id="x1")
        assert ref.kind == "ats_board"


class TestJobInvariants:
    def test_salary_min_max_ordered(self) -> None:
        with pytest.raises(ValidationError, match="salary_min"):
            make_job(salary_min=900_000, salary_max=500_000)

    def test_blank_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_job(title="  ")

    def test_remote_friendly_detection(self) -> None:
        remote = make_job(work_mode="remote")
        assert remote.is_remote_friendly is True
        onsite = make_job(work_mode="onsite", location="Chennai")
        assert onsite.is_remote_friendly is False


class TestPolicyStatusEnum:
    def test_all_five_statuses_exist(self) -> None:
        # R-POLICY-1: the taxonomy is exactly these five.
        assert {s.value for s in PolicyStatus} == {
            "allowed_public_api",
            "permitted_with_limits",
            "user_account_required",
            "assisted_only",
            "prohibited",
        }
