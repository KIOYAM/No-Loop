"""MatchResult domain model (MASTER_SPEC §8; RESEARCH.md S1/S5).

The Match Triangle: hard gate (boolean) + soft score (weighted factors) +
explanation. No deceptive single numbers — every score carries its factors and
the missing requirements.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["GateVerdict", "MatchFactor", "MatchResult"]


class GateVerdict(enum.StrEnum):
    PASS = "pass"  # noqa: S105 - gate verdict, not a secret
    FAIL = "fail"
    UNDETERMINED = "undetermined"


class MatchFactor(BaseModel):
    """One scored factor with its contribution and human reason."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, examples=["skills_overlap", "title_similarity"])
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0)
    contribution: float
    reason: str = Field(min_length=1)


class MatchResult(BaseModel):
    """Immutable scoring outcome for one (profile, job) pair."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str
    job_id: str
    hard_gate: GateVerdict
    gate_reasons: tuple[str, ...] = Field(default=())
    factors: tuple[MatchFactor, ...] = Field(default=())
    score: float = Field(
        ge=0.0, le=1.0, description="Weighted soft score of gated-in jobs; 0.0 when gated out"
    )
    missing_requirements: tuple[str, ...] = Field(default=())
    notes: tuple[str, ...] = Field(default=(), description="Undetermined-factor notes")

    @property
    def is_eligible(self) -> bool:
        return self.hard_gate == GateVerdict.PASS

    def explain(self) -> str:
        """Human-readable explanation (R-UX-4: factors + missing, never a bare %)."""
        if self.hard_gate == GateVerdict.FAIL:
            return "Excluded: " + "; ".join(self.gate_reasons)
        lines = [f"Score {self.score:.2f}"]
        for f in sorted(self.factors, key=lambda x: -x.contribution):
            lines.append(
                f"  + {f.name}: {f.score:.2f} (w={f.weight:.2f})"
                f" -> {f.contribution:.2f} — {f.reason}"
            )
        if self.missing_requirements:
            lines.append("Missing: " + "; ".join(self.missing_requirements))
        for n in self.notes:
            lines.append(f"Note: {n}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
