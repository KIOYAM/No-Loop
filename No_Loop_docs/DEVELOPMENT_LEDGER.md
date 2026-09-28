# No_Loop Development Ledger

For every AI-assisted coding session, append one entry (newest last). Never claim completion without evidence.

## Entry template

```
### [YYYY-MM-DD HH:MM] <task title>
- Agent/model:
- Loop(s) executed:
- Task:
- Files changed: (exact paths)
- Reason:
- Tests run: (names/commands)
- Test results: (actual outcomes)
- Lint/types: (commands + result)
- Unresolved issues:
- Architectural decisions: (ADR refs if any)
- Dependencies added/removed: (lock delta; none = "none")
- Security impact: (none / described)
- Performance impact: (numbers if measured; never invented)
- Environment audit: no C: writes? duplicate packages? (R-ENV-2/3)
- Evidence: (test output excerpts, benchmark numbers, screenshots refs)
```

## Decision record template (ADR, referenced from entries)

```
### ADR-<n>: <title>
### Decision
### Context
### Options
### Chosen option
### Why
### Trade-offs
### Revisit condition
```

Open ADR slots (from RESEARCH.md §4 + NOLOOP_DEV_KICKOFF-spec): ADR-1 UI shell; ADR-2 PDF reading library; ADR-3 persistence layer (merged into ADR-6 run); ADR-4 taxonomy bundling; ADR-5 email send path; **ADR-6 embedded DB (FIRST to execute — SQLite vs DuckDB benchmark protocol in spec §4.2); ADR-7 PDF writing library (ReportLab vs weasyprint).**

## Entries

### [2026-09-28] Documentation pack created
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Loop(s) executed: LOOP-12 (research) + LOOP-15 (docs)
- Task: Create the full No_Loop documentation pack: environment contract, agent rules, loop system, master spec, architecture, development plan, data-source register, strategy research, ledgers, security/contributing/conduct/license, and 16 skill cards.
- Files changed: all files in No_Loop_docs/ (see PROGRESS.md P017 evidence)
- Reason: project needed complete, non-overlapping, cross-linked rules so AI agents can develop No_Loop without missing loops, fabricating data, or polluting the machine.
- Tests run: none (documentation-only change)
- Research performed (R-TRUTH-4): live web verification of job APIs (Arbeitnow, Remotive, RemoteOK, Jobicy, Adzuna, Jooble, HN/Algolia), ATS public boards (Greenhouse, Lever, Ashby), taxonomies (O*NET, ESCO), policy sources (LinkedIn UA §8.2 + prohibited-software help page, Naukri terms), DPDP Act 2023 consent principles, Ollama model RAM needs, PyInstaller/Inno packaging, ATS resume-formatting studies. Access dates 2026-09-28; URLs recorded in DATA_SOURCES.md.
- Dependencies added/removed: none (no code yet)
- Environment audit: no tooling installed; no C: writes; no package changes.
- Unresolved issues: ADR-1..5 open by design; Workday public-API status marked UNVERIFIED-PRIMARY until a primary source is pinned; Jooble approval flow to verify during first LOOP-12 re-run.
- Evidence: DATA_SOURCES.md §1–9; RESEARCH.md; this entry.

