"""AI provider adapters (LOOP-3; MASTER_SPEC §12; RESEARCH.md S7).

Tier 0 NoAIProvider and Tier 1 RuleBasedProvider ship first: the app is fully
useful with zero keys (hard requirement). BYOK Gemini arrives in a later slice;
its adapter will implement the same protocol.
"""

from __future__ import annotations

from typing import Any

from app.domain.errors import ProviderUnavailableError
from app.ports import GenerationRequest, GenerationResult

__all__ = ["NoAIProvider", "RuleBasedProvider"]


class NoAIProvider:
    """Always available; generates nothing. Forces callers down rule-based paths."""

    name = "no-ai"

    def available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest | None) -> GenerationResult:
        task = request.task if request is not None else "unknown"
        raise ProviderUnavailableError(
            stage=f"ai.{task}",
            reason="No-AI mode produces no generated text; use the rule-based drafting service",
        )

    def privacy_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sends_data_off_device": False,
            "data_categories": [],
            "destination": None,
            "retention": "nothing is sent anywhere",
        }

    def estimate_cost(self, request: GenerationRequest) -> dict[str, Any]:
        return {"provider": self.name, "money": 0.0, "latency": "instant", "available": True}


class RuleBasedProvider:
    """Template + selection NLG over CONFIRMED facts only (S2 truth-preserving).

    ``generate`` executes the task locally: no network, no model, deterministic
    output for identical inputs. Unknown tasks raise ProviderUnavailableError so
    callers fall back visibly (MASTER_SPEC §17).
    """

    name = "rule-based"

    def available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if request.task == "email_draft":
            return GenerationResult(
                text=self._draft_email(
                    request.facts_payload, request.job_payload, request.instructions
                ),
                provider=self.name,
            )
        raise ProviderUnavailableError(
            stage=f"ai.{request.task}", reason=f"task not supported by {self.name}"
        )

    @staticmethod
    def _draft_email(facts_payload: str, job_payload: str, instructions: str) -> str:
        facts = _parse_payload(facts_payload)
        job = _parse_payload(job_payload)
        role = job.get("title", "the role")
        company = job.get("company", "your company")
        skills = facts.get("skills", [])
        years = facts.get("experience_years")
        skill_line = ", ".join(skills[:5]) if skills else "my core technical skills"
        experience_line = (
            f"with {years}+ years of experience" if years else "with hands-on project experience"
        )
        body = (
            f"Dear Hiring Team,\n\n"
            f"I am applying for the {role} position at {company}. "
            f"The role's requirements align directly with my background {experience_line} "
            f"in {skill_line}.\n\n"
        )
        reqs = job.get("requirements", [])
        if reqs:
            body += "On the specific requirements:\n"
            for req in reqs[:4]:
                body += f"- {req}\n"
            body += "\n"
        body += (
            "My resume is attached with details of relevant projects and measurable outcomes. "
            "I would welcome the opportunity to discuss how I can contribute to your team.\n\n"
            "Best regards,\n"
        )
        name = facts.get("name")
        body += name if name else "[Your name]"
        return body

    def privacy_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sends_data_off_device": False,
            "data_categories": [],
            "destination": "local only",
            "retention": "deterministic templates; nothing stored beyond drafts",
        }

    def estimate_cost(self, request: GenerationRequest) -> dict[str, Any]:
        return {"provider": self.name, "money": 0.0, "latency": "<10ms", "available": True}


def _parse_payload(payload: str) -> dict[str, Any]:
    """Payloads are 'key=value' lines (kept dependency-free and redaction-friendly)."""
    out: dict[str, Any] = {}
    for line in payload.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
        elif line.startswith("- "):
            out.setdefault("requirements", []).append(line[2:].strip())
    if "skills" in out and isinstance(out["skills"], str):
        out["skills"] = [s.strip() for s in out["skills"].split(",") if s.strip()]
    return out
