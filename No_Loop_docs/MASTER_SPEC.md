# No_Loop Master Product Specification

## 1. Product definition
No_Loop is a downloadable desktop application that helps a job seeker:
1. Import a resume.
2. Parse and understand resume data.
3. Build structured Canonical Profiles — **multiple named candidate profiles** (e.g. "Python Developer" and "ML Engineer"), each with its own resume documents, targeting, queue and tracker; profiles are switchable and fully isolated from each other (NOLOOP_DEV_KICKOFF-spec §3 Round 4).
4. Ask dynamic onboarding questions generated only from real gaps/ambiguities.
5. Suggest target job roles, seniority/experience ranges, locations and search criteria.
6. Let the user accept, reject, edit, or add their own criteria.
7. Discover jobs from supported sources (public APIs, ATS boards, career pages, user-imported URLs/JDs).
8. Normalize and deduplicate jobs (5-key pipeline, RESEARCH.md S8).
9. Score jobs against the active profile (Match Triangle: hard gate + soft score + explanation).
10. Show the reasons behind every match and the missing requirements.
11. Research the employer/job when permitted and technically possible.
12. Generate a job-specific application package from the active Canonical Profile (truth-preserving tailoring, S2).
13. Draft a job-specific email based on the actual job requirements.
14. Preview everything before sending/submitting.
15. Automate supported application steps only where legally/technically permitted (Policy Status-driven). **v0.1 posture is fill-only:** the browser adapter auto-fills permitted forms and the user clicks Submit; full auto-submit is v0.2 (NOLOOP_DEV_KICKOFF-spec §3 Round 6).
16. Fall back to guided Assisted Flow whenever automation is unavailable or prohibited.
17. Track **all** applications and their statuses locally in the Application Ledger — automated, assisted, and fully manual ones alike (quick-add flow); the ledger is a complete job-search command center.

Reference end-user scenario (from the originating requirement): a Python/AI-ML associate developer targeting roles like Python Developer, AI/ML Developer, AI Engineer, Backend (FastAPI/Django) Developer, ML Engineer, Generative AI Developer; 1+ year experience; locations Coimbatore / Chennai / Bangalore / Remote; configurable salary range and real notice period; per-application records of company, role, JD, date, resume version, application URL, status. **India-first defaults:** location presets (Coimbatore/Chennai/Bangalore/Remote), ₹ salary formats, notice-period norms; global boards remain available (NOLOOP_DEV_KICKOFF-spec §3 Round 3).

## 2. Non-negotiable product requirements
- Desktop/local-first; no required cloud server; no mandatory paid API; no mandatory AI API; no mandatory database installation.
- No manual Python/Node/DB setup for end users; installer bundles runtime dependencies.
- SQLite (or equivalent embedded DB) auto-created and auto-migrated on first run.
- Secrets stored in the OS credential store where available; never logged.
- Clear consent (Consent Envelope) before any external communication or final submission.
- Never fabricate qualifications, employers, projects, education, dates, skills, salary, experience, or achievements.
- Never silently change the Canonical Profile.
- All generated content traceable to source profile facts and the target job (Evidence Map).
- Never claim an application succeeded without a verifiable completion signal (or user confirmation for assisted submissions).
- Every automation adapter has a manual/assisted fallback; unsupported workflows are never brute-forced.
- User can pause/stop automation at any instant; can inspect generated content before sending.
- Application history exportable (CSV/JSON); delete-all function exists and works.
- Core must run in 2 GB RAM; measured targets per operation (§13), not marketing numbers.

## 3. Resume intelligence
Input formats: PDF and DOCX first; TXT secondary; RTF only if practical.

Pipeline: `file → text extraction → structure detection → normalized profile → confidence/ambiguity report → user confirmation → Canonical Profile`.

**Scanned/image-only PDFs (v0.1, user decision):** when extraction yields no text, show a clear error — "No text found — this looks like a scanned image. Export a text PDF or paste your resume text." — with a guided paste-text fallback. No OCR in v0.1 (OCR is a v2+ optional plugin).