### [2026-09-28, later] Canonical-doc amendments from NOLOOP_DEV_KICKOFF-spec §12 (LOOP-15)
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Loop(s) executed: LOOP-15 (documentation sync)
- Task: Apply the 8 spec amendments from the interview-based kickoff spec (22 user decisions captured 2026-09-28) to the canonical docs: MASTER_SPEC (multiple named candidate profiles; v0.1 fill-only automation posture; mandatory limits setup with no silent caps; India-first defaults; scanned-PDF error path; ledger tracks ALL applications incl. manual; Gemini-first BYOK; EN+TA+HI UI; portable data location), AGENT_RULES (new R-ENV-6 reference-library rule; new R-TRUTH-6 attribution/license gate; new R-PROC-7 session-start live verification; R-POLICY-3 fill-only amendment), APPLICATION_LEDGER (entry_method field; Quick-Add manual flow; profile_id scoping; invariants 6–7), ARCHITECTURE (portable-zip packaging; i18n layer; ADR-7 PDF writer + reportlab in dependency register; component map + repository layout updates; Gemini-first Tier 2), ENVIRONMENT (§1.4 .references/ contract + gitignore requirement), LOOPS (LOOP-4 profile-isolation + limits-gate checks; LOOP-5 scanned-PDF path; LOOP-8 fill-only scope + field-reliability log + no-submit grep audit; LOOP-11 portable zip scope; selection table updates), DATA_SOURCES (new §9 reference-repo license register with reuse postures).
- Files changed: MASTER_SPEC.md, AGENT_RULES.md, APPLICATION_LEDGER.md, ARCHITECTURE.md, ENVIRONMENT.md, LOOPS.md, DATA_SOURCES.md, DEVELOPMENT_LEDGER.md, NOLOOP_DEV_KICKOFF-spec.md (created earlier this session)
- Reason: user interview decisions (6 rounds, 22 answers) had to become binding canonical rules before Milestone M1 development starts
- Tests run: none (documentation-only change)
- Lint/types: n/a
- Unresolved issues: ADR-6 must be the first ADR executed (M1); Tamil/Hindi translations require a copy-freeze first
- Architectural decisions: fill-only v0.1 automation; multiple named profiles with profile_id scoping from M2; all-applications ledger with entry_method; portable zip distribution; DB decision deferred to benchmarked ADR-6
- Dependencies added/removed: none (reportlab noted as pending ADR-7, not yet added)
- Security impact: positive — fill-only removes the submit-automation attack surface for v0.1; attribution/license gates reduce supply-chain risk
- Performance impact: none (docs)
- Environment audit: no C: writes; no packages installed; no duplicate rules introduced (cross-checked)
- Evidence: spec file NOLOOP_DEV_KICKOFF-spec.md §3 (22 decisions), §12 (amendment list); each amended file cites the spec section it implements

