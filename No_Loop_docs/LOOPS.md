# LOOPS.md — The Loop System (No Loop May Be Skipped)

This is the operational heart of the project. Every unit of work on No_Loop happens inside a named loop. A loop = entry condition → ordered steps → exit criteria → written artifacts. **An agent that skips a loop or a step inside a loop has not done the work**, even if code exists.

## 0. The Meta-Loop (always running)

```
SELECT loop (by task type) → verify environment → run loop → close loop (evidence)
   ↑                                                            │
   └──────────────────── next task / next increment ←───────────┘
```

**Every loop, without exception, starts with:**
1. Read ENVIRONMENT.md §2 and set env vars (R-ENV-1, R-ENV-2: nothing on C:).
2. Confirm active interpreter is the project `.venv` on `D:` (R-ENV-4).
3. Read the task-relevant sections of MASTER_SPEC.md and the matching skill file in `skills/`.

**Every loop, without exception, ends with (the Closing Checklist):**
1. Tests run + results stated (R-TRUTH-1/2).
2. Lint + type checks run.
3. PROGRESS.md updated with evidence (R-PROC-4).
4. DEVELOPMENT_LEDGER.md entry appended (R-PROC-3).
5. Files changed listed explicitly.
6. Environment check: no writes on `C:`, no duplicate packages introduced (R-ENV-2/3).
7. Any new external claim carries a source URL + date (R-TRUTH-4).

---

## LOOP-1: Bootstrap Loop (repository & tooling)

**Trigger:** empty/missing app skeleton, or a fresh clone with no tooling.
**Entry:** ENVIRONMENT.md read and applied.
1. Create repository layout exactly as ARCHITECTURE.md §Repository.
2. Create `pyproject.toml` (PEP 621) + lock file; declare the minimal dependency set from ARCHITECTURE.md §Dependencies with per-dependency purpose comments; configure ruff/mypy/pytest per CODING_STANDARDS.md §1.
3. Create `.venv` inside the project on `D:`; install from lock only.
4. Configure ruff + mypy + pytest; create CI workflow running lint, types, tests plus the CODING_STANDARDS.md §12 gates (domain-purity grep, vendor-name grep, .gitignore integrity, coverage).
5. Create `.gitignore` covering `.venv/`, `.local-data/`, caches, build artifacts, secrets — and **`.references/`** (integrity-checked by CI).
6. Create `scripts/devenv.ps1` + `scripts/devenv.sh` exporting ENVIRONMENT.md §2 variables.
7. Verify `.references/` exists with `PROVENANCE.md` (library built 2026-09-28); if re-cloning is ever needed, update PROVENANCE.md the same session.
**Exit:** `pytest` passes on an empty test; `ruff check .` clean; `mypy` clean; venv verified on `D:`.
**Artifacts:** PROGRESS.md P001 → DONE; ledger entry.
**Rules engaged:** R-ENV-1..5, R-ARCH-4.

## LOOP-2: Domain Modeling Loop (per bounded context)

**Trigger:** a new entity/aggregate from MASTER_SPEC §15 (UserProfile, Job, MatchResult, Application, …).
1. Write the domain narrative: what this concept means, what invariants it protects (cite MASTER_SPEC section).
2. Define Pydantic models: fields, types, validation, invariants as model validators. No IO, no vendor imports (R-ARCH-1/3).
3. Define the port (interface) if this concept talks to the outside world.
4. Table-driven tests: valid cases, invalid cases, boundary cases, invariant violations.
5. Property-ish round-trip tests: serialize → deserialize → equality.
**Exit:** tests prove every invariant; `mypy` clean; no vendor/IO imports in domain files (grep check).
**Artifacts:** ledger entry; PROGRESS.md P002 (and per-entity sub-items).
**Rules:** R-ARCH-1, R-ARCH-3, R-TRUTH-1.

## LOOP-3: Adapter Loop (per external integration)

**Trigger:** a new job source, ATS, email provider, AI provider, browser, or OS integration.
1. **Policy first (before any code):** research the target's terms, robots.txt, API docs, rate limits. Fetch live pages when network is available. Classify POLICY_STATUS per AGENT_RULES R-POLICY-1 with source URLs + access date in `DATA_SOURCES.md` §Adapter policy register.
2. Define the adapter's capability declaration: DISCOVERY / PARSING / APPLICATION / EMAIL / CAPABILITIES / POLICY_STATUS (MASTER_SPEC §6).
3. Implement the port from the domain side; adapter maps external shapes ↔ domain models. Vendor names never leak past this layer (R-ARCH-3).
4. Contract tests against recorded fixtures (saved real responses, redacted). No live network in unit tests.
5. Optional live smoke test, marked `@pytest.mark.network`, rate-limited, off by default.
6. Failure mapping: every external error → domain error with stage/reason/retryable/user-action (MASTER_SPEC §17).
7. Manual fallback defined and documented for every automated capability (R-POLICY-2/3).
**Exit:** contract tests pass; policy register updated; fallback documented; adapter listed in adapter catalog.
**Artifacts:** ledger entry with decision record; PROGRESS.md P006/P008/P011 as applicable.
**Rules:** R-POLICY-1..4, R-ARCH-2, R-SEC-2.