Extract: name/contact; summary; education; employment; dates; titles; responsibilities; achievements; projects; technologies; certifications; links; locations; portfolio/GitHub/LinkedIn URLs. Inferred-but-unconfirmed fields are stored separately from confirmed facts and never displayed as fact (S4).

Structure extraction must handle common real-world layouts; generated resumes follow ATS-parseable formatting (single column, standard headings, standard fonts — DATA_SOURCES.md §6).

## 4. Dynamic onboarding
Questions are generated from actual gaps and target-job choices, not a fixed form. Question classes:
- Target roles; locations; remote/hybrid/onsite.
- Min/max experience; notice period; work authorization; relocation willingness; salary expectations.
- Technologies to emphasize; technologies NOT to be claimed as production experience.
- Application limits: per-day/per-week caps, match threshold, sources to enable.

All questions concise, editable, skippable. Answers become Confirmed Facts. Question engine diffs Confirmed Facts against role-requirement templates (O*NET/ESCO-informed).

**Mandatory limits setup (v0.1, user decision):** there are NO silent default caps. Discovery and the Application Queue remain disabled until the user explicitly sets every limit from zero on first run — per-day cap, per-week cap, match threshold, company cooldown, active hours. This deliberate friction is a product feature (NOLOOP_DEV_KICKOFF-spec §3 Round 4, §8.7). Scanned/image-only PDFs produce a clear error with a guided paste-text fallback; no OCR in v0.1.

## 5. Job targeting
User can: accept/reject/edit suggested roles; add custom roles; set experience ranges; set locations; choose sources; set exclusions (companies, keywords); configure work mode; configure recency; set application limits and match threshold.

## 6. Job discovery
Pluggable Source Adapters only — no portal hard-coded in domain. Source classes: public job APIs/feeds; company career pages; ATS public job boards; supported portals; user-provided job URLs; imported JDs (paste/file).

Every adapter declares: DISCOVERY, PARSING, APPLICATION, EMAIL, CAPABILITIES, POLICY_STATUS. The authoritative source list + statuses + endpoints lives in DATA_SOURCES.md and is re-verified by LOOP-12.

## 7. Employer research
Collect per job: company name; role; JD; requirements; location; application URL; ATS/provider; company website; relevant public info. Lightweight HTTP parsing first; browser rendering only when necessary and permitted. All fetched content treated as untrusted input (SECURITY.md).

## 8. Matching
Hybrid Match Triangle:
- Hard constraints (deterministic gate): location/work-mode, experience range, work authorization, exclusions, recency. Fail any → excluded with reason shown.
- Soft score (weighted, deterministic): skills overlap (taxonomy-normalized), title similarity, experience compatibility, required-vs-preferred weighting, education/certification fit, salary alignment.
- Explanation: per-factor contributions + missing requirements list.

AI may explain/summarize; deterministic checks remain the source of truth for hard constraints. Never output a deceptive single score implying certainty.

## 9. Application package
Per selected job: canonical resume unchanged; derived job-specific resume artifact; optional cover letter; job-specific email; optional short recruiter message; Evidence Map; source/evidence metadata. Emails must reference actual role/company/requirements with relevant candidate evidence — no generic filler (LOOP-7 guard).

## 10. Email
Provider abstraction: local draft only (default) → SMTP (user-configured) → mail-client handoff → optional connected provider later. Sending requires explicit user authorization per settings; draft/preview is the default state.

## 11. Automation
ApplicationAdapter contract: discover fields → map profile fields → upload resume → fill supported fields → detect questions → pause for ambiguous/high-risk fields → obtain explicit consent per settings → **v0.1: fill-only — the adapter never clicks Submit; the user always performs the final submission** → verify recorded outcome → record evidence (AutomationRun + Application Ledger). Full auto-submit is v0.2, gated on field-reliability telemetry from fill-only runs (NOLOOP_DEV_KICKOFF-spec §6.2).

