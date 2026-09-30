#!/usr/bin/env python
"""Golden benchmark for the resume parser.

Measures field-level precision / recall / F1 of ``parse_resume_text`` against the
hand-written ``gold.json`` files under ``tests/fixtures/resumes/cases``.

    python scripts/bench_resume.py                 # human-readable table
    python scripts/bench_resume.py --json          # machine-readable report
    python scripts/bench_resume.py --case no-headings --verbose

Exit status is 1 when the micro F1 floor (the same one enforced by
``tests/benchmarks/test_resume_golden.py``) is breached, so it is safe to call
from CI or a pre-push hook.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.benchmarks.golden_scoring import (  # noqa: E402  (path set above)
    MICRO_F1_FLOOR,
    aggregate,
    load_cases,
    score_case,
)


def _bar(value: float, width: int = 24) -> str:
    filled = round(value * width)
    return "#" * filled + "." * (width - filled)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="only run the named case")
    parser.add_argument("--json", action="store_true", help="emit the full JSON report")
    parser.add_argument("--verbose", action="store_true", help="list every miss")
    parser.add_argument("--top", type=int, default=5, help="worst cases to list")
    args = parser.parse_args(argv)

    cases = [case for case in load_cases() if not args.case or case.name == args.case]
    if not cases:
        print(f"no golden case named {args.case!r}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    reports = [score_case(case) for case in cases]
    elapsed_ms = (time.perf_counter() - started) * 1000
    agg = aggregate(reports)

    if args.json:
        print(json.dumps({"aggregate": agg, "cases": reports}, indent=2, ensure_ascii=False))
        return 0 if agg["f1"] >= MICRO_F1_FLOOR or args.case else 1

    print(f"golden resume benchmark — {agg['cases']} cases, {elapsed_ms:.0f} ms total")
    print()
    header = f"{'case':<24}{'P':>7}{'R':>7}{'F1':>7}{'tp':>5}{'fp':>5}{'fn':>5}  ats cov"
    print(header)
    print("-" * len(header))
    for report in reports:
        print(
            f"{report['case']:<24}"
            f"{report['precision']:>7.3f}"
            f"{report['recall']:>7.3f}"
            f"{report['f1']:>7.3f}"
            f"{report['tp']:>5}{report['fp']:>5}{report['fn']:>5}"
            f"  {report['ats']:>3} {report['coverage']:>3}"
        )
    print("-" * len(header))
    print(
        f"{'MICRO':<24}"
        f"{agg['precision']:>7.3f}"
        f"{agg['recall']:>7.3f}"
        f"{agg['f1']:>7.3f}"
        f"{agg['tp']:>5}{agg['fp']:>5}{agg['fn']:>5}"
        f"   floor {MICRO_F1_FLOOR:.2f} "
        f"{'PASS' if agg['f1'] >= MICRO_F1_FLOOR else 'FAIL'}"
    )
    print()
    print(f"[{_bar(agg['f1'])}] micro F1 {agg['f1']:.3f}")

    misses = []
    for report in reports:
        for field, detail in report["fields"].items():
            for value in detail["missing"]:
                misses.append((report["case"], field, "missed", value))
            for value in detail["unexpected"]:
                misses.append((report["case"], field, "hallucinated", value))
        for check in report["failed_checks"]:
            misses.append((report["case"], "check", "failed", check))

    if misses:
        print()
        print(
            f"{len(misses)} field-level deviations"
            f"{' (use --verbose for all)' if not args.verbose else ''}:"
        )
        shown = misses if args.verbose else misses[: max(args.top * 3, 10)]
        for case, field, kind, value in shown:
            print(f"  {case:<22}{field:<16}{kind:<13}{value}")
        if not args.verbose and len(shown) < len(misses):
            print(f"  … {len(misses) - len(shown)} more (re-run with --verbose)")

    return 0 if agg["f1"] >= MICRO_F1_FLOOR or args.case else 1


if __name__ == "__main__":
    raise SystemExit(main())