## LOOP-4: Feature Loop (vertical slice)

**Trigger:** a feature from DEVELOPMENT.md build order.
1. State the acceptance criteria ( Given/When/Then ) and cite the MASTER_SPEC requirement number it implements.
2. Identify affected layers; plan the smallest coherent change (R-PROC-2).
3. Domain → application service → adapter wiring → UI, in that order, each step compiling.
4. Tests at each layer: unit (domain), service (application), contract (adapters), UI smoke.
5. No-AI-mode test: feature works with NoAIProvider/RuleBasedProvider (hard requirement, MASTER_SPEC §12).
6. Failure-path test: simulate failure at every external boundary; verify §17 failure behavior (no silent failure).
7. **Profile-scoping check (v0.1):** any feature touching profile-scoped data must prove cross-profile isolation (invariant 7, APPLICATION_LEDGER.md) and correct behavior under profile switching.
8. **Limits-gate check (v0.1):** discovery/queue features verify they remain disabled until mandatory limits setup is complete (MASTER_SPEC §4).
9. Update user-facing docs for the feature (all three languages when UI strings changed).
**Exit:** acceptance criteria demonstrated by named tests; no-AI mode proven; failure paths proven; profile isolation proven where applicable.
**Artifacts:** ledger entry; PROGRESS.md item; DEVELOPMENT.md checklist tick if a build-order stage completes.
**Rules:** R-TRUTH-2/3, R-ARCH-6, R-UX-1.

## LOOP-5: Resume Intelligence Loop (per capability)

**Trigger:** parser/extraction/profile work (P004, P005).
1. Source a test corpus: synthetic resumes (no real personal data committed) + public sample documents; record provenance in RESEARCH.md.
2. Implement extraction (PDF via PyMuPDF, DOCX via python-docx, TXT) — extraction ≠ inference (skill 03).
3. **Scanned/image-only PDF path (v0.1):** when extraction yields no text, produce the clear error + guided paste-text fallback (MASTER_SPEC §3); never crash, never hang, never attempt OCR.
4. Implement structure detection → normalized profile fields with per-field confidence.
5. Inferred-but-unconfirmed fields are stored separately and never displayed as fact (R-POLICY-6).
6. Onboarding question generation from gaps/ambiguities (MASTER_SPEC §4) — questions must be answerable, skippable, editable; the mandatory limits-setup step is part of this loop's deliverables (v0.1).
7. Golden-file tests: input file → expected normalized profile; regression on every parser change.
8. ATS-format sanity: generated/tailored output validated against single-column standard-heading best practice (DATA_SOURCES.md §Resume formatting evidence).
**Exit:** golden tests pass; scanned-PDF error path proven; confidence report correct; no fabricated facts possible by construction.
**Artifacts:** ledger; PROGRESS.md P004/P005.
**Rules:** R-POLICY-6, R-TRUTH-1.

## LOOP-6: Matching Engine Loop

**Trigger:** matching/scoring work (P007).
1. Hard constraints coded deterministically: location, work-mode, experience range, exclusions, work authorization.
2. Soft scoring: skills overlap (rapidfuzz + taxonomy normalization via O*NET/ESCO data per DATA_SOURCES.md), title similarity, requirement required-vs-preferred weighting.
3. Every score emits a factor breakdown + missing-requirements list (R-UX-4). No unexplained single numbers.
4. Calibration fixtures: (profile, job, expected classification) triples reviewed by the human.
5. Performance test: 1,000 jobs × typical profile under the target budget (MASTER_SPEC §13) on the dev baseline; record numbers in ledger, never invent them (R-TRUTH-1).
**Exit:** deterministic tests pass; explanation output verified; benchmark recorded.
**Artifacts:** ledger; PROGRESS.md P007.
**Rules:** R-ARCH-6, R-UX-4, R-TRUTH-1.

## LOOP-7: Content Generation Loop (resumes, answers, emails)

**Trigger:** generation features (P009 + application package from MASTER_SPEC §9).
1. Prompt/template design: input = canonical profile subset + job record + requirement mapping; output schema validated.
2. Evidence mapping: every generated claim carries a pointer to a confirmed profile fact; generator structurally cannot emit unmapped claims for factual fields.
3. Job-specificity check: email must reference actual role/company/requirements; automated guard rejects generic-template-only output (CURSOR_MASTER_PROMPT email contract).
4. No-AI path: rule-based drafting produces a compliant, useful draft without any AI provider.
5. Human preview mandatory by default; send/submit gated by settings + explicit consent (R-SEC-3).
**Exit:** guard tests pass (fabrication attempt blocked; generic email rejected); preview flow verified.
**Artifacts:** ledger; PROGRESS.md P009.
**Rules:** R-POLICY-6, R-TRUTH-5, R-UX-2/3.