### [2026-09-28, latest] Reference library built + coding standards created (LOOP-1 partial + LOOP-15)
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Loop(s) executed: LOOP-1 (partial: .gitignore + reference-library step) + LOOP-15 (docs)
- Task: Build the physical reference library per NOLOOP_DEV_KICKOFF-spec §5.1 and write the canonical coding standards.
- Work performed:
  1. Cloned all 8 audited reference repos (shallow, `--depth 1`) into `D:\Kannan-Projects\NoLoop\.references\` per user decision (spec §3 Round 2) — all 8 directories verified on disk.
  2. Extracted per-repo HEAD commits, last-commit dates, and LICENSE files. **License verification produced corrections vs the research pack:** jobsync = MIT (upgraded from UNVERIFIED), AutoApply = MIT (upgraded), jobmatch-ai = MIT (confirmed), JobMatchAI extension = NO LICENSE FILE FOUND (downgraded from the research pack's "MIT as stated" → IDEAS-ONLY — proof PROVENANCE verification matters), aipply / ai-job-application-bot / job-apply-bot = no license → IDEAS-ONLY, Job_Scraper = AGPL-3.0 confirmed (662-line license text).
  3. Created `.references/PROVENANCE.md` — authoritative provenance record: commit hashes, dates, verified licenses, reuse verdicts (3× MIT-SNIPPETS-OK, 4× IDEAS-ONLY, 1× AGPL-NO-COPY), per-repo study guide, checkout rules, AGPL contamination check command.
  4. Created root `.gitignore` (protects `.references/`, `.venv/`, secrets, user data, build artifacts; ENVIRONMENT contract; LOOP-1 exit criterion).
  5. Created `No_Loop_docs/CODING_STANDARDS.md` — full canonical coding standards: toolchain policy (ruff format+check, mypy strict in domain, pytest + coverage gates), layout laws (domain purity, vendor-name gate, module size), typing standards, error taxonomy (stage/reason/retryable/user_action/diagnostic_id), async & bounded-concurrency rules, data/persistence standards (profile_id discipline, WAL, reversible migrations, index-per-query), security coding standards (SSRF guard helper mandate, magic-byte sniffing, consent points, subprocess/exec ban), testing standards (no-AI suite, network marks, flaky=bug, real-send ban, benchmark honesty), documentation standards (i18n string-ID rule), dependency procedure, reference-adoption workflow, git/CI standards, and the §13 "Definition of clean" checklist.
  6. Initialized `docs/ATTRIBUTIONS.md` (append-only registry with entry template + pre-approved source table mirroring PROVENANCE verdicts).
  7. Cross-linked: README index (+CODING_STANDARDS row, reference-library note, interview-spec note), LOOP-1 (steps 2/4/5/7 now reference CODING_STANDARDS gates and .references verification), LOOP-9 (new step 6 contamination check for ATTRIBUTIONS + AGPL).
- Files changed: `.gitignore` (new); `.references/` (8 clones + PROVENANCE.md, gitignored); `No_Loop_docs/CODING_STANDARDS.md` (new); `No_Loop_docs/README.md`, `No_Loop_docs/LOOPS.md` (edits); `docs/ATTRIBUTIONS.md` (new); `DEVELOPMENT_LEDGER.md` (this entry)
- Tests run: none (infrastructure + docs only; no app code exists yet)
- Lint/types: n/a
- Unresolved issues: 5 repos lack license files (IDEAS-ONLY enforced until owners add licenses); shallow clones — to update, delete + re-clone + update PROVENANCE.md the same session; ADR-6 remains the first ADR to execute (M1)
- Architectural decisions: reference study physically realized on D: per R-ENV-6; AGPL repo permanently ideas-only; coding standards now the third binding authority after AGENT_RULES and MASTER_SPEC
- Dependencies added/removed: none
- Security impact: positive — license verdicts are now evidence-based rather than claimed; AGPL contamination guard lives in LOOP-9; .gitignore protects secrets/references from day one
- Performance impact: none
- Environment audit: git used only for read-only clones inside the project on D:; no C: writes; no packages installed anywhere; no lock file changes
- Evidence: `git rev-parse HEAD` outputs and LICENSE file heads recorded in `.references/PROVENANCE.md` (jobsync/AutoApply/jobmatch-ai = "MIT License" headers; Job_Scraper = "GNU AFFERO GENERAL PUBLIC LICENSE"); `ls .references` shows all 8 directories; ledger history itself documents the build steps.

### [2026-09-28, coding-start] LOOP-1 bootstrap + LOOP-2 first domain models — coding begins
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Loop(s) executed: LOOP-1 (bootstrap), LOOP-2 (errors, facts, profile, jobs, applications), Closing Checklist
- Task: Make the project runnable: tooling config, venv on D:, CI, and the first five domain modules with their invariant tests (CODING_STANDARDS applied from line one).
- Files changed:
  - pyproject.toml (new: deps + ruff/mypy/pytest/coverage config)
  - scripts/devenv.ps1, scripts/devenv.sh (new: ENVIRONMENT §2 env vars, D: caches)
  - requirements.lock.txt (generated, header-marked)
  - .github/workflows/ci.yml (new: format/lint/types/tests + domain-purity + vendor-name + .gitignore-integrity gates)
  - app/__init__.py, app/domain/__init__.py, app/domain/errors.py, app/domain/facts.py, app/domain/profile.py, app/domain/jobs.py, app/domain/applications.py (new)
  - tests/__init__.py, tests/unit/__init__.py, tests/unit/test_errors.py, tests/unit/test_facts.py, tests/unit/test_profiles.py, tests/unit/test_jobs.py, tests/unit/test_applications.py (new)
  - No_Loop_docs/PROGRESS.md (P001 DONE, P002 IN_PROGRESS with evidence)
- Reason: development was declared startable; LOOP-1 + first LOOP-2 slices chosen per DEVELOPMENT.md build order (stages 1-2).
- Tests run: pytest (59 tests) — all pass. Suites: error taxonomy (incl. policy/consent/automation stops), fact ledger (provenance mandatory, confidence-1.0 reserved for user entry, rejected facts terminal, immutability), profiles (limits gate: no silent caps; fully-configured required; targeting validation; multi-profile scoping), jobs (fingerprint stability, URL allowlist, salary ordering, PolicyStatus taxonomy), applications (R-TRUTH-5 evidence rule, automated-consent gate, §17 FAILED record, terminal states, manual Quick-Add default status, URL validation).
- Test results: 59 passed, 0 failed.
- Lint/types: ruff format --check clean (14 files); ruff check "All checks passed!"; mypy "Success: no issues found in 14 source files" (strict in app/domain per CODING_STANDARDS).
- Unresolved issues: remaining domain entities (JobCluster, MatchResult, ConsentEnvelope, AutomationRun, AuditEvent, EmailDraft, ApplicationArtifact, ResumeDocument, JobSource, Setting) → next LOOP-2 rounds; ADR-6 (DB benchmark) still first ADR for P003; mypy version resolved to 2.3.1 (works, recorded).
- Architectural decisions: enums use enum.StrEnum (UP042); Application state machine validates transitions + evidence + consent invariants in the domain layer itself (not the service layer) so no caller can bypass them; manual Quick-Add defaults to REVIEW_REQUIRED (never DISCOVERED — manual entries never re-enter discovery); domain validator normalizes blank titles/companies with explicit error; fingerprint = sha256 of normalized title|company|description (S8 key 4).
- Dependencies added/removed: pydantic, sqlalchemy, httpx, selectolax, rapidfuzz (+pytest/pytest-asyncio/pytest-cov/ruff/mypy as dev tooling) — all into .venv on D:; lock delta recorded in requirements.lock.txt.
- Security impact: domain enforces http(s)-only source/application URLs; PolicyStatus taxonomy present in domain; error taxonomy prevents silent failures (every error carries stage/reason/retryable/user_action/diagnostic_id).
- Performance impact: none measured yet (pure domain code; benchmarks start with P003+).
- Environment audit: no C: writes (venv + caches all on D:; PIP_CACHE_DIR=D:/DevCache/pip); no duplicate packages (single lock, capability-checked per ARCHITECTURE register); no new packages beyond declared set.
- Evidence: pytest "59 passed"; mypy "Success: no issues found in 14 source files"; ruff "All checks passed!"; domain-purity grep OK; vendor-name gate OK (after removing 'linkedin' from a docstring example in profile.py); venv check "venv OK on D:".

### [2026-09-28, rebuild] SELF-AUDIT + core pipeline built end-to-end (W1–W6)
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Loop(s) executed: SELF-AUDIT (skill 15 applied mid-build) + LOOP-3 (arbeitnow, jd_import, ai providers) + LOOP-4 (queue/ledger/export/CLI) + LOOP-5 (extractors + facts-from-resume) + LOOP-6 (match engine + dedup) + LOOP-7 (email drafter) + Closing Checklist
- Trigger: user challenge "you don't fully develop this as per the standards and not added as the cores we focusing on and you still not solving anything" — audit verdict: challenge CORRECT. Only 3/17 MASTER_SPEC capabilities were even partially built; no adapters, no matching, no CLI; "runnable" was overclaimed (R-TRUTH-1 self-violation). Full findings: No_Loop_docs/SELF_AUDIT.md.
- Capabilities closed (MASTER_SPEC §1): #7 discovery (arbeitnow adapter + JD/URL import + demo fixture source); #8 dedup (JobIdentityResolver, S8 5-key); #9 matching (MatchEngine: hard gate → weighted soft score); #10 explanation (MatchResult.explain() — factors + missing + notes); #1/2 resume import (TXT/DOCX extractors + honest PDF-unavailable path per pending ADR-2); #3 profile builder (facts → confirmed); #13 email drafting (rule-based + evidence map + 3 guards: specificity, confirmed-facts-only, certainty-spam ban); #17 ledger service (append-only audit + CSV/JSON export excluding consent refs); #14 CLI surface (10 commands, full pipeline runs offline).
- Files changed (new): app/ports/__init__.py; app/domain/matching.py; app/services/{match_engine,dedup,email_drafter,queue}.py; app/adapters/{__init__,extractors,facts_from_resume,fetcher,ai_providers,storage}.py; app/adapters/sources/{__init__,arbeitnow,jd_import}.py; app/cli.py; tests/contract/{__init__,test_arbeitnow_adapter}.py; tests/integration/{__init__,test_pipeline}.py; tests/fixtures/arbeitnow_page1.json; No_Loop_docs/SELF_AUDIT.md. (Modified): app/domain/__init__.py; pyproject.toml (asyncio_mode=auto; per-file ignores).
- Tests run: pytest — 91 passed, 0 failed (59 prior domain + 32 new: arbeitnow contract vs fixture incl. sanitization+policy metadata; dedup merge/provenance; matching gates/factors/notes; email guards G1-G3 incl. inferred-fact exclusion; queue caps/threshold/cooldown/hours/limits-gate; ledger audit append-only; export exclusion). Live-network smoke marked @network (skipped by default).
- Real bug found and fixed by live CLI run: naive-vs-aware datetime comparison crashed the recency gate; fixed via _to_utc() normalization with documented assumption + tests. Also fixed: quick-add transition now passes user-assertion evidence (domain invariant correctly rejected the shortcut — proof the R-TRUTH-5 enforcement works at runtime).
- CLI end-to-end evidence (offline): create-profile → set-limits (queue gate) → demo-discover (4 jobs, deduped) → match (5 jobs scored with factor breakdowns + missing lists) → import-resume (6 inferred facts + confidence + contact) → confirm-facts → import-jd → draft-email (job-specific, 10 confirmed facts referenced, specificity all true) → quick-add → export CSV. All commands exited 0.
- Lint/types: ruff format --check clean; ruff check "All checks passed!"; mypy "Success: no issues found in 35 source files" (strict domain).
- Dependencies added/removed: none (httpx/selectolax/rapidfuzz now actually USED — were declared earlier).
- Architectural decisions: ports use runtime_checkable Protocols + generic taxonomy kinds (adapter_id opaque, R-ARCH-3); adapters return ExtractionResult instead of raising for honest unavailability; arbeitnow discovery bounded (max 5 pages, 2s delay, UA identified); storage = JSON-file behind swappable port pending ADR-6 (declared in module docstring, NOT a silent placeholder); match engine deterministic-only, taxonomy normalizer swap-point isolated.
- Security impact: SSRF-guarded fetcher (scheme allowlist, DNS private-range block, 5MB cap, redirect re-validation) is the only HTTP path; HTML sanitized via selectolax before storage; file caps 10MB; email guards ban certainty-spam.
- Performance impact: not yet benchmarked (LOOP-10 next; no invented numbers).
- Environment audit: no C: writes (all data in .local-data on D:, cleaned after test); no new packages; lock unchanged.
- Unresolved issues: PDF extraction blocked on ADR-2 (honest refusal shipped); BYOK Gemini Tier-2 adapter pending; persistence is JSON pending ADR-6 benchmark; UI shell ADR-1 pending; LOOP-10 benchmarks pending; live-source POLICY_STATUS re-verification due at next LOOP-12.
- Evidence: pytest 91 passed; mypy/ruff clean; CLI transcripts in session log; .local-data written and then removed (privacy hygiene).
