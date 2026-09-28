# NOLOOP_DEV_KICKOFF-spec.md
**Request short name:** Reference Audit & Development Kickoff (v0.1)
**Date:** 2026-09-28
**Status:** SPEC — approved for implementation planning; no code written yet
**Supersedes/amends:** listed per section; changes to canonical docs are itemized in §12

---

## 1. Original request (verbatim intent)

> "please review the references sources and codes thats we have from the github links and all that is usefull and which will we let the ai to look and use thats and make an full audit quick and make an full developements startable also make sure what db we gonna use ? cause if we let the people to use this they will not have need to install and use an db for them and we not host this and have their data right and reanalsye all the stacks and defined and coding statndared and the guidence to the ai as to always if need go live internet and read and learn the code and use that."

Decomposed into five workstreams:
1. **W1 — Reference audit:** review the 8 GitHub reference sources in `No_Loop_Open_Source_Reference_Research/`, determine what is useful and what the AI may look at/use.
2. **W2 — DB decision:** pick the embedded database so end users never install one and we never host their data.
3. **W3 — Make development startable:** everything needed for the AI (or a human) to begin real development immediately.
4. **W4 — Re-analyze stacks, coding standards, AI guidance:** refresh ARCHITECTURE/standards so the AI always knows it may go to the live internet to read, learn, and use code (within license/security gates).
5. **W5 — Spec it:** capture all decisions in this file before implementation.

---

## 2. Audit results — the 8 reference repositories (W1)

All 8 repos were re-verified live on 2026-09-28 via web search (direct GitHub fetch is sandboxed on this machine; verify license files again when cloning — §5).

| # | Repo | Verified | License (stated/observed) | Useful to No_Loop | Reuse posture |
|---|---|---|---|---|---|
| 1 | Gsync/jobsync | ✅ exists | Unverified — check on clone | Tracker + AI resume review; **provider adapter pattern** (Ollama/Deepseek) "made adding Ollama trivial"; pluggable job extraction (JobSpy, Gradcracker, UKVisaJobs); self-hosted; backup/restore | Ideas; snippets only if MIT confirmed |
| 2 | SamlyticsDS/jobmatch-ai | ✅ exists | MIT (stated in repo) | Board scanning, resume-fit scoring, **tailored ATS-friendly CV generation**, tracker, SQLite-local architecture | MIT snippets allowed with attribution |
| 3 | attdobi/aipply | ✅ exists | Unverified | Playwright browser automation structure; LinkedIn flow (pattern only — implementation FORBIDDEN, LinkedIn = PROHIBITED per DATA_SOURCES §1.9) | Ideas only |
| 4 | AbhishekMandapmalvi/AutoApply | ✅ exists | Unverified | Multi-ATS workflow decomposition (Greenhouse/Lever/Workday/Ashby), knowledge-base + deterministic retrieval, local-first | Ideas; snippets if MIT confirmed |
| 5 | wadekarg/JobMatchAI | ✅ exists | MIT (stated) | Page-analysis UX, skill-gap view, auto-fill convenience layer, extension-context thinking | MIT snippets allowed with attribution |
| 6 | ScottCoffin/Job_Scraper | ✅ exists | **AGPL-3.0 (stated)** | Config-driven sources, dedup, salary normalization, triage dashboard, zero-server operation | **Reference-only. ZERO code reuse** (AGPL contamination risk under Apache-2.0 project) |
| 7 | Vigneshyadala/ai-job-application-bot | ✅ exists | Unverified | Gemini integration shape; 0–100 fit score + auto-apply above threshold (validates our S1); success verification after submit; daily limits; 15+ platform claims (to be studied skeptically) | Ideas; snippets if MIT confirmed |
| 8 | dsharm9148/job-apply-bot | ✅ exists | Unverified | scrape→tailor→apply→log pipeline separation; application threshold; evidence logging | Ideas; snippets if MIT confirmed |

**Audit verdict:** ecosystem validates No_Loop's strategy set (thresholds, local/BYOK AI, tracking, adapters, dedup). Two repos are MIT-confirmed; one is AGPL (hard no-copy); five licenses unknown until clone. **ToS-violating implementations (LinkedIn auto-apply) are studied for architecture only, never ported.**

