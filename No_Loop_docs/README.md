# No_Loop — Master Development Pack

No_Loop is a local-first, open-source, AI-assisted job discovery and application automation desktop application for Windows-first delivery, built for low-memory machines, and honest by construction: it automates only where permitted, assists everywhere else, and records everything.

## Core principles (binding)

1. No mandatory paid service, subscription, hosted backend, or API key.
2. Local-first and privacy-first: nothing leaves the device without explicit consent.
3. Usable by non-technical users after installation — no terminal, no manual DB setup.
4. Lightweight: core designed for a 2 GB RAM baseline.
5. AI is optional: Tier 0 deterministic → Tier 1 rule-based → Tier 2 BYOK cloud → Tier 3 local model.
6. The user owns the resume/profile data; one Canonical Profile, all outputs are Derived Artifacts.
7. No fabrication, ever: every generated claim traces to a confirmed fact (Evidence Map).
8. Policy-aware automation: unsupported or prohibited sites get Assisted Flows, never bypasses.
9. Every application action is recorded in the Application Ledger.
10. Development itself is loop-driven and ledger-tracked — no loops may be skipped.
11. Open-source (Apache-2.0) with replaceable adapters.

## Document map — read in this order

| # | File | What it is |
|---|---|---|
| 0 | `ENVIRONMENT.md` | Machine contract: D-drive project, C-drive forbiddance, no package duplication. READ FIRST. |
| 1 | `CURSOR_MASTER_PROMPT.md` | Entry prompt for any AI agent starting work. |
| 2 | `AGENT_RULES.md` | The binding rules (R-ENV/R-TRUTH/R-ARCH/R-POLICY/R-PROC/R-SEC/R-UX) invoked by the prompt. |
| 2b | `CODING_STANDARDS.md` | Canonical coding standards: toolchain, typing, errors, async, data, security, tests, deps, git/CI. |
| 3 | `LOOPS.md` | The 15 mandatory loops with entry/exit criteria and the Closing Checklist. |
| 4 | `MASTER_SPEC.md` | The complete product specification (what we build). |
| 5 | `ARCHITECTURE.md` | Stack, layers, repository layout, dependency register (how it is built). |
| 6 | `DEVELOPMENT.md` | Build order, vertical-slice plan, definition of done. |
| 7 | `DATA_SOURCES.md` | Live-verified register of job APIs, taxonomies, policy statuses, legal baselines. |
| 8 | `RESEARCH.md` | Strategy, canonical vocabulary, innovated strategies S1–S10, ADR list. |
| 9 | `PROGRESS.md` | Progress ledger — statuses with evidence. |
| 10 | `DEVELOPMENT_LEDGER.md` | Session/decision records with evidence discipline. |
| 11 | `APPLICATION_LEDGER.md` | Product ledger schema + application state machine. |
| 12 | `SECURITY.md` | Security & privacy requirements and checklist. |
| 13 | `CONTRIBUTING.md` | Contribution process. |
| 14 | `CODE_OF_CONDUCT.md` | Conduct standards. |
| 15 | `LICENSE` | Apache-2.0 (full text). |
| — | `skills/` | 16 role cards; load the relevant one(s) per loop. |

Companion research pack (read-only input, do not modify without human instruction):
`../No_Loop_Open_Source_Reference_Research/` — 8 analyzed public projects, license notes, local inspection guide.

**Reference library (physical):** `../.references/` — read-only shallow clones of all 8 repos + `PROVENANCE.md` (authoritative license verdicts: 3× MIT-SNIPPETS-OK, 4× IDEAS-ONLY, 1× AGPL-NO-COPY). Gitignored; governed by R-ENV-6/R-TRUTH-6. External code adoptions are recorded in `../docs/ATTRIBUTIONS.md`.

**Interview spec:** `NOLOOP_DEV_KICKOFF-spec.md` — 22 binding product decisions from the kickoff interview (DB-by-ADR, multiple profiles, fill-only v0.1, India-first, EN+TA+HI, portable zip, all-applications ledger).

## Rule of precedence

ENVIRONMENT + AGENT_RULES + LOOPS govern *process*. MASTER_SPEC governs *product*. If documents conflict, the more restrictive rule wins until an ADR resolves it.
