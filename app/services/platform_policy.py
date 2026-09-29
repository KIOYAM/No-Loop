"""Platform policy registry + Assisted Flow (R-POLICY-3; DATA_SOURCES §1.9).

HARD BOUNDARY (binding docs, verified 2026-09-28):
- LinkedIn: User Agreement §8.2 + "Prohibited software and extensions" page
  prohibit scraping and unauthorized automation. Status: PROHIBITED.
- Indeed: no public candidate API; ToS restricts automated access.
  Status: ASSISTED_ONLY.
- Naukri: terms prohibit automated/derivative use. Status: PROHIBITED.

No_Loop therefore NEVER bots these platforms. Instead it ships the compliant
**Assisted Flow**: a complete application package (answers sheet from
confirmed facts, tailored email, checklist) the user submits themselves; the
outcome is then recorded in the ledger. This is a first-class product feature
per the kickoff spec — automation where permitted, assistance everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.errors import SourcePolicyError
from app.domain.jobs import PolicyStatus

__all__ = ["PlatformPolicy", "PLATFORM_POLICIES", "build_assisted_package"]

POLICY_REVIEW_DATE = "2026-09-28"


@dataclass(frozen=True)
class PlatformPolicy:
    """One external platform's policy declaration (evidence-backed)."""

    key: str  # opaque key; vendor name only in display_name (adapter-side data)
    display_name: str
    status: PolicyStatus
    policy_source_url: str
    policy_note: str
    can_prepare_package: bool = True  # assisted flow always available
    can_automate: bool = False


PLATFORM_POLICIES: dict[str, PlatformPolicy] = {
    "linkedin": PlatformPolicy(
        key="linkedin",
        display_name="LinkedIn",
        status=PolicyStatus.PROHIBITED,
        policy_source_url=(
            "https://www.linkedin.com/legal/user-agreement (§8.2); "
            "https://www.linkedin.com/help/linkedin/answer/a1341387"
        ),
        policy_note=(
            "User Agreement §8.2 prohibits scraping and unauthorized automation; "
            "auto-apply tools are listed as violations. No_Loop prepares; you submit."
        ),
    ),
    "indeed": PlatformPolicy(
        key="indeed",
        display_name="Indeed",
        status=PolicyStatus.ASSISTED_ONLY,
        policy_source_url="https://www.indeed.com/legal (ToS; automated access restricted)",
        policy_note=(
            "No public candidate API; ToS restricts automated access. Assisted flow provided."
        ),
    ),
    "naukri": PlatformPolicy(
        key="naukri",
        display_name="Naukri",
        status=PolicyStatus.PROHIBITED,
        policy_source_url="https://www.naukri.com/termsconditions",
        policy_note="Terms prohibit automated/derivative use without written consent.",
    ),
    "ats_fill": PlatformPolicy(
        key="ats_fill",
        display_name="ATS public forms (fill-only)",
        status=PolicyStatus.USER_ACCOUNT_REQUIRED,
        policy_source_url="Per-ATS policy register (DATA_SOURCES.md §9)",
        policy_note=(
            "Public application forms: No_Loop may auto-FILL; the user always clicks Submit (v0.1)."
        ),
        can_automate=False,  # fill-only in v0.1; auto-submit is v0.2 gated on telemetry
    ),
}


def policy_for(platform_key: str | None) -> PlatformPolicy:
    """Resolve a platform key to its policy; unknown -> assisted-only default."""
    if platform_key and platform_key in PLATFORM_POLICIES:
        return PLATFORM_POLICIES[platform_key]
    return PlatformPolicy(
        key=platform_key or "unknown",
        display_name=platform_key or "Unknown platform",
        status=PolicyStatus.ASSISTED_ONLY,
        policy_source_url="default-assisted",
        policy_note=(
            "No verified automation permission — assisted flow by default (R-POLICY-1 default)."
        ),
    )


def assert_no_bot(platform_key: str) -> PlatformPolicy:
    """Raise if any code path attempts bot automation on a restricted platform."""
    policy = policy_for(platform_key)
    if policy.status in (PolicyStatus.PROHIBITED, PolicyStatus.ASSISTED_ONLY):
        raise SourcePolicyError(
            stage=f"automation.{policy.key}",
            reason=(
                f"{policy.display_name} is {policy.status.value}: "
                "bot automation is forbidden by policy"
            ),
            details={"policy_source": policy.policy_source_url, "note": policy.policy_note},
        )
    return policy


@dataclass
class AssistedPackage:
    """Everything the user needs to submit manually, in one view."""

    platform_key: str
    status: PolicyStatus
    steps: list[str] = field(default_factory=list)
    answers: list[dict[str, str]] = field(default_factory=list)
    answers_needing_user: list[dict[str, str]] = field(default_factory=list)
    email_draft: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform_key,
            "policy_status": self.status.value,
            "steps": self.steps,
            "answers_ready": self.answers,
            "answers_needing_user": self.answers_needing_user,
            "email_draft": self.email_draft,
            "evidence": self.evidence,
        }


def build_assisted_package(
    *,
    platform_key: str,
    policy: PlatformPolicy,
    answers_ready: list[dict[str, str]],
    answers_needing_user: list[dict[str, str]],
    email_draft: str | None,
    job_title: str,
    company: str,
) -> AssistedPackage:
    """Assemble the human-submission package (no network, no bot)."""
    return AssistedPackage(
        platform_key=platform_key,
        status=policy.status,
        steps=[
            f"1. Open the {policy.display_name} application page for '{job_title}' at {company}.",
            "2. Upload the tailored resume artifact (generated from your confirmed facts).",
            "3. Copy each 'ready' answer below into the matching form field.",
            "4. Answer the flagged questions yourself — No_Loop will not guess for you.",
            "5. Review everything, then YOU click Submit.",
            "6. Return here and record the outcome "
            "(No_Loop saves it to your ledger with evidence).",
        ],
        answers=answers_ready,
        answers_needing_user=answers_needing_user,
        email_draft=email_draft,
        evidence={
            "policy_source_url": policy.policy_source_url,
            "policy_note": policy.policy_note,
            "prepared_by": "assisted-flow",
        },
    )
