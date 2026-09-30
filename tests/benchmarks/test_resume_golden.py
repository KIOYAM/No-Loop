"""Golden evaluation harness for the resume parser (field-level P/R/F1).

Every fixture under ``tests/fixtures/resumes/cases`` carries a hand-written
``gold.json``. This test measures how close the parser gets to that truth and
fails when either number drops below its floor, so extraction work can never
quietly regress.

Run just this benchmark::

    python -m pytest tests/benchmarks -q

Print a report (per field, per case, micro totals)::

    python scripts/bench_resume.py
"""

from __future__ import annotations

import json

import pytest

from tests.benchmarks.golden_scoring import (
    CASE_F1_FLOOR,
    MICRO_F1_FLOOR,
    aggregate,
    load_cases,
    score_case,
)

CASES = load_cases()


def test_at_least_five_golden_cases() -> None:
    """Fixtures are the whole point: losing them must not go unnoticed."""
    names = [case.name for case in CASES]
    assert len(CASES) >= 5, f"golden cases missing: {names}"


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_golden_case(case) -> None:
    report = score_case(case)
    assert report["f1"] >= CASE_F1_FLOOR, json.dumps(report, indent=2, ensure_ascii=False)
    assert not report["failed_checks"], json.dumps(
        report["failed_checks"], indent=2, ensure_ascii=False
    )
    # anti-hallucination: the parser may only say what a human already verified
    hallucinated = {
        field: detail["unexpected"]
        for field, detail in report["fields"].items()
        if detail["unexpected"]
    }
    assert not hallucinated, (
        "facts extracted that are not in gold.json — verify them by eye and "
        "only then add them to the fixture:\n"
        + json.dumps(hallucinated, indent=2, ensure_ascii=False)
    )


def test_micro_f1_across_all_cases() -> None:
    """Pooled field-level F1 over the whole corpus."""
    reports = [score_case(case) for case in CASES]
    agg = aggregate(reports)
    assert agg["f1"] >= MICRO_F1_FLOOR, json.dumps(
        {
            "aggregate": agg,
            "worst_cases": sorted(reports, key=lambda r: r["f1"])[:3],
        },
        indent=2,
        ensure_ascii=False,
    )