Browser automation is not a default runtime dependency; Playwright initializes on demand only, browsers stored on `D:` in dev (ENVIRONMENT.md). v0.1 automated target: Greenhouse-hosted public application forms, fill-only. All other portals: Assisted Flow. Hard stops: CAPTCHA, MFA, anti-bot challenge, unknown page state → pause and hand control to the user. Never bypass.

## 12. AI provider architecture
Provider interface: `available()`, `generate()`, `structured_generate()`, `explain()`, `estimate_cost()`, `privacy_info()`.
Built-in providers: NoAIProvider, RuleBasedProvider, **UserProvidedGeminiProvider (first BYOK implementation — v0.1, user decision)**, OpenAI-compatible generic BYOK (v0.2), LocalModelProvider (Ollama/llama.cpp-compatible; v0.2; only used if the user already runs it; auto-disabled under memory pressure).
The application must be fully useful with no API key. Provider keys are user-owned, stored in the OS keychain, never bundled, never logged. Every provider surfaces its privacy_info before activation (what data goes where).

## 13. Performance
Design rules: lazy loading; streaming parsing; bounded concurrency; SQLite indexes; caching; dedup; incremental processing; no always-on browser; no always-on model; never resend the whole resume to AI repeatedly (send requirement-relevant slices).

Measurable targets on a documented low-end baseline (2 GB-class machine, recorded in each benchmark run):
- local DB lookup: generally sub-100 ms
- cached job normalization: generally sub-100 ms
- deterministic matching: generally sub-500 ms per 1,000-job batch
- PDF/DOCX parsing: size-dependent; benchmark with corpus
- network/AI operations: inherently variable; always show progress and cancelation

Benchmarks run in LOOP-10; real numbers recorded in the ledger. Never fabricate numbers.

## 14. Security
Local-only by default; OS keychain for secrets; encrypted sensitive local settings where practical; no secret logging; diagnostics redaction; explicit external-data disclosure; least-privilege; safe file handling (type/size caps); SSRF protections on user URLs; download restrictions; audit of automation actions; export + delete-all. Full requirements + checklist: SECURITY.md.

## 15. Data model (core entities)
CandidateProfile (named profile; the "canonical profile" container); UserProfile; ResumeDocument; ResumeFact (provenance, confidence, state); TargetPreference; JobSource; Job; JobRequirement; JobCluster (dedup); MatchResult; Application (with `entry_method ∈ {automated, assisted, manual}`); ApplicationArtifact; EmailDraft; AutomationRun (evidence[]); ConsentEnvelope; CredentialReference; AuditEvent; Setting; DevelopmentLedger; ProgressLedger.
Every profile-scoped entity carries `profile_id` (multiple named profiles, NOLOOP_DEV_KICKOFF-spec §8.5). Field-level schemas are defined in code via LOOP-2 and mirrored in APPLICATION_LEDGER.md where product-facing.

## 16. UX
First run: Install (portable zip) → Open → choose data location (default per-user folder / Portable toggle) → Import Resume → Parse → Review facts (confirm/reject inferred) → Answer targeted questions → **Set application limits (mandatory, from zero)** → Select target roles → Configure sources → Start discovery. No terminal anywhere. UI languages: English + Tamil + Hindi (all strings externalized; NOLOOP_DEV_KICKOFF-spec §8.4).

Main areas: Dashboard; Profiles (create/switch); Profile; Resume; Targeting; Jobs; Job Detail; Application Queue; Email Drafts; Application Tracker (incl. manual quick-add); Automation Runs; Settings (data location, AI, privacy, languages); Diagnostics; (maintainer area hidden in production builds).

## 17. Failure behavior
Never silently fail. Every failed operation reports: stage; reason; retryability; user action; technical diagnostic ID. Failure taxonomy tested per LOOP-4 step 6.

## 18. Open source
License: Apache-2.0 (full text in LICENSE). Includes: LICENSE; CONTRIBUTING.md; SECURITY.md; CODE_OF_CONDUCT.md; README; architecture docs; tests; adapter documentation; sample data with no personal information.
