# SELF_AUDIT.md — Honest Gap Analysis & Rebuild Plan

**Date:** 2026-09-28 · **Auditor:** Buffy (adversarial self-audit per skill 15, applied mid-build)
**Trigger:** User challenge: "you don't fully develop this as per the standards and not added as the cores we focusing on and you still not solving anything."

## 1. Audit verdict: the challenge is CORRECT

What was built (5 domain models + 59 tests + tooling) is **infrastructure, not the product**. Measured against MASTER_SPEC §1, it delivers capabilities 1–3 of **17** and demonstrates exactly none of the core value loop the user asked for:

```
import resume → facts → profile → targeting → discover → dedup → match → explain
→ tailor → draft email → queue/threshold → ledger → export
```

### Capability coverage audit (MASTER_SPEC §1.1–§1.17)

| # | Capability | Status | Gap |
|---|---|---|---|
| 1 | Import resume | ❌ | No extractor exists. Nothing imports anything. |
| 2 | Parse/understand | ❌ | No extraction pipeline. |
| 3 | Build profile | ◐ | Models exist; no service builds one from facts. |
| 4 | Dynamic onboarding questions | ❌ | No question engine. |
| 5 | Suggest targeting | ❌ | — |
| 6 | Accept/edit criteria | ◐ | Domain types exist; nothing uses them. |
| 7 | Discover jobs | ❌ | **No source adapter exists.** Not one byte of real job data can flow. |
| 8 | Normalize + dedup (S8) | ◐ | Fingerprint exists; no resolver/merger. |
| 9 | Score + Match Triangle | ❌ | No MatchResult model, no engine. THE core IP — missing. |
| 10 | Explain matches | ❌ | — |
| 11 | Employer research | ❌ | — |
| 12 | Application package (S2) | ❌ | No generator; no DOCX/PDF. |
| 13 | Job-specific email | ❌ | No drafter; no evidence map; no anti-generic guard. |
| 14 | Preview | ❌ | No CLI/UI surface at all — **nothing can be run**. |
| 15 | Fill-only automation | ❌ | — (planned post-P006) |
| 16 | Assisted flow | ❌ | — |
| 17 | Track all applications | ◐ | Domain state machine exists; no ledger service/persistence/export. |

### Standards non-compliance found in my own code

1. **R-ARCH-2 violated by omission:** zero ports defined — adapters were impossible by construction.
2. **ADR-6 (user-mandated FIRST ADR) skipped** — I built tooling before the benchmarked DB decision.
3. **LOOP-3 never executed** — no adapter, no policy classification run, no fixtures.
4. **No entry point:** no CLI, no app wiring; "runnable" claim in ledger was overclaimed (R-TRUTH-1 violation by me).
5. **StorageError raised nowhere** — the StorageError exists but nothing persists anything.
6. **pytest-asyncio installed but unused; httpx/selectolax/rapidfuzz installed but unused** — deps declared for capabilities I hadn't built.

### Root cause
I optimized for *process-legible* increments (tests green, gates green) instead of *user-legible* increments (can I import my resume and get matches?). Process compliance became a substitute for product delivery — precisely the "fake functionality behind green UI" failure DEVELOPMENT.md forbids.

## 2. Rebuild plan (executed immediately after this audit)

Priority: close capabilities **7/8/9/10 → 1/2/3 → 13 → 17 → 14** — discovery+matching first (the differentiating core), then resume import, then drafting, ledger, and a runnable CLI surface. Storage via in-file SQLite repositories **behind a port**, with ADR-6 benchmark still to be run before depending on SQLite-specific behavior.

| Wave | Capabilities closed | Deliverables |
|---|---|---|
| W1 | 9, 10, 8 | `MatchResult` domain model; `MatchEngine` (hard gate → soft score → explanation); `JobIdentityResolver` (5-key dedup, S8) |
| W2 | 1, 2, 3 | Ports (`ResumeExtractor`, `SourceAdapter`, `AIProvider`, `Repository`); TXT/DOCX extractor + honest "PDF unavailable (ADR-2 pending)" path; profile builder service (facts → confirmed profile) |
| W3 | 7 | First real source adapter (arbeitnow — ALLOWED_PUBLIC_API, DATA_SOURCES §1.1) with fixture contract tests; URL/JD import adapter; SSRF-guarded fetcher |
| W4 | 13, 17 | Email drafter (rule-based, evidence map, anti-generic guard); queue service (threshold+caps enforcement); ledger service + CSV/JSON export |
| W5 | 14 | `app/cli.py`: import → confirm → discover → match → draft → apply → quick-add → export pipeline |
| W6 | — | Integration test: end-to-end with synthetic fixtures, no network; audit doc updated; ledgers updated |

## 3. Permanent process correction (anti-pattern named)

New rule added to AGENT_RULES (R-PROC-8): *every development session must advance at least one user-visible MASTER_SPEC capability end-to-end, or state in the ledger why it cannot.* Process gates prove correctness; only capability closure proves progress.

## 4. What was genuinely good (kept)

- Domain invariants (evidence rule, consent gate, limits gate) are correct and load-bearing — they will be exercised by the new services.
- Tooling/CI gates work and caught real violations during coding.
- The audit discipline itself: this document exists because the user challenged, and the honest answer was "yes."
