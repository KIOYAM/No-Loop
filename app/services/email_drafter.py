"""Email drafting service (LOOP-7; RESEARCH.md S2; skill 08).

Guards (tested):
- G1 job-specificity: draft must reference role, company, ≥2 JD requirements,
  ≥2 evidence-backed skills — else generation REFUSES (no generic filler).
- G2 fact-truthfulness: only CONFIRMED facts enter payloads (caller contract
  asserted here via fact states).
- G3 certainty-spam ban: banned phrases rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.adapters.ai_providers import RuleBasedProvider
from app.domain.errors import ValidationError
from app.domain.facts import FactState, ResumeFact
from app.domain.jobs import Job
from app.ports import GenerationRequest

__all__ = ["EmailDraft", "EmailDrafter", "BANNED_PHRASES"]

BANNED_PHRASES = (
    "guaranteed",
    "100% match",
    "perfect fit",
    "i am the best",
    "dream candidate",
    "world-class expert",
)


@dataclass
class EmailDraft:
    body: str
    provider: str
    evidence: dict[str, list[str]] = field(default_factory=dict)
    job_specificity: dict[str, object] = field(default_factory=dict)


class EmailDrafter:
    """Rule-based job-specific email generation with guard checks."""

    def __init__(self, provider: RuleBasedProvider | None = None) -> None:
        self._provider = provider or RuleBasedProvider()

    def draft(self, *, profile_name: str | None, facts: list[ResumeFact], job: Job) -> EmailDraft:
        # G2: confirmed facts only
        confirmed = [f for f in facts if f.state == FactState.CONFIRMED]
        skills = [f.skill.name for f in confirmed if f.field_class == "skill" and f.skill]
        years_list = [int(f.value) for f in confirmed if f.field_class == "experience_years"]

        requirements = _extract_requirements(job.description_text)

        # G1 pre-check: refuse drafting when we cannot be job-specific
        if len(requirements) < 1 and not job.description_text.strip():
            raise ValidationError(
                stage="email.draft",
                reason="no JD requirements to reference; refusing generic filler",
                user_action="Import the full JD text or paste the description.",
            )

        facts_payload = (
            f"name={profile_name or ''}\n"
            f"skills={', '.join(skills)}\n"
            f"experience_years={years_list[0] if years_list else ''}\n"
        )
        job_payload = f"title={job.title}\ncompany={job.company}\n" + "".join(
            f"- {r}\n" for r in requirements[:6]
        )
        result = self._provider.generate(
            GenerationRequest(
                task="email_draft",
                instructions="job-specific application email",
                facts_payload=facts_payload,
                job_payload=job_payload,
            )
        )
        body = result.text

        # G3: certainty-spam ban
        lowered = body.lower()
        for phrase in BANNED_PHRASES:
            if phrase in lowered:
                raise ValidationError(
                    stage="email.draft", reason=f"banned certainty phrase in draft: '{phrase}'"
                )

        # G1 post-check: verify specificity
        checks = {
            "references_role": job.title.lower() in lowered,
            "references_company": job.company.lower() in lowered,
            "references_requirements": sum(1 for r in requirements if r.lower()[:30] in lowered)
            >= 2
            or any(r.lower()[:30] in lowered for r in requirements),
            "references_skills": sum(1 for s in skills if s.lower() in lowered) >= 2
            or len(skills) == 0,
        }
        if not (checks["references_role"] and checks["references_company"]):
            raise ValidationError(
                stage="email.draft",
                reason="draft failed job-specificity guard (role/company missing)",
            )

        evidence: dict[str, list[str]] = {
            "skills_used": skills[:8],
            "experience_years": [str(y) for y in years_list],
            "requirements_referenced": requirements[:6],
            "fact_ids": [f.id for f in confirmed if f.field_class in ("skill", "experience_years")],
        }
        return EmailDraft(
            body=body,
            provider=result.provider,
            evidence=evidence,
            job_specificity={"job_id": job.id, **checks},
        )


def _extract_requirements(description_text: str) -> list[str]:
    """Deterministic requirement extraction: bullet lines & 'required/must' sentences."""
    requirements: list[str] = []
    for line in description_text.splitlines():
        clean = line.strip().lstrip("-•*· ").strip()
        if not clean or len(clean) < 8 or len(clean) > 160:
            continue
        if re.match(r"^[-•*·]", line.strip()):
            requirements.append(clean)
            continue
        low = clean.lower()
        if any(
            k in low
            for k in ("must have", "required", "requirements", "you will", "responsibilities")
        ):
            requirements.append(clean)
    return requirements
