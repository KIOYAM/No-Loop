"""Contract tests: arbeitnow adapter against recorded fixture (LOOP-3; skill 04).

No live network in tests (CODING_STANDARDS §8.7): normalization logic is
exercised directly with the fixture payload; the HTTP path is covered by the
SSRF guard's own unit tests and by network-marked smoke tests only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.adapters.sources.arbeitnow import ArbeitnowAdapter, _sanitize_html_to_text

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "arbeitnow_page1.json").read_text(encoding="utf-8")
)


class TestPolicyDeclaration:
    def test_policy_status_is_public_api_with_evidence(self) -> None:
        adapter = ArbeitnowAdapter()
        # R-POLICY-1: status + source URL + review date are mandatory metadata.
        assert adapter.policy.policy_status.value == "allowed_public_api"
        assert adapter.policy.policy_source_url.startswith("https://www.arbeitnow.com")
        assert adapter.policy.policy_reviewed_at == "2026-09-28"
        assert adapter.policy.discovery is True
        assert adapter.policy.application is False  # discovery-only surface


class TestNormalization:
    def test_full_item_maps_to_domain_job(self) -> None:
        adapter = ArbeitnowAdapter()
        job = adapter._normalize(FIXTURE["data"][0])
        assert job is not None
        assert job.title == "Senior Python Developer"
        assert job.company == "Fixture GmbH"
        assert job.work_mode == "remote"
        assert job.source.native_id == "syn-1-pydev"
        assert job.source.kind == "public_api"  # generic taxonomy, not vendor name
        assert job.posted_at is not None and job.posted_at.tzinfo is not None

    def test_description_html_sanitized(self) -> None:
        adapter = ArbeitnowAdapter()
        job = adapter._normalize(FIXTURE["data"][0])
        assert job is not None
        assert "script" not in job.description_text.lower()
        assert "alert" not in job.description_text
        assert "Python" in job.description_text  # real content survives

    def test_malformed_item_skipped_not_fatal(self) -> None:
        # Source isolation: one bad item never kills discovery (skill 04 step 8).
        adapter = ArbeitnowAdapter()
        assert adapter._normalize(FIXTURE["data"][2]) is None

    def test_all_fixture_items_processed(self) -> None:
        adapter = ArbeitnowAdapter()
        jobs = [adapter._normalize(item) for item in FIXTURE["data"]]
        assert sum(1 for j in jobs if j is not None) == 2


class TestSanitizer:
    def test_dangerous_tags_removed(self) -> None:
        dirty = "<p>hello</p><script>evil()</script><iframe src='x'></iframe><style>.x{}</style>"
        clean = _sanitize_html_to_text(dirty)
        assert "evil" not in clean
        assert "hello" in clean


class TestLiveSmoke:
    @pytest.mark.network
    @pytest.mark.asyncio
    async def test_live_discovery_smoke(self) -> None:
        """Live test: opt-in only (`pytest -m network`), rate-limited, 3 jobs max."""
        adapter = ArbeitnowAdapter(page_delay_s=2.0, max_pages=1)
        jobs = []
        async for job in adapter.discover(limit=3):
            jobs.append(job)
        assert len(jobs) <= 3
        for job in jobs:
            assert job.url and job.url.startswith("https://")