---

## 3. Interview decisions (22 answers, 6 rounds — all binding)

### Round 1 — Database & data ownership
| Question | Decision |
|---|---|
| Which embedded DB? | **AI decides via ADR** — benchmark SQLite vs DuckDB vs alternatives; record ADR-6 with numbers |
| Where does user data live on their machine? | **User chooses at setup** — default per-user app-data folder + "Portable data" toggle in Settings that relocates the data dir |
| Backup safety net? | **Manual export only** — user-triggered export; nothing automatic |

### Round 2 — AI use of references & internet
| Question | Decision |
|---|---|
| How far may AI use reference code? | **Clone & study all 8** locally on D:; write our own code; **MIT snippets allowed with attribution** |
| When does live-web access happen? | **Aggressive everywhere** — AI re-verifies policies/docs at every session start AND may pull code examples from the web while coding |
| May AI clone repos locally? | **Yes** — into `D:\Kannan-Projects\NoLoop\.references\` (gitignored), read-only study, never copied into app code |

### Round 3 — Product scope
| Question | Decision |
|---|---|
| v0.1 scope? | **Full loop + one automated path** (refined in Round 6 to fill-only) |
| Market focus first? | **India-first** — locations/salary/notice-period defaults; global boards still available |
| Update checks & crash telemetry? | **Both opt-in, OFF by default** |
| Distribution? | **Portable .zip from GitHub Releases** — no installer initially |

### Round 4 — Edge cases & guardrails
| Question | Decision |
|---|---|
| Multiple candidate profiles? | **Multiple profiles** (e.g. "Python Developer" AND "ML Engineer", each with own resume/targeting/tracker, switchable) |
| Scanned/image-only PDFs? | **Clear error, no OCR in v0.1** — "No text found — this looks like a scanned image. Export a text PDF or paste your resume text." |
| Auto-apply cap defaults? | **User sets everything from zero on first run** — no silent defaults; caps/thresholds are a mandatory onboarding step |
| Language scope? | **Multilingual UI** (refined in Round 5) |

### Round 5 — Multilingual & artifacts
| Question | Decision |
|---|---|
| Which languages, how? | **English + Tamil + Hindi shipping together** |
| Tailored resume output format? | **DOCX + PDF both** (editable + upload-ready; adds a PDF-writer dependency) |
| First BYOK AI provider? | **Gemini first** (matches reference bots + original idea; free tier; one provider done well) |
| Definition of "startable"? | **Full v0.1 built first** — one complete delivery before the project is called started |

### Round 6 — Automation, ledger, AI code-gen, OS
| Question | Decision |
|---|---|
| Auto-submit comfort on Greenhouse forms? | **Fill-only in v0.1** — auto-fills the form, user clicks Submit; full auto-submit deferred to v0.2 after field-reliability work |
| Ledger scope? | **ALL applications** — including fully manual ones, tracked through offer/reject (complete job-search command center) |
| AI live-learning rule while coding? | **Wide net** — may pull and adapt code found anywhere, WITH license check + security review before merge |
| OS scope for v0.1? | **Windows 10/11 x64 only** |

---

## 4. Database specification (W2 — ADR-6)

### 4.1 Hard constraints (from product principles + user)
- End users **never install** anything DB-related; the DB is embedded and invisible.
- **We never host user data** — no server, no sync account, no telemetry of content. Data exists only on the user's machine.
- 2 GB RAM baseline; single-file portability preferred for the Portable mode.

### 4.2 ADR-6 candidates and evaluation criteria
| Candidate | Strengths | Risks |
|---|---|---|
| **SQLite (via SQLAlchemy Core)** | Built into Python's ecosystem, single file, WAL mode, proven at low RAM, simplest packaging, universal tooling | Weaker analytics (not needed) |
| **DuckDB** | Strong analytics, columnar, single file | Larger binary, OLTP-appropriate? No — designed for analytics; app data is transactional; higher RAM use |
| **SQLite + SQLModel** | Ergonomics | Extra layer; lean-memory concern (open ADR-3 anyway) |
| LMDB / others | Fast KV | No SQL; would force hand-rolled indexing |

**Required benchmark protocol (LOOP-10, recorded in ADR-6):** DB lookup p50/p95 on 10k jobs; match batch on 1k rows; memory RSS after core flow on 2 GB-capped profile; on-disk size after 6-month simulated usage (~50 MB data); portable-copy test (data dir moved between drives/machines must keep working).
**Default expectation:** SQLite wins; the ADR exists to prove it with numbers, per the user's explicit choice.

### 4.3 Data ownership model
- Zero-knowledge by construction: no account, no cloud, no sync. The words "server", "sync", "cloud account" must not appear in product UI.
- Data location (user's choice at first run, changeable in Settings):
  - **Default:** Windows per-user app-data folder (`%APPDATA%\No_Loop\`).
  - **Portable toggle:** relocate data dir to a user-chosen folder (e.g. next to the .exe or a USB path). App must fully re-point (DB, artifacts, caches) and verify integrity after relocation.
- Manual export: one click → timestamped export (CSV + JSON + resume artifacts) to a user-chosen folder. This is the ONLY backup mechanism in v0.1 (user's explicit choice; document "backup is your job" in-app once during onboarding).
- Delete-all must remove: DB, artifacts, exports' index, caches — verified by test (LOOP-9).

---

## 5. Reference & live-internet usage specification (W1 + W4)

### 5.1 Local reference library
- Path: `D:\Kannan-Projects\NoLoop\.references\` — **gitignored**, never ships, never copied into `app/`.
- Contains: clones of all 8 audited repos + `PROVENANCE.md` recording for each: clone date, commit hash, LICENSE file content, reuse verdict (IDEAS-ONLY / MIT-SNIPPETS-OK / AGPL-NO-COPY).
- Rule: read-only study. Any snippet leaving `.references/` must pass §5.3 gates and be re-typed/adapted with attribution comment + license note in the target file.

### 5.2 Live-internet policy (aggressive, per user)
AI agents are expected to use the live internet continuously:
1. **Session start (every session):** re-verify any policy/API claim the session will touch (LOOP-12 mini-run): DATA_SOURCES.md §1/§1.9 statuses, endpoint shapes, rate limits. Drift found → update register + ledger before coding.
2. **While coding:** fetch official docs, real API response samples, library docs, and code examples from the web whenever uncertain.
3. **While researching:** public repo code, issues, changelogs are fair learning material.

### 5.3 The two gates on "wide net" code learning (user-chosen balance)
Even under wide-net learning, merged code must pass:
1. **License gate:** identify license of the source; MIT/Apache/BSD → allowed with attribution header (`# Adapted from <repo>@<commit> — MIT`); GPL/AGPL/unknown → ideas-only, no transcription; no license → treat as all-rights-reserved (ideas-only).
2. **Security gate (LOOP-9 checklist items 2,4,5,11):** no untrusted pasted code reaches a merge without review for injection vectors, network calls, obfuscation, and dependency duplication (R-ENV-3).
- Every adapted snippet is recorded in the ledger entry of the session (source URL, license, what changed).
- Attribution ledger maintained in `app/` docs: `docs/ATTRIBUTIONS.md`.

