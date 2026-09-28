# Skill: Matching Engineer (05)

**Load for:** LOOP-6 (MatchEngine, thresholds, dedup verification, benchmarks).
**Reads:** MASTER_SPEC §8/§13, DATA_SOURCES.md §2, RESEARCH.md S1/S5/S8, AGENT_RULES R-ARCH-6/R-UX-4.

## Role
Build fast deterministic matching with explanations. Hard constraints evaluated separately from soft similarity. Never produce deceptive certainty.

## Design (Match Triangle)
1. **Hard gate (boolean, SQL+code):** location/work-mode compatibility; experience range; work authorization; user exclusions (companies/keywords); recency window; salary floor overlap (if known). Fails → excluded with the reason stored and shown ("Excluded: location mismatch — job is onsite Berlin").
2. **Soft score (weighted factors, deterministic):**
   - skills overlap: taxonomy-normalized skill sets (ESCO/O*NET surface forms), weighted by required-vs-preferred (JD parsing separates "required"/"must have" from "nice to have" via section/phrase rules)
   - title similarity: rapidfuzz on normalized titles + role-family mapping from targeting preferences
   - experience compatibility: JD years vs profile years (parsed from date ranges)
   - education/certification fit when specified
   - salary alignment when both known
   Weights configurable (defaults documented); missing inputs → factor marked N/A, never scored as zero silently.
3. **Explanation:** per-factor contribution list + missing-requirements list; UI shows both (R-UX-4). No single unexplained percentage.

## Threshold behavior (S1)
User threshold gates ApplicationQueue admission: hard-gate pass AND soft score ≥ threshold → eligible for READY; below → stays DISCOVERED with reasons visible. Threshold changes are retroactive-free (invariant 4, APPLICATION_LEDGER.md).

## Performance (with skill 10)
- Stage 1 in SQL with indexes (location, work mode, posted date, source) — target sub-100 ms for typical filters.
- Stage 2 survivors only; sub-500 ms per 1,000 jobs on the baseline (MASTER_SPEC §13); measure in LOOP-10, record real numbers (R-TRUTH-1).
- Cache normalized skill vectors per job (invalidate on JD change).

## Test discipline
- Calibration fixtures: (profile, job, expected gate verdict, expected score band, expected explanation) — reviewed by human.
- Property test: explanation factors sum to displayed score within epsilon.
- Dedup verification fixtures for S8 (cross-source duplicates merge, provenance preserved).

## Guardrails
No AI in the gate or score path (AI may explain top-N only, clearly labeled). No hidden penalties. No fabricated "92% match" certainty language — scores are bands + factors.

## Deliverables
MatchEngine module, taxonomy normalizer, threshold config, explanation renderer data, calibration tests, benchmark entries.