## LOOP-8: Automation Loop (browser/application fill adapters)

**Trigger:** any adapter that fills application forms (P011). **v0.1 scope: FILL-ONLY — the adapter never clicks Submit; the user always performs the final submission** (user decision, NOLOOP_DEV_KICKOFF-spec §3 Round 6; MASTER_SPEC §11). Auto-submit is v0.2, gated on field-reliability telemetry from fill-only runs.
1. Complete LOOP-3 (policy classification) first. If `PROHIBITED` → build assisted flow instead and stop.
2. Implement the ApplicationAdapter contract from CURSOR_MASTER_PROMPT (discover fields → map → upload → fill → pause on ambiguity → consent → **fill-only handoff: present the completed form to the user** → user clicks Submit → user confirms outcome → record evidence).
3. Hard stops: CAPTCHA, MFA, anti-bot challenge, unknown page state → pause, hand control to user, record (R-POLICY-2).
4. Stop/pause honored synchronously; tested (R-SEC-4).
5. Playwright launched on demand only; browsers path on `D:` (R-ENV-2); no resident process (R-ARCH-5).
6. Evidence capture: screenshots/DOM snapshot hashes + timestamps + **field-reliability log (which fields mapped/filled/failed)** written to AutomationRun record; ledger record created for every run (success or failure).
7. Dry-run mode: full fill without any user-visible site change risk, used in all tests.
**Exit:** dry-run + fill-only tests pass; no submit path exists in code (grep-audited); hard-stop tests pass; evidence verified; policy status re-confirmed with live sources + date.
**Artifacts:** ledger with decision record; PROGRESS.md P011; APPLICATION_LEDGER.md updated if schema changed.
**Rules:** R-POLICY-2/3, R-SEC-4, R-TRUTH-5.

## LOOP-9: Security Review Loop

**Trigger:** any PR touching network, storage, secrets, automation, or personal data; and pre-release always.
1. Threat-model the change: inputs, trust boundaries, data flows, what leaves the device.
2. Checklist SECURITY.md item by item; each item marked pass/fail/N-A with evidence.
3. Secret-scan diff; grep logs for sensitive patterns; verify redaction.
4. SSRF test the URL fetcher with private-range/scheme payloads.
5. Verify delete-all/export works and actually removes everything (DB, files, caches).
6. **Contamination check:** confirm `docs/ATTRIBUTIONS.md` entries exist for every adapted snippet in the diff; confirm no code structurally mirrors AGPL sources (`.references/PROVENANCE.md` checkout rule 4).
**Exit:** checklist complete with evidence; failures fixed before merge.
**Artifacts:** ledger entry with security impact section filled.
**Rules:** R-SEC-1..5.

## LOOP-10: Performance Loop

**Trigger:** every build-order stage end; any feature suspected slow; pre-release.
1. Run the benchmark suite (parsing, normalization, matching, SQLite ops, dedup, UI startup, memory, network concurrency) on the documented baseline hardware profile.
2. Record real numbers with machine specs in ledger; compare against MASTER_SPEC §13 targets (R-TRUTH-1: never fabricate benchmarks).
3. If over budget: profile → fix (cache/lazy/index/bounded concurrency) → re-measure. No dependency removal/addition without a benchmark delta (skill 10).
4. Memory ceiling check on 2 GB profile (bounded caches, streaming parsing, no resident browser/model).
**Exit:** benchmarks recorded; regressions explained or fixed.
**Artifacts:** ledger; PROGRESS.md P014.

## LOOP-11: Packaging Loop

**Trigger:** P012; every release. **v0.1 ships a portable .zip — no installer** (user decision, NOLOOP_DEV_KICKOFF-spec §3 Round 3).
1. Build onedir bundle (PyInstaller first; Nuitka only if benchmarked better) for Windows 10/11 x64; zip the bundle with a README ("extract anywhere, run No_Loop.exe").
2. First-run: data location chooser (default per-user folder / Portable toggle per NOLOOP_DEV_KICKOFF-spec §4.3); verify no C-drive writes on the dev/test machine outside documented user-data locations (ENVIRONMENT.md §5).
3. Portable test: extract the zip to two different locations (incl. a non-system drive), run both, relocate the data dir via Settings, verify the app re-points DB/artifacts/caches and integrity holds.
4. Clean-VM test: download zip → extract → first-run wizard (import sample resume → limits setup → discovery dry run) → delete folder leaves only user-chosen data dir (documented).
5. Footprint budget: zip + extracted size vs. recorded budget; deltas explained in ledger.
6. Inno Setup installer + MSIX + update-check/crash-report (both opt-in, off by default) are v0.2 additions.
**Exit:** clean-VM + portable tests pass; zip artifact attached to release notes.
**Artifacts:** ledger; PROGRESS.md P012.