### 5.4 What the AI may NEVER do online (unchanged from AGENT_RULES)
Bypass CAPTCHA/anti-bot/paywalls; scrape PROHIBITED portals (LinkedIn, Naukri); login-walled content for research; leak user data anywhere; disable safety gates for speed.

---

## 6. v0.1 product scope (W3)

### 6.1 The full loop (all of this ships in v0.1)
```
Import resume (PDF/DOCX/TXT; scanned→clear error, paste-text fallback)
→ Parse → fact ledger (inferred vs confirmed) → confirm/reject/edit
→ Multiple profiles (create/switch; per-profile resume, targeting, tracker)
→ Onboarding: gap questions + MANDATORY limits setup (user sets every cap from zero)
→ India-first targeting defaults (Coimbatore/Chennai/Bangalore/Remote presets; ₹ salary; notice period)
→ Discovery: arbeitnow, remotive, remoteok, jobicy (no key) + adzuna (user key) + greenhouse/lever/ashby boards + URL/JD import
→ Normalize → 5-key dedup → Match Triangle (hard gate + soft score + explanation)
→ Threshold gate → queue
→ Generation: tailored resume (DOCX + PDF), cover letter, job-specific email draft (rule-based, zero-key)
→ Gemini BYOK optional path (Tier 2; key in OS keychain; privacy panel)
→ Greenhouse-hosted forms: AUTO-FILL ONLY (browser adapter fills; user clicks Submit)
→ All other portals: Assisted Flow (package + human submits + user records outcome)
→ Application Ledger tracks ALL applications (auto, assisted, fully manual)
→ Tracker board (DISCOVERED→…→OFFER/CLOSED) + manual export
→ Portable .zip distribution, Windows x64
→ EN + Tamil + Hindi UI
```

