"""MatchEngine — the two-stage matching service (LOOP-6; RESEARCH.md S1/S5).

Stage 1 HARD GATE (deterministic, boolean): location/work-mode, exclusions,
recency, salary floor. Fail => excluded WITH the reason (R-UX-4).
Stage 2 SOFT SCORE (weighted factors): skills overlap (rapidfuzz), title
similarity, salary alignment. Missing inputs => factor marked N/A via notes,
never silently scored as zero (skill 05).

AI never runs here — this is Tier-0 deterministic (R-ARCH-6).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rapidfuzz import fuzz

from app.domain.jobs import Job
from app.domain.matching import GateVerdict, MatchFactor, MatchResult
from app.domain.profile import TargetPreference, WorkMode

__all__ = ["MatchEngine"]


def _default_now() -> datetime:
    """Naive local now (posted_at from adapters may be tz-aware or naive)."""
    return datetime.now(tz=UTC)  # noqa: DTZ005 - deliberate naive/aware mixing point


def _to_utc(value: datetime) -> datetime:
    """Normalize naive datetimes to UTC by *assuming* they are UTC-local.

    Adapters may emit naive (source-local) or aware timestamps; comparison
    requires one frame. Documented assumption, tested both ways.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


_DEFAULT_WEIGHTS: dict[str, float] = {
    "skills_overlap": 0.50,
    "title_similarity": 0.35,
    "salary_alignment": 0.15,
}

_SKILL_SYNONYMS: dict[str, tuple[str, ...]] = {
    "py": ("python",),
    "fastapi": ("fast api",),
    "ml": ("machine learning",),
    "js": ("javascript",),
}


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _skill_tokens(text: str) -> set[str]:
    """Lowercased word tokens, with common tech-compounds joined (e.g. node.js)."""
    t = _norm(text)
    t = t.replace("node.js", "nodejs").replace(".net", "dotnet")
    return {w.strip(".,;:()[]") for w in t.split() if w}


def _skills_from_job(job: Job) -> set[str]:
    """Extract a crude skill-candidate set from the JD text (deterministic).

    The taxonomy normalizer (ESCO/O*NET) will replace this heuristic later;
    the MatchEngine only depends on the *interface*, so swapping it is local.
    """
    known = {
        "python",
        "java",
        "javascript",
        "typescript",
        "sql",
        "html",
        "css",
        "fastapi",
        "django",
        "flask",
        "react",
        "nodejs",
        "docker",
        "kubernetes",
        "aws",
        "azure",
        "gcp",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "machine learning",
        "deep learning",
        "nlp",
        "pandas",
        "numpy",
        "pytorch",
        "tensorflow",
        "git",
        "linux",
        "rest",
        "api",
        "ci/cd",
    }
    tokens = _skill_tokens(job.description_text)
    found: set[str] = set()
    for skill in known:
        if " " in skill:
            if skill in job.description_text.lower():
                found.add(skill)
        elif skill in tokens:
            found.add(skill)
    return found


def _skills_from_profile(skills: list[str]) -> set[str]:
    out: set[str] = set()
    for s in skills:
        n = _norm(s)
        for syn in _SKILL_SYNONYMS.get(n, (n,)):
            out.add(syn)
    return out


