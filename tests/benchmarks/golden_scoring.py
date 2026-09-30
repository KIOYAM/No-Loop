"""Golden-evaluation scoring shared by the pytest benchmark and scripts/bench_resume.py.

Ground truth lives next to each fixture in ``tests/fixtures/resumes/cases/<case>/gold.json``.
The gold files are hand-written: open ``resume.txt`` and you should be able to
verify every listed value with your own eyes. Nothing here is generated from
the parser's output, otherwise a bug would silently redefine "correct".
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

from app.adapters.facts_from_resume import ResumeParseOutcome, parse_resume_text

CASES_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "resumes" / "cases"

#: Numeric facts carry an absolute tolerance: a derived "years" figure moves
#: with today's date (10 vs 11.1 for a decade-long career is not a bug).
FLOAT_TOLERANCE: dict[str, float] = {"experience_years": 2.5}

#: Floors enforced by ``tests/benchmarks/test_resume_golden.py``.
#: Lowering these is a deliberate act, never a side effect of a refactor.
#: Precision is checked separately as "no hallucinated fact at all": every
#: predicted value must appear in gold, so a bad alias cannot slip through.
MICRO_F1_FLOOR = 0.90
CASE_F1_FLOOR = 0.85


@dataclass(frozen=True)
class Case:
    """One golden fixture: raw text plus the hand-written truth."""

    name: str
    path: pathlib.Path
    text: str
    gold: dict[str, Any]

    @property
    def resume_path(self) -> pathlib.Path:
        return self.path / "resume.txt"


def load_cases() -> list[Case]:
    cases: list[Case] = []
    if not CASES_DIR.is_dir():
        return cases
    for case_dir in sorted(CASES_DIR.iterdir()):
        gold_path = case_dir / "gold.json"
        if not case_dir.is_dir() or not gold_path.exists():
            continue
        cases.append(
            Case(
                name=case_dir.name,
                path=case_dir,
                text=(case_dir / "resume.txt").read_text(encoding="utf-8"),
                gold=json.loads(gold_path.read_text(encoding="utf-8")),
            )
        )
    return cases


def normalize(value: Any) -> str:
    """Comparison key: dates arrive as dicts, numbers as int/float."""
    if isinstance(value, dict):
        value = value.get("raw", "")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split()).lower()


def predicted_values(outcome: ResumeParseOutcome, field_class: str) -> list[Any]:
    values: list[Any] = []
    for fact in outcome.facts:
        if fact.field_class != field_class:
            continue
        if fact.skill is not None:
            values.append(fact.skill.normalized_name)
        else:
            values.append(fact.value)
    return values


def _match(
    golds: list[Any], preds: list[Any], tolerance: float | None
) -> tuple[set[int], set[int]]:
    """Greedy multiset matching → (matched gold indexes, matched pred indexes)."""
    matched_gold: set[int] = set()
    matched_pred: set[int] = set()
    if tolerance is not None:
        for gi, gold in enumerate(golds):
            for pi, pred in enumerate(preds):
                if pi in matched_pred:
                    continue
                try:
                    left, right = float(pred), float(gold)
                except (TypeError, ValueError):
                    continue
                if abs(left - right) <= tolerance:
                    matched_gold.add(gi)
                    matched_pred.add(pi)
                    break
        return matched_gold, matched_pred

    buckets: dict[str, list[int]] = {}
    for pi, pred in enumerate(preds):
        buckets.setdefault(normalize(pred), []).append(pi)
    for gi, gold in enumerate(golds):
        bucket = buckets.get(normalize(gold))
        if bucket:
            matched_pred.add(bucket.pop())
            matched_gold.add(gi)
    return matched_gold, matched_pred


def score_case(case: Case) -> dict[str, Any]:
    outcome = parse_resume_text("golden", case.text, document_id=case.name)
    expect: dict[str, list[Any]] = case.gold.get("expect", {})
    field_classes = sorted(set(expect) | {f.field_class for f in outcome.facts})

    tp = fp = fn = 0
    fields: dict[str, dict[str, Any]] = {}
    for field_class in field_classes:
        golds = list(expect.get(field_class, []))
        preds = predicted_values(outcome, field_class)
        matched_gold, matched_pred = _match(golds, preds, FLOAT_TOLERANCE.get(field_class))
        field_tp = len(matched_gold)
        field_fn = len(golds) - field_tp
        field_fp = len(preds) - len(matched_pred)
        tp += field_tp
        fn += field_fn
        fp += field_fp
        fields[field_class] = {
            "gold": len(golds),
            "pred": len(preds),
            "tp": field_tp,
            "missing": [str(g) for i, g in enumerate(golds) if i not in matched_gold],
            "unexpected": [str(p) for i, p in enumerate(preds) if i not in matched_pred],
        }

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    failed_checks = _run_checks(case, outcome, fields)
    return {
        "case": case.name,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "coverage": outcome.coverage.get("percent"),
        "ats": outcome.parseability.get("score"),
        "ambiguities": outcome.ambiguities,
        "fields": fields,
        "failed_checks": failed_checks,
    }


def _run_checks(
    case: Case, outcome: ResumeParseOutcome, fields: dict[str, dict[str, Any]]
) -> list[str]:
    """Explicit expectations that field matching cannot express."""
    checks: dict[str, Any] = case.gold.get("checks", {})
    failures: list[str] = []

    if (
        "coverage_percent" in checks
        and outcome.coverage.get("percent") != checks["coverage_percent"]
    ):
        failures.append(
            f"coverage {outcome.coverage.get('percent')} != {checks['coverage_percent']}"
        )
    if "coverage_percent_min" in checks and (
        outcome.coverage.get("percent") is None
        or outcome.coverage.get("percent") < checks["coverage_percent_min"]
    ):
        failures.append(
            f"coverage {outcome.coverage.get('percent')} < {checks['coverage_percent_min']}"
        )
    if "ats_score" in checks and outcome.parseability.get("score") != checks["ats_score"]:
        failures.append(f"ATS {outcome.parseability.get('score')} != {checks['ats_score']}")
    if "ats_score_min" in checks and (
        outcome.parseability.get("score") is None
        or outcome.parseability.get("score") < checks["ats_score_min"]
    ):
        failures.append(f"ATS {outcome.parseability.get('score')} < {checks['ats_score_min']}")
    if "unrecognized_headings" in checks:
        got = list(outcome.structure.get("unrecognized_headings", []))
        want = list(checks["unrecognized_headings"])
        if got != want:
            failures.append(f"unrecognized headings {got} != {want}")

    # fields the resume simply does not contain must produce no facts at all
    for field_class in case.gold.get("absent", []):
        unexpected = fields.get(field_class, {}).get("pred", 0)
        if unexpected:
            failures.append(f"{field_class}: expected none, got {unexpected}")
    return failures


def aggregate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Micro (pooled) precision/recall/F1 across every case."""
    tp = sum(r["tp"] for r in reports)
    fp = sum(r["fp"] for r in reports)
    fn = sum(r["fn"] for r in reports)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "cases": len(reports),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "failed_checks": [f"{r['case']}: {c}" for r in reports for c in r["failed_checks"]],
    }


def full_report() -> dict[str, Any]:
    reports = [score_case(case) for case in load_cases()]
    return {"aggregate": aggregate(reports), "cases": reports}
