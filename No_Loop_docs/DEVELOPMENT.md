# No_Loop Development Plan

## Day-one objective
Produce a complete runnable vertical product foundation, not a throwaway demo:
- installable desktop shell
- local database initialized automatically
- resume import and parsing
- structured profile with fact ledger
- dynamic onboarding
- target-role selection
- job ingestion from at least one legal/available source plus URL/JD import
- deterministic matching with explanations
- job-specific email drafting
- application ledger
- adapter architecture
- optional browser automation boundary
- settings and provider abstraction
- tests
- packaging
- documentation
- development/progress ledgers

## Build order (each stage = LOOP-4 vertical slice + co-runs)

| # | Stage | Primary loop | Co-runs | PROGRESS items |
|---|---|---|---|---|
| 1 | Repository + quality tooling + env contract | LOOP-1 | LOOP-15 | P001 |
| 2 | Domain models (all 15+ entities) | LOOP-2 ×N | LOOP-15 | P002 |
| 3 | SQLite repository + migrations | LOOP-2/3 | LOOP-9 | P003 |
| 4 | Resume parser + fact ledger | LOOP-5 | LOOP-10 | P004 |
| 5 | Profile confirmation + onboarding engine | LOOP-5 | LOOP-15 | P005 |
| 6 | Job normalization + dedup + source adapters (first: arbeitnow + URL/JD import) | LOOP-3 | LOOP-12 first, LOOP-9 after | P006 |
| 7 | Matching engine | LOOP-6 | LOOP-10 | P007 |
| 8 | AI provider abstraction (Tier 0/1 first) | LOOP-3 | LOOP-9 | P008 |
| 9 | Content generation + evidence mapping | LOOP-7 | LOOP-15 | P009 |
| 10 | Email preview/draft + providers | LOOP-7 | LOOP-9 | P009 |
| 11 | Application ledger + queue + tracker | LOOP-4 | LOOP-15 | P010 |
| 12 | Additional source adapters (remotive, remoteok, adzuna, greenhouse/lever/ashby) | LOOP-3 | LOOP-12 | P006 |
| 13 | Optional browser/application adapter (only if a lawful target exists) | LOOP-8 | LOOP-3 first, LOOP-9 after | P011 |
| 14 | Desktop packaging | LOOP-11 | LOOP-10 | P012 |
| 15 | Integration tests + no-AI-mode suite | LOOP-4/13 | — | P013 |
| 16 | Security review | LOOP-9 | — | P015 |
| 17 | Performance benchmarks | LOOP-10 | — | P014 |
| 18 | Documentation sync | LOOP-15 | — | all |
| 19 | Release artifact + audit | LOOP-13 | LOOP-11, LOOP-12 | P016 |

## Definition of done (any stage)
1. All loop exit criteria met (LOOPS.md).
2. Tests: unit + relevant contract/integration; failure paths included; no-AI mode covered.
3. Lint + types clean; benchmarks run if hot path.
4. Docs updated; ledgers updated with evidence; PROGRESS item DONE (VERIFIED only via independent re-check).
5. Environment audit: no C: writes, no duplicate packages, lock updated.

## Rule
Do not create fake functionality behind green UI. If a feature is not implemented, label it as unavailable and provide its fallback (R-TRUTH-3).

## Working agreements
- AI agents: read CURSOR_MASTER_PROMPT.md → AGENT_RULES.md → the loop for the task → the matching skill card. Then work. Then close the loop.
- Humans: same rules apply; CONTRIBUTING.md is the human-facing summary.
- Any deviation from build order requires a ledger note explaining why and the risk.