class MatchEngine:
    """Deterministic matcher. Construct once; call :meth:`score` per job."""

    def __init__(
        self,
        *,
        profile_id: str,
        profile_skills: list[str],
        targeting: TargetPreference,
        weights: dict[str, float] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.profile_id = profile_id
        self.profile_skills = _skills_from_profile(profile_skills)
        self.targeting = targeting
        self.weights = dict(_DEFAULT_WEIGHTS if weights is None else weights)
        self.now = now or _default_now()
        wsum = sum(self.weights.values())
        if abs(wsum - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0 (got {wsum})")

    # ---------- Stage 1: hard gate ----------

    def _gate(self, job: Job) -> tuple[GateVerdict, list[str]]:
        reasons: list[str] = []
        t = self.targeting

        # Work-mode compatibility
        if job.work_mode and t.work_modes and WorkMode.ANY not in t.work_modes:
            job_mode = job.work_mode  # normalized by adapters to remote/hybrid/onsite
            allowed = {m.value for m in t.work_modes}
            if job_mode not in allowed and job_mode != "unknown":
                reasons.append(
                    f"work mode mismatch: job is {job_mode}, targeting {sorted(allowed)}"
                )

        # Location (only enforced for non-remote jobs)
        if t.locations and not job.is_remote_friendly:
            loc = (job.location or "").lower()
            if not any(city.lower() in loc for city in t.locations):
                reasons.append(
                    f"location mismatch: job is onsite at '{job.location}',"
                    f" targeting {sorted(t.locations)}"
                )

        # Exclusions
        company = _norm(job.company)
        if any(x.lower() == company for x in t.excluded_companies):
            reasons.append(f"company excluded: {job.company}")
        jd = job.description_text.lower()
        if any(kw.lower() in jd for kw in t.excluded_keywords):
            reasons.append("excluded keyword present in description")

        # Recency — compare in a single reference frame: convert everything to UTC.
        if job.posted_at is not None and t.recency_days:
            posted = _to_utc(job.posted_at)
            now_utc = _to_utc(self.now)
            if posted < now_utc - timedelta(days=t.recency_days):
                reasons.append(f"posting older than {t.recency_days} days")

        return (GateVerdict.FAIL, reasons) if reasons else (GateVerdict.PASS, [])

    # ---------- Stage 2: soft score ----------

    def _score_factors(self, job: Job) -> tuple[list[MatchFactor], list[str], list[str]]:
        factors: list[MatchFactor] = []
        notes: list[str] = []
        missing: list[str] = []
        t = self.targeting

        # skills overlap
        job_skills = _skills_from_job(job)
        if self.profile_skills and job_skills:
            inter = self.profile_skills & job_skills
            score = len(inter) / max(1, len(job_skills))
            missing += sorted(job_skills - self.profile_skills)[:5]
            matched_preview = ", ".join(sorted(inter)[:6]) or "none"
            factors.append(
                MatchFactor(
                    name="skills_overlap",
                    score=round(score, 4),
                    weight=self.weights["skills_overlap"],
                    contribution=round(score * self.weights["skills_overlap"], 4),
                    reason=(
                        f"profile matches {len(inter)}/{len(job_skills)} JD skills"
                        f" ({matched_preview})"
                    ),
                )
            )
        else:
            notes.append("skills_overlap undetermined (missing profile skills or JD text)")

        # title similarity
        best = 0.0
        for title in self.targeting.role_titles:
            best = max(best, fuzz.token_set_ratio(_norm(job.title), _norm(title)) / 100.0)
        factors.append(
            MatchFactor(
                name="title_similarity",
                score=round(best, 4),
                weight=self.weights["title_similarity"],
                contribution=round(best * self.weights["title_similarity"], 4),
                reason=f"best title match {best:.0%} vs targeting roles",
            )
        )

        # salary alignment
        if t.min_salary and job.salary_max:
            if job.salary_currency and t.currency and job.salary_currency != t.currency:
                notes.append(
                    "salary_alignment skipped (currency mismatch; conversion not supported)"
                )
                score = 0.5
                reason = "salary present but currency differs — neutral 0.5"
            else:
                if job.salary_max >= t.min_salary:
                    score, reason = 1.0, "salary_max meets the target floor"
                else:
                    score = max(0.0, job.salary_max / t.min_salary)
                    reason = f"salary_max {job.salary_max} below target {t.min_salary}"
            factors.append(
                MatchFactor(
                    name="salary_alignment",
                    score=round(score, 4),
                    weight=self.weights["salary_alignment"],
                    contribution=round(score * self.weights["salary_alignment"], 4),
                    reason=reason,
                )
            )
        else:
            notes.append("salary_alignment undetermined (missing salary data)")

        return factors, notes, missing

    # ---------- Public API ----------

    def score(self, job: Job) -> MatchResult:
        verdict, reasons = self._gate(job)
        if verdict == GateVerdict.FAIL:
            return MatchResult(
                profile_id=self.profile_id,
                job_id=job.id,
                hard_gate=verdict,
                gate_reasons=tuple(reasons),
                score=0.0,
            )
        factors, notes, missing = self._score_factors(job)
        score = round(sum(f.contribution for f in factors), 4)
        return MatchResult(
            profile_id=self.profile_id,
            job_id=job.id,
            hard_gate=GateVerdict.PASS,
            factors=tuple(factors),
            score=min(1.0, score),
            missing_requirements=tuple(missing),
            notes=tuple(notes),
        )
