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


### [2026-09-29 22:25] UI/server hardening + live end-to-end verification + engine None-targeting fix
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Loop(s) executed: LOOP-4 (UI services) + LOOP-9 (review of handler logic) + Closing Checklist; live smoke run against real arbeitnow API
- Task: finish interrupted Gemini/settings/UI/question-answerer/platform-policy/resume-edgecase wave; fix all lint/type debt; verify the full stack live.
- Files changed: app/domain/errors.py (SourcePolicyError/ConsentRequiredError/AutomationBlockedError/ProviderUnavailableError: kwargs-collision fixed — subclass defaults no longer clobber caller values); app/ui/server.py (kanban move evidence bug: compared str target vs enum → evidence always None → domain refused; convenience flat profile keys → TargetPreference; _record_task_failure — background tasks can no longer fail silently; typed sort in _run_match); app/services/match_engine.py (targeting=None tolerated: gate PASS + neutral TargetPreference("any") fallback for factors); app/adapters/system_probe.py (os.sysconf absent on Windows — getattr guard); app/services/ai_registry.py (_path_exists str|None; stale ignore removed); app/services/question_answerer.py (contextlib.suppress); app/services/reports.py (line length); tests/integration/test_ui_server.py (unused var).
- Real bugs found by live run (not by tests): (1) kanban evidence bug above — domain correctly refused, UI was at fault; (2) profiles created without nested targeting silently no-op'd matching; (3) MatchEngine(targeting=None) crashed in _gate/_score_factors.
- Live evidence: server boots on 127.0.0.1; SSE stream verified with curl (-N); Gemini key saved write-only (backend=file); profile with targeting persisted; arbeitnow LIVE discovery → 27 real jobs stored; match over live jobs: hard gates correctly fail German-onsite roles vs Chennai/Remote targeting; resume import → 6 inferred facts → bulk-confirm → engine rerun shows confirmed-skills lift (quant role with Python/SQL: 0.50). All over the HTTP API, no test fixtures.
- Tests run: pytest — 139 passed, 0 failed. Lint/types: ruff check "All checks passed!", ruff format clean, mypy --no-incremental "Success: no issues found in 40 source files".
- Unresolved issues: real-browser UI pass (manual); assisted-flow package UI wiring; SSE backpressure benchmark (LOOP-10); Gemini key against real API endpoint (needs user key); PDF/DOCX rendering (ADR-7); SQLite (ADR-6).
- Environment audit: .smoke-data/.smoke.log/.local-data removed after verification (privacy hygiene); no C: writes; no new packages.