### 6.2 Explicit v0.1 exclusions (deferred)
- Full auto-submit (v0.2 — after field-reliability telemetry from fill-only runs)
- OCR (v2+ optional plugin)
- Linux/macOS builds (post-v0.1, community-assisted)
- Installer (Inno Setup) — arrives with v0.2; v0.1 is portable zip only
- Update checker + crash reporter — designed but shipped OFF-default in v0.2
- Local model provider adapter (Tier 3) — v0.2
- SMTP sending — v0.2 (v0.1 = draft + mail-client handoff only)

### 6.3 Non-functional requirements carried into v0.1 (unchanged)
2 GB RAM baseline; no AI key required; no terminal for end users; DB auto-created/auto-migrated; dev-environment rules (ENVIRONMENT.md: nothing on C:, `.venv` on D:, caches to `D:\DevCache\`, no package duplication).

---

## 7. Stack re-analysis (W4 — deltas to ARCHITECTURE.md)

| Concern | v0.1 decision | Notes |
|---|---|---|
| Language | Python 3.12+ (unchanged) | |
| DB | SQLite pending ADR-6 benchmark (§4.2) | ADR-6 is the FIRST ADR executed |
| Persistence layer | SQLAlchemy Core vs SQLModel — merged into ADR-6 run | one benchmark session decides both |
| UI shell | PySide6 assumed; ADR-1 still required before UI work begins (footprint benchmark); PyWebView fallback | Windows-only scope reduces shell risk |
| PDF reading | PyMuPDF vs pypdf — ADR-2 (AGPL question) unchanged | |
| **PDF writing (NEW)** | ReportLab (BSD) vs weasyprint (heavier) — **new ADR-7** | needed for DOCX+PDF tailored output |
| DOCX read/write | python-docx (unchanged) | |
| i18n (NEW) | Qt Linguist (.ts/.qm) if PySide6; else gettext-style JSON catalogs; all strings externalized from line one; **English copy finalized → translated to Tamil + Hindi** | translation QA required |
| AI provider | Tier 0 NoAI + Tier 1 RuleBased + **Tier 2 Gemini BYOK first**; OpenAI-compatible generic second (v0.2) | Gemini key via keyring; privacy panel mandatory |
| Browser automation | Playwright, on-demand, fill-only scope in v0.1 | Greenhouse-hosted forms only |
| Packaging | PyInstaller onedir → portable .zip (no installer v0.1) | LOOP-11 scope reduced accordingly |
| HTTP / parsing / similarity | httpx / selectolax / rapidfuzz (unchanged, sole-client rule) | |

---

## 8. Coding standards & AI guidance (W4 — deltas)

**Unchanged baseline:** AGENT_RULES.md (all 25 rules), LOOPS.md (15 loops + closing checklist), ENVIRONMENT.md (machine contract), ARCHITECTURE.md layering, MASTER_SPEC contracts, skills/ role cards.

**Amendments from this spec:**
1. **New standing instruction to all AI agents:** "You are expected to use the live internet: re-verify policy claims each session, learn from docs and real code, and adapt external code under the two gates (§5.3). Working offline without flagging UNVERIFIED claims is a process violation."
2. **New rule R-ENV-6 (proposed):** Reference study happens only in `.references/`; nothing from `.references/` reaches `app/` without §5.3 gates + ledger record.
3. **New rule R-TRUTH-6 (proposed):** Every adaptation of external code must be attributed in-code and in `docs/ATTRIBUTIONS.md`; unattributed merges are defects.
4. **i18n standard:** zero hard-coded user-facing strings; string IDs + catalogs; language completeness tracked in PROGRESS.md (EN 100%, TA 100%, HI 100% required for v0.1 release gate).
5. **Multiple-profile standard:** every profile-scoped table carries `profile_id`; UI switches profiles atomically; no cross-profile data leakage in matching/queue/tracker (test required).
6. **Ledger-universality standard:** manual application entry UI is first-class (quick-add: company, role, date, status, URL, notes), not an afterthought.
7. **Caps-onboarding standard:** discovery/queue features remain disabled until the user completes the limits-setup step (deliberate friction, user's choice).

---

## 9. Definition of "development startable" (user decision: full v0.1)

The project is officially "started" when the **entire v0.1 scope (§6.1)** passes LOOP-13 release audit. Interim milestone gates (progress markers, not "startable"):
- **M1:** ADR-6 (DB) + ADR-1 (shell) + ADR-2 (PDF read) + ADR-7 (PDF write) decided with benchmarks; `.references/` populated with PROVENANCE.md; LOOP-1 repo skeleton done.
- **M2:** Domain models (multi-profile) + DB + resume import/parse/confirm working end-to-end on CLI.
- **M3:** Discovery + dedup + matching with explanations working on real API data.
- **M4:** Generation (DOCX+PDF+email, rule-based) + ledger + tracker UI working; EN UI complete.
- **M5:** Greenhouse fill-only adapter + assisted flows + Gemini BYOK + Tamil/Hindi UI complete.
- **M6:** Full v0.1 = portable zip passes clean-Windows-VM test → **project officially started** per user's definition.

---

## 10. Risks & mitigations
| Risk | Mitigation |
|---|---|
| 3-language UI triples string QA | Copy freeze before translation; string-ID lint; translation completeness in release gate |
| Fill-only Greenhouse adapter brittle across employers | Field-reliability logging in every run feeds v0.2 auto-submit decision; dry-run default |
| "Wide net" code adoption imports bad practices | §5.3 gates mandatory; ATTRIBUTIONS.md audit in LOOP-13 |
| Multiple profiles inflate data model late | `profile_id` from M2 onward (before any feature tables exist) |
| ADR-6 benchmark bias | Fixed protocol §4.2; numbers in ledger; human sign-off |
| AGPL contamination from reference study | AGPL repo = ideas-only rule; grep gate in LOOP-9 for copied patterns |

---

## 11. Acceptance criteria for THIS spec (meta)
- [x] All 22 interview answers captured verbatim in decision tables (§3)
- [x] Reference audit with live verification + reuse posture per repo (§2)
- [x] DB question resolved into an ADR process with protocol (§4)
- [x] Live-internet & code-learning rules explicit and gated (§5)
- [x] v0.1 scope + exclusions + milestones defined (§6, §9)
- [x] Stack/standards deltas enumerated for canonical docs (§7, §8)
- [ ] Canonical docs amended per §12 (next task, not part of this spec)

## 12. Required canonical-doc amendments (to execute before M1)
1. MASTER_SPEC §15/§16: single canonical profile → **multiple named candidate profiles**.
2. MASTER_SPEC §11: v0.1 automation posture = **fill-only**; auto-submit is v0.2.
3. APPLICATION_LEDGER.md: ledger tracks **all applications incl. fully manual** (add `entry_method ∈ {automated, assisted, manual}` + quick-add flow).
4. ARCHITECTURE.md: add ReportLab-or-alt (ADR-7), i18n layer, Gemini-first Tier 2 note; packaging = portable zip.
5. ENVIRONMENT.md: add `.references\` location + gitignore requirement (§3 layout).
6. AGENT_RULES.md: add R-ENV-6, R-TRUTH-6; amend R-PROC-6 with the session-start live verification duty.
7. LOOPS.md: LOOP-11 scoped to portable zip; LOOP-5 gains scanned-PDF error path; LOOP-8 renamed "fill-only" scope for v0.1; new mandatory onboarding-limits step in LOOP-4 (targeting features).
8. DATA_SOURCES.md: add per-repo license column update after cloning (PROVENANCE cross-ref).
