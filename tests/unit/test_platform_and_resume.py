"""Unit tests: platform policy enforcement + assisted flow + resume edge cases."""

from __future__ import annotations

import pytest
from app.adapters.resume_edgecases import (
    content_hash,
    decode_bytes,
    looks_like_encrypted_pdf,
    normalized_hash,
)
from app.domain.errors import SourcePolicyError
from app.domain.jobs import PolicyStatus
from app.services.platform_policy import (
    PLATFORM_POLICIES,
    assert_no_bot,
    build_assisted_package,
    policy_for,
)


class TestPlatformPolicies:
    def test_linkedin_is_prohibited_with_evidence(self) -> None:
        policy = PLATFORM_POLICIES["linkedin"]
        assert policy.status is PolicyStatus.PROHIBITED
        assert "8.2" in policy.policy_source_url  # evidence pinned
        assert policy.can_automate is False

    def test_indeed_is_assisted_only(self) -> None:
        assert PLATFORM_POLICIES["indeed"].status is PolicyStatus.ASSISTED_ONLY

    def test_naukri_is_prohibited(self) -> None:
        assert PLATFORM_POLICIES["naukri"].status is PolicyStatus.PROHIBITED

    def test_assert_no_bot_blocks_prohibited(self) -> None:
        with pytest.raises(SourcePolicyError, match="forbidden by policy"):
            assert_no_bot("linkedin")
        with pytest.raises(SourcePolicyError):
            assert_no_bot("naukri")

    def test_assert_no_bot_blocks_unknown_by_default(self) -> None:
        # R-POLICY-1 default: unknown platform = assisted-only (fail closed).
        with pytest.raises(SourcePolicyError):
            assert_no_bot("some-new-portal")

    def test_unknown_platform_gets_assisted_policy(self) -> None:
        policy = policy_for("mystery-board")
        assert policy.status is PolicyStatus.ASSISTED_ONLY


class TestAssistedPackage:
    def test_package_contains_steps_answers_and_evidence(self) -> None:
        policy = PLATFORM_POLICIES["linkedin"]
        package = build_assisted_package(
            platform_key="linkedin",
            policy=policy,
            answers_ready=[{"q": "Years of experience", "a": "2+ years"}],
            answers_needing_user=[{"q": "Work authorization", "reason": "legal status"}],
            email_draft="Dear hiring team…",
            job_title="Python Developer",
            company="Acme",
        )
        data = package.to_dict()
        assert data["policy_status"] == "prohibited"
        assert len(data["steps"]) == 6
        assert "YOU click Submit" in " ".join(data["steps"])
        assert data["answers_ready"][0]["a"] == "2+ years"
        assert data["answers_needing_user"][0]["q"] == "Work authorization"
        assert "8.2" in data["evidence"]["policy_source_url"]


class TestResumeEdgeCases:
    def test_utf8_bom_decoded(self) -> None:
        text, enc = decode_bytes(b"\xef\xbb\xbfKannan resume")
        assert text == "Kannan resume"  # BOM stripped
        assert enc == "utf-8-sig"

    def test_utf16_detected(self) -> None:
        text, enc = decode_bytes("Kannan resume éà".encode("utf-16"))
        assert "Kannan" in text
        assert enc.startswith("utf-16")

    def test_cp1252_smart_quotes(self) -> None:
        data = "Kannan’s resume — experience".encode("cp1252")
        text, enc = decode_bytes(data)
        assert "Kannan’s" in text  # smart quote preserved
        assert enc == "cp1252"

    def test_double_encoded_mojibake_skipped(self) -> None:
        # UTF-8 bytes mis-labeled: decoder should skip mojibake candidates.
        data = "café résumé".encode()
        text, enc = decode_bytes(data)
        assert "café" in text

    def test_undecodable_never_crashes(self) -> None:
        text, enc = decode_bytes(bytes(range(0, 256)) * 4)
        assert isinstance(text, str) and enc == "utf-8-replace"

    def test_empty_raises_clear(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            decode_bytes(b"")

    def test_encrypted_pdf_detected(self) -> None:
        fake = b"%PDF-1.7 ... /Encrypt 5 0 R ... trailer"
        assert looks_like_encrypted_pdf(fake) is True
        assert looks_like_encrypted_pdf(b"%PDF-1.7 plain text only") is False
        assert looks_like_encrypted_pdf(b"not a pdf") is False

    def test_content_hash_stable_and_normalized(self) -> None:
        a = content_hash(b"same")
        assert content_hash(b"same") == a != content_hash(b"other")
        # normalized text hash ignores line-ending + spacing noise
        h1 = normalized_hash("line one\r\nline two  x")
        h2 = normalized_hash("line one\nline two x")
        assert h1 == h2