### [2026-09-29 23:10] Capability audit (star-wise) — IMPROVEMENT_AUDIT.md
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Task: star-wise audit of all capabilities vs actual code state.
- Method: read every service/adapter/route file; traced endpoint wiring (JS→API), provider usage, and pipeline integration; verified test count and gate status.
- Key findings: settings.js route registered but MISSING (P0 UI bug); agent_run.py hardcodes RuleBasedProvider (user's Gemini key never used in drafting); resume_edgecases not wired into resume_pipeline (only profile_service); sources are Germany-heavy for an India-first product; ADR-6/ADR-2 still open.
- Evidence: 17 capabilities rated from code inspection; ratings and file-level evidence in No_Loop_docs/IMPROVEMENT_AUDIT.md.
- Next: 5 prioritized tasks listed in the audit (Settings fix first).


### [2026-09-29 23:59] Audit tasks 1-5 executed in parallel (settings UI, AI registry, PDF, sources, package viewer)
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Task: execute all 5 recommended improvements from IMPROVEMENT_AUDIT.md.
- T1 settings.js: created the route registered in app.js (was MISSING — P0). Gemini key write-only form + model picker, provider selector with fallback help, per-profile limits editor, system diagnostics panel. Module verified via node import (render exported).
- T2 AI through registry: GeminiProvider gained sync generate() bridge (EmailDrafter/QuestionAnswerer are sync callers — even a wired Gemini previously would have crashed); AgentRunService now resolves the provider via AIRegistry (gemini->local->rule, never raises); server passes settings into the service. The user's Gemini key now actually drives drafting.
- T3 PDF (ADR-2 closed): pypdf 6.19.0 (BSD-3) chosen over PyMuPDF (AGPL - forbidden by R-TRUTH-6) and pdfminer.six (slower); PdfExtractor replaces PdfExtractorUnavailable (magic-byte check, encrypted-PDF refusal, 50-page bound, per-page isolation, scanned-document honest error); verified end-to-end: generated PDF -> text -> 7 inferred facts; attribution recorded in docs/ATTRIBUTIONS.md.
- T4 sources: remotive adapter (public API, remote jobs incl. India, sanitize tests) + adzuna-IN adapter (user's free app_id/app_key via settings + secret store, never hardcoded; INR salary currency); /api/discover now takes source + query; /api/settings/adzuna stores credentials. Live smoke: remotive + adzuna both returned jobs (9 stored).
- T5 assisted-package viewer: GET /api/assisted-packages (+ api.assistedPackages); per-card file icon opens modal with policy status label, steps checklist, ready answers with copy buttons, needs-user items flagged, email draft with copy, you-click-submit reminder. LinkedIn/Indeed compliant flow now human-usable.
- Tests run: pytest — 145 passed (6 new: PDF extract/magic/scanned + remotive parse/sanitize + adzuna credentials/parse). Lint/types: ruff clean, ruff format clean, mypy "Success: no issues found in 42 source files".
- Live evidence: server up on 127.0.0.1:8880; /api/meta ok; discover source=remotive and source=adzuna both accepted; assisted-packages endpoint returns; settings.js verified as importable module via node.
- Dependencies added/removed: +pypdf>=5.0 (pyproject + lock refreshed; all into .venv on D:, PIP_CACHE_DIR=D:/DevCache/pip).
- Environment audit: smoke data/server cleaned; no C: writes; no duplicate packages.
- Unresolved: real-browser click-through of settings + package viewer (module-level verified); Gemini live call needs the user's key; remoteok needs policy verification before adapter work; SSE backpressure benchmark (LOOP-10).

### [2026-09-30 00:20] Reference gap analysis + platform automation map — REFERENCE_GAP_ANALYSIS.md
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Task: identify what we importantly missed vs the 8 reference repos; map platform/company-portal automation per policy.
- Method: re-read all 8 .references READMEs + AutoApply apply/ module layout; cross-checked DATA_SOURCES §1.9 policy statuses and R-POLICY rules; 2026 web research on auto-apply tools + India portals (LinkedIn/Naukri ToS enforcement, Instahyre/Cutshort/Wellfound landscape).
- Key findings: 12 gaps rated (A1-A12); biggest: document rendering (ADR-7 blocks 3 features), Knowledge Base with TF-IDF reuse (AutoApply, MIT), ATS text-similarity score. Platform map: LinkedIn/Naukri = PROHIBITED (assisted only, ever), Indeed/Instahyre etc = ASSISTED_ONLY, ATS portals (Workday/Greenhouse/Lever/Ashby) = the lawful fill-only sweet spot with MIT reference code available from AutoApply.
- Honest note recorded: all auto-submit reference tools violate platform ToS (AutoApply admits it in its own README line 212); our assisted/fill-only posture is the differentiator, not a limitation.
- Evidence: No_Loop_docs/REFERENCE_GAP_ANALYSIS.md (Parts A-D with priorities).

### [2026-09-30 01:20] Priorities 1-6 executed (ADR-7 renderer, KB+TF-IDF, ATS plans, answer sheets, scheduler, employer intel)
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Task: execute all six priorities from REFERENCE_GAP_ANALYSIS Part D.
- P1 ADR-7 EXECUTED: reportlab 5.0.1 (BSD) + python-docx 1.2.0 (MIT) chosen (weasyprint heavy, PyMuPDF AGPL-forbidden); renderer.py renders ATS-safe resume PDF + resume DOCX + interview-prep-pack DOCX; both promoted to core deps in pyproject (stale AGPL pymupdf extra removed); attribution recorded.
- P2: domain/knowledge.py — KBEntry (project/achievement/story/blurb/certification, user-asserted, reuse counter), tech-token-aware tokenizer (c++, ci/cd kept whole), tfidf_rank (IDF over entry corpus, cosine vs JD); resume_builder.py — ResumeAssembler (facts+KB->doc; KB entries quoted verbatim, never invented), ats_score (TF-IDF cosine resume-vs-JD), tailoring_suggestions (missing terms with explicit do-NOT-claim guard).
- P3: greenhouse.py adapter (public boards API: discovery + per-job question schema; ALLOWED_PUBLIC_API declared); apply_sheets.ATSFillPlanner — fill plans from question schema, file-upload fields honestly excluded, record_fill/reliability with the documented v0.2 gate (>=98% over >=50 fills).
- P4: build_answer_sheet — LinkedIn Easy-Apply 5-question set + Naukri 8 recruiter fields, answers only from the fact sheet (needs_user flagged otherwise), JD-skill substitution in the Easy-Apply skill slot; /api/answer-sheet; platform allowlist enforced. NO browser automation against PROHIBITED platforms (R-POLICY-3).
- P5: scheduler.py — persisted per-profile schedules (30min-24h bounds), 60s daemon tick, one profile per tick, discover+match only, all caps still enforced, nothing auto-submits; /api/schedule.
- P6: employer_intel.py — per-company report (applications, outcome breakdown, interview rate, avg days-to-response) from the user's OWN ledger + user-authored notes; top-companies view; /api/company/intel + /api/company/top.
- Wiring: UILauncher handlers _profile_and_facts (shared validation), kb save/delete, render resume/prep-pack, ats plan, answer sheet, schedule, company intel/top; 10 new POST routes registered.
- Live evidence (all over HTTP on 127.0.0.1:8890): profile->KB entry->resume import->5 facts confirmed->resume PDF 1841 bytes starting %PDF with ATS score 0.3989->prep pack 36995 bytes->LinkedIn sheet filled:2/needs:3->Naukri 8 entries->ATS plan fillable:1/needs-user:1 (file upload correctly excluded)->schedule 60min->intel note recorded.
- Tests run: pytest - 291 passed (52 new since the last wave; new file test_knowledge_docs_sheets.py covers TF-IDF ranking/cosine/KB invariants, builder+ATS, PDF/DOCX/prep-pack rendering incl. %PDF and PK magic, planner incl. reliability gate, both sheets, scheduler persistence, employer intel). Lint/types: ruff clean, format clean, mypy "Success: no issues found in 50 source files".
- Dependencies added: reportlab>=4,<5 + python-docx>=1.1,<2 as CORE deps (ADR-7); types-reportlab dev-side; pymupdf extra removed (AGPL, superseded). Lock regenerated. All into .venv on D:.
- Environment audit: smoke data/server cleaned; no C: writes (PIP_CACHE_DIR=D:/DevCache/pip).
- Unresolved: KB/prep-pack UI editor screens (endpoints ready); Playwright fill executor for ATS plans (v0.2, gated on the reliability log); resume-rendered docs stored into resume_versions; scheduler UI toggle.

### [2026-09-30 02:05] Real-browser verification wave (agent-browser) + quick-add hardening
- Agent/model: Buffy (Codebuff, z-ai/glm-5.3-flash)
- Task: verify the P1-P6 surface in a real browser via the agent-browser skill; fix anything found.
- Setup: serve_ui on 127.0.0.1:8895 (fresh .local-data seeded via HTTP); agent-browser session on the app; snapshot/click/eval/screenshot loop.
- Verified in-browser: settings page full render incl. Gemini key save -> toast -> /api/state configured:true; profile creation via UI; kanban board columns; assisted-package modal opens with the honest "no package yet" notice and its Close button removes the dialog; quick-add API now rejects unknown profiles.
- Defect investigated (was believed broken): package-viewer modal "never opens" on trusted click. Instrumented live (window error + unhandledrejection + fetch capture + document-level click capture): handler, fetch (200) and modal append all work when the button node is fresh. Root cause of the false alarm: agent-browser trusted clicks land on document.documentElement in this environment (elementFromPoint mismatch; outer window 1280x720 vs OS-reported screen 800x600), so refs that survived a DOM change still received nothing — a test-harness artifact, NOT app code. Re-routed verification through eval-driven clicks; flow proven end-to-end.
- Fix 1 (hardening, not a bug): openPackageViewer used querySelector("dialog.modal:last-of-type") to grab the dialog; now uses modal()'s return value like sibling call sites, and returns dlg.
- Fix 2 (real defect): handle_quick_add accepted any non-empty profile_id, creating ledger records scoped to nonexistent profiles. Now returns {"ok": false, "error": "profile not found"} when the store has no such profile (house style per _profile_and_facts). Verified: POST /api/applications with profile_id "none" -> rejected; server restarted for the change.
- Git note: P1-P6 landed earlier in 52002be (checkpoint) — the ledger entry above predates that commit's push; current dirty tree is the separate resume-processing upgrade workstream plus the two fixes above (server.py, applications.js).
- Honest note: trusted-click verification of modals is unreliable under agent-browser on this machine; eval-driven clicks + node-persistence probes are the reliable protocol. Recorded so the next agent does not re-chase the same ghost.
- Cleanup: browser session closed (--all), 8895 server killed, smoke logs/screenshots/.local-data deleted; no C: writes.
- Unresolved: resume-processing upgrade workstream uncommitted (not this wave's scope); KB/prep-pack UI screens; scheduler UI toggle; ATS fill executor (v0.2 gate).


### [2026-09-30 07:55] Resume-processing upgrade P0-P2 core + golden evaluation harness
- Agent/model: MiMo-V2.6-Flash (opencode)
- Task: write No_Loop_docs/RESUME_PROCESSING_UPGRADE.md (analysis first), then implement its P0-P2 core across extraction, parsing, pipeline, matching and UI. Full git push taken before starting (f2d0836..52002be).
- Analysis doc: scorecard, 7-layer gap analysis (L1 layout .. L7 eval), target architecture, P0-P3 roadmap, eval-harness design, 10 UX suggestions, 14 references (EDLIGO 2025 ATS failure rates, ATSChecker 2026, ESCO skills extractor, etc.). Implementation status table added at the top once the work landed.
- L1 extractors.py: pypdf visitor API gives (x, y, size) -> line clustering -> gutter detection (75th-percentile left extent ignores full-width headers) -> column split BEFORE y-clustering; ordered text is a no-loss upgrade only (falls back to plain when it holds <60% of words). DOCX now walks document body order (paragraphs were all listed before the tables). page_offsets so facts carry provenance.page.
- New modules: skill_taxonomy.py (148 canonical skills / 293 surface forms, boundary-safe, ambiguity gating for prose words like "go", dedupe key = canonical so first provenance wins, ESCO URIs deliberately None), resume_sections.py (exact alias -> fuzzy with remainder rule -> unknown-but-standalone headings, all with body spans), resume_records.py (dates/tenure month-accurate, employment, education with strict corroboration, certifications with hint mode, projects), parseability.py (MASTER_SPEC 13-group coverage + ATS-style parseability score with per-flag fixes).
- facts_from_resume.py rewritten around those layers: 9 -> 26 facts and coverage 77% on the workstream sample; every fact carries span (+page for PDFs), summary falls back to the first prose line under the header, phone matcher rewritten to candidate regexes with 10-15 digit validation (the old pattern missed "+34 612 34 56 78" and swallowed newlines), awards under CERTIFICATIONS & AWARDS reclassify to achievement, whole-document fallbacks are gated (employment needs a title-looking fragment, education needs >=2 corroborating elements, tenure never reads a degree span as work).
- Pipeline/UI: resume_pipeline window selection + source_text grounding (0.9 rule+LLM / 0.7 LLM-only / 0.8 legacy), match_engine canonicalises both sides, profile_service stores resume_documents (structure only, still no raw text), real imported_at, coverage/parseability/document_id in ImportResult; resume.js and profile.js show coverage + ATS score.
- Evaluation harness (the multiplier): tests/fixtures/resumes/cases/{standard-india, fresh-grad, nonstandard-headings, international-es, no-headings} each with a HAND-WRITTEN gold.json (ground truth verified against resume.txt by eye, never copied from parser output); tests/benchmarks/golden_scoring.py computes micro field P/R/F1; scripts/bench_resume.py prints the report. Result: micro F1 0.997 (precision 1.000, recall 0.993, 147 tp / 0 fp / 1 fn). Gates: MICRO_F1_FLOOR 0.90, CASE_F1_FLOOR 0.85, plus a zero-hallucination rule (any fact not in gold fails), so a bad alias can never slip through quietly.
- Defects the harness + fixtures caught and fixed: taxonomy aliases "rails" -> ruby on rails from "payment rails" and bare "oracle" from "Oracle Certified Associate"; phone line read as education; "B.Tech Computer Science" read as an employer; tenure 4.0 invented from a student's degree span; summary equal to name+email; B.S./M.A. dotted degrees never matched; ES section headings absent; section confidence hardcoded to 1.0 so fuzzy headings looked exact.
- Tests: 368 passed (48 new: test_skill_taxonomy, test_resume_sections, test_resume_records, test_layout_extraction incl. a reportlab 2-column PDF, plus 7 golden benchmark tests). ruff clean, ruff format clean, mypy Success (54 files). benchmark suite exits non-zero below the floor.
- Known gap left visible in gold rather than papered over: nonstandard-headings misses the project under the invented heading "SOME THINGS I'VE BUILT" -> content-based section classification is next on this thread.
- Docs: IMPROVEMENT_AUDIT rows 8 (resume handling -> 4 stars), 15 (test count), 17 (matching engine -> 5 stars) and suggested task 3 (marked DONE) refreshed; RESUME_PROCESSING_UPGRADE.md gained the implementation-status table.
- Unresolved: P2.13 local small-model tier, P2.14 OCR extra, P3 multilingual (ES/PT heading + title seeds only), P3 ATS self-panel, source-highlighted confirmation UI, resume import diff, content-based classification of unknown headings.

### [2026-09-30 20:00] Visual resume builder - first slice (GrapesJS, propose-only AI)
- Task: build the plan in No_Loop_docs/RESUME_BUILDER_PLAN.md - a #/builder route where the resume is a live, editable document using the exact structure the app already assembles, with the Settings-selected AI proposing pinpoint, grounded suggestions per application (propose-only; the human clicks Apply).
- Vendored (local-first): scripts/vendor_grapesjs.ps1 pulls the two npm tarballs once -> app/ui/static/vendor/grapesjs/ (GrapesJS 0.23.6 + preset-newsletter 1.0.2, BSD-3-Clause, UMD, committed). No CDN, no build step, no network at runtime. The preset resets GrapesJS's panels, so opts.blocks: [] drops the newsletter blocks and one "Resume" category remains: Text / Bullets / Job entry / Skill chips / Divider.
- Backend: builder_template.py (render_skeleton with data-nl-path leaves -> bound_values -> diff_overrides -> merge_doc -> section_order / html_export / text_export), builder_ai.py (prompt, JSON parse, grounding gate, local_suggestions for the no-key tier), builder_service.py (bootstrap / list / save variant / save template / suggest / apply / export over JsonStore resume_templates + resume_variants, key profile_id[:application_id]); 7 routes added to ui/server.py plus _LARGE_BODY_PATHS (20 MB) for the two save routes. bootstrap.structure tolerates unknown section names, so a hand-added section can never 500.
- Frontend: js/core/grapesjs_loader.js (idempotent load, unloadGrapesJS on route:leave), js/routes/builder.js (init over the preset, bound components, 900 ms chained autosave with client-side markup cleanup, AI panel, structure panel with move up/down, export modal), api.js (7 methods), i18n builder.* keys, css/builder.css, nav entry, storageManager:false so no resume copy lands in localStorage.
- Propose-only is enforced, not promised: a card renders Apply only when proposed is non-empty; the rule tier ships filler-bullet rewrites with EMPTY proposed (pointed at, never ghost-written) plus one ATS note that says "do NOT claim them"; apply stores the path/proposed as an override with an audit event, then the canvas re-renders from the merged doc.
- Honest deviations (all recorded in plan section 12): bootstrap returns structure only, so an unbound block the user drops on the canvas does not come back on reload (overrides and section order do - disclosed in builder.structureHint); ATS text export uses a new text_export() because ResumeAssembler.resume_text is the flat scoring string and would ship a resume with no email or dates; only the Resume block category (no CMS); Style Manager not wired yet; the GrapesJS chrome stays dark in the light theme.
- Verified in the browser against a seeded data dir: boot with zero console errors -> type into a bullet -> 900 ms save -> override_count 1 -> type the fact back -> override_count 0 (a diff, not a history); Experience moved above Skills persists and drives every export; Suggest returns 4-5 cards; Apply (fetch response intercepted to stand in for a configured provider) -> toast + override; leaving the route mid-edit saves before teardown and removes the GrapesJS CSS/debug handle; a per-application variant shows ATS 26% + JD-driven suggestions; all four exports downloaded (html 12 KB, pdf 2 KB, docx 37 KB, txt with contact + employers + periods).
- Gates: pytest -q green, ruff check clean, ruff format clean on every file touched (repo-wide it still flags only the uncommitted app/adapters/gemini_provider.py), mypy "Success: no issues found in 57 source files", node --check clean on the five changed JS files. Slice suites: tests/unit/test_builder_template.py, tests/unit/test_builder_ai.py, tests/integration/test_builder_api.py.
- Not done (P3, listed in the plan): template gallery UI, Style Manager on CSS vars, persisting unbound canvas blocks, a11y pass on the preset's icon buttons, dark-chrome theming.