## LOOP-12: Research Loop (live data verification)

**Trigger:** (a) before designing any adapter/feature that touches external systems, (b) every policy re-verification (quarterly or before release), (c) when any doc claim is challenged.
1. List the claims to verify (from DATA_SOURCES.md registers or the task).
2. Fetch authoritative sources live: official API docs, terms pages, robots.txt, library docs. Prefer primary sources; record URL + access date + quote.
3. Update DATA_SOURCES.md / RESEARCH.md registers; bump review dates; flag drift (endpoint changed, policy text changed, license changed).
4. Feed changes into the affected adapters' policy status and, if status changes, open a task through LOOP-3/LOOP-8.
**Exit:** every listed claim either re-verified with fresh source or flagged UNVERIFIED in writing.
**Artifacts:** ledger entry listing claims re-verified; register diff.
**Rules:** R-TRUTH-4, R-POLICY-1.

## LOOP-13: Quality Gate / Release Audit Loop

**Trigger:** release candidate; also after any major milestone.
1. Run the full final quality gate list from CURSOR_MASTER_PROMPT (fresh install → no-key operation → security → packaging → docs).
2. Independent re-check of every VERIFIED claim in PROGRESS.md by sampling evidence (skill 15).
3. Verify documentation cross-links: README → AGENT_RULES → LOOPS → skills all resolve; no placeholder text anywhere (`grep -ri "TODO\|TBD\|placeholder\|lorem"` on docs).
4. Verify no-duplication audit: lock file reviewed for capability-duplicate packages; ENVIRONMENT audit snippet run.
**Exit:** signed-off audit section appended to PROGRESS.md with date and findings.
**Artifacts:** ledger; release notes draft.

## LOOP-14: Incident & Failure Handling Loop

**Trigger:** any runtime failure reported, test flake, data corruption, or rule violation discovered.
1. Reproduce; capture stage/reason/retryability per MASTER_SPEC §17.
2. Classify: bug / policy drift / environment drift / rule violation.
3. Fix at the correct layer (domain invariant → adapter mapping → env contract) — never patch symptoms in the wrong layer.
4. Add the regression test that would have caught it.
5. If a rule was violated: record in ledger per AGENT_RULES §Enforcement and add a guard step to the relevant loop.
**Exit:** reproduction test passes post-fix; incident documented.
**Artifacts:** ledger entry; loop amendment if needed.

## LOOP-15: Documentation Sync Loop

**Trigger:** end of every task that changed behavior, schema, policy status, or architecture.
1. Update the smallest set of docs affected: MASTER_SPEC (if behavior contract changed), ARCHITECTURE (if layers/dependencies changed), DATA_SOURCES (if sources/policies changed), PROGRESS + ledger (always).
2. Cross-link check: any new file referenced from README index.
3. Verify the doc statement ↔ code reality correspondence for the changed area (R-TRUTH-2).
**Exit:** docs state exactly what the code does, with no stale claims.
**Artifacts:** included in the ledger entry.

---

## Loop selection table

| Task type | Loop(s) | Mandatory co-runs |
|---|---|---|
| New repo/tooling | LOOP-1 | — |
| New/changed entity | LOOP-2 | LOOP-15 |
| New integration | LOOP-3 | LOOP-12 before code, LOOP-9 after |
| User feature | LOOP-4 | LOOP-15 |
| Resume/parse work | LOOP-5 | LOOP-10 if hot path |
| Matching work | LOOP-6 | LOOP-10 |
| Generation work | LOOP-7 | LOOP-15 |
| Form-fill automation | LOOP-8 (fill-only) | LOOP-3 first, LOOP-9 after |
| Touches secrets/network/data | LOOP-9 | — |
| Suspected slowness / stage end | LOOP-10 | — |
| Release | LOOP-11 + LOOP-13 | LOOP-10, LOOP-12 |
| Anything fails | LOOP-14 | — |
| External claim verification | LOOP-12 | — |
| Docs changed | LOOP-15 | — |
| Reference-repo study / snippet adoption | R-ENV-6 + R-TRUTH-6 gates | LOOP-9 |

**Anti-patterns (loop violations):** writing code before the policy step of LOOP-3; marking DONE without tests; fixing an import by duplicating a package (R-ENV-3); "temporary" C: writes; claiming benchmark numbers without running them; editing docs to match buggy code instead of fixing code (LOOP-14 misuse).
