# AGENT_RULES.md — Binding Rules for All AI Agents Working on No_Loop

**Authority:** This file is binding for every AI agent (Cursor, Claude Code, Copilot, Codebuff, or any other) and every human contributor. MASTER_SPEC defines *what* to build; this file defines *how you are allowed to work*. CURSOR_MASTER_PROMPT.md is the entry prompt; this file is the law it invokes.

Rule IDs are referenced by LOOPS.md, DEVELOPMENT.md and the skills files. If a task instruction conflicts with a rule, the rule wins; if the rule seems wrong, escalate to the human with a written justification — never silently deviate.

---

## Section A — Environment rules (R-ENV)

- **R-ENV-1.** Before any command: read `ENVIRONMENT.md` and set the required environment variables (§2). The project lives on `D:\Kannan-Projects\NoLoop` only.
- **R-ENV-2.** **C-drive forbiddance:** never install, write, cache, or download anything to `C:` during development. No global installs, no caches in `C:\Users\...\AppData`, no venv outside the project. Playwright browsers, pip/uv caches, model weights go to `D:\DevCache\` via env vars.
- **R-ENV-3.** **No package duplication:** exactly one dependency source of truth (`pyproject.toml` + lock). Never install into a global interpreter. Never add a second package that duplicates an existing capability without a written ADR.
- **R-ENV-4.** Always activate/use the project `.venv`. Verify `sys.executable` points inside the project before pip operations.
- **R-ENV-5.** Never modify, reorder, or "clean up" `No_Loop_docs/` or `No_Loop_Open_Source_Reference_Research/` without explicit human instruction.
- **R-ENV-6.** Reference study happens only in `D:\Kannan-Projects\NoLoop\.references\` (gitignored, read-only clones of the 8 audited repos; see ENVIRONMENT.md §3 and NOLOOP_DEV_KICKOFF-spec §5.1). Nothing from `.references/` reaches `app/` without the two gates (R-TRUTH-6 + LOOP-9 security items) and a ledger record. Each clone's PROVENANCE.md entry (commit hash, license, reuse verdict) is authoritative.

## Section B — Truth & evidence rules (R-TRUTH)

- **R-TRUTH-1.** Never fabricate: resume facts, job data, application outcomes, test results, benchmark numbers, or completion claims. If you don't know, you say you don't know.
- **R-TRUTH-2.** No feature is "done" without: code + tests run + evidence recorded in PROGRESS.md and DEVELOPMENT_LEDGER.md.
- **R-TRUTH-3.** Never mark a TODO/placeholder as complete. Unimplemented capability = visible "Not available — use fallback X" in UI and docs.
- **R-TRUTH-4.** Every external claim in docs/code comments (a policy, an API behavior, a limit) carries a source URL and an access date, or is marked UNVERIFIED. Use the live web to verify when network is available (see DATA_SOURCES.md §Verification workflow).
- **R-TRUTH-5.** Never claim an application was submitted unless a verifiable completion signal exists (see APPLICATION_LEDGER.md evidence rules). "Looks submitted" ≠ submitted. In v0.1 the adapter never submits at all (fill-only) — only humans click Submit.
- **R-TRUTH-6.** Every adaptation of external code (from `.references/` or the live web) must be attributed in-code (`# Adapted from <repo>@<commit> — <license>`) and recorded in `docs/ATTRIBUTIONS.md` + the session ledger entry. Unattributed merges are defects. License gate: MIT/Apache/BSD → snippets OK with attribution; GPL/AGPL/unknown/no-license → ideas-only, never transcribe (NOLOOP_DEV_KICKOFF-spec §5.3).

## Section C — Architecture rules (R-ARCH)

- **R-ARCH-1.** Dependency direction is fixed: UI → Application Services → Domain → Ports → Adapters → Infrastructure. The domain layer imports nothing from adapters, UI, or vendors.
- **R-ARCH-2.** Every external system (job source, ATS, email provider, AI provider, browser, OS keychain) is behind a port/interface. No direct SDK/HTTP calls from domain or application services.
- **R-ARCH-3.** No job portal, ATS, AI vendor, or email vendor name may appear in the domain layer. Vendor names live only in adapters and their config.
- **R-ARCH-4.** Adding a dependency requires: (a) no existing package covers it, (b) purpose documented in ARCHITECTURE.md §Dependencies, (c) license compatible with Apache-2.0, (d) footprint justified against the 2 GB baseline, (e) ledger entry.
- **R-ARCH-5.** No Electron. No always-running browser process. No always-running model process. No hosted backend requirement.
- **R-ARCH-6.** Deterministic first: anything computable with rules/fuzzy matching/indexes is deterministic code. AI is an optional layer that explains or generates, never the source of truth for hard constraints.
- **R-ARCH-7.** Database schema changes go through the migrations directory with a numbered migration and a test that proves upgrade + downgrade.

## Section D — Policy & ethics rules (R-POLICY)

- **R-POLICY-1.** Each source/automation adapter ships with a POLICY_STATUS (`ALLOWED_PUBLIC_API`, `PERMITTED_WITH_LIMITS`, `USER_ACCOUNT_REQUIRED`, `ASSISTED_ONLY`, `PROHIBITED`) + source URL + review date. Default is `ASSISTED_ONLY`.
- **R-POLICY-2.** Never bypass CAPTCHA, MFA, anti-bot challenges, paywalls, rate limits, or access controls — technically, by obfuscation, or by coaching the user to.
- **R-POLICY-3.** Sites that prohibit automation in their terms (e.g. LinkedIn User Agreement §8.2, Naukri terms) get `PROHIBITED` or `ASSISTED_ONLY` status: no bot submits there, ever. The compliant path is: user opens the site, No_Loop prepares the package (tailored resume, answers, email) and records the outcome the user reports. In v0.1, EVERY automated target is fill-only: the human clicks Submit everywhere; full auto-submit is a v0.2 decision gated on fill-run reliability telemetry.
- **R-POLICY-4.** Respect robots.txt, published rate limits, and API terms for every fetcher. Bounded concurrency, identified User-Agent, no fingerprint spoofing.
- **R-POLICY-5.** Personal data handling follows privacy-by-design: local-first storage, explicit consent before anything leaves the device, export + delete-all controls (DPDP Act 2023 consent principles are the baseline; see SECURITY.md).
- **R-POLICY-6.** Never fabricate qualifications, employers, dates, skills, or achievements in any generated artifact. Every generated claim traces to a confirmed profile fact (evidence mapping).

## Section E — Process rules (R-PROC)

- **R-PROC-1.** Work follows LOOPS.md. Pick the named loop for your task, execute every step in order, close the loop. Skipping a step = loop violation = work is not accepted.
- **R-PROC-2.** Smallest coherent change per task. No drive-by refactors, no reformatting unrelated files.
- **R-PROC-3.** Every task ends with: tests run, lint/type checks run, PROGRESS.md updated, DEVELOPMENT_LEDGER.md appended, exact files changed listed.
- **R-PROC-4.** Update PROGRESS.md item status only with evidence links (test names, benchmark output, file paths). VERIFIED status requires independent re-check (another loop run or the release auditor skill).
- **R-PROC-5.** If blocked, record BLOCKED in PROGRESS.md with the reason and the unblock condition. Do not invent workarounds that violate any rule in this file.
- **R-PROC-6.** Research before inventing: before designing anything non-trivial, consult RESEARCH.md, DATA_SOURCES.md, and the reference pack; do live web verification when the fact matters (R-TRUTH-4). Record findings in the ledger.
- **R-PROC-7.** Live internet is expected, not exceptional (NOLOOP_DEV_KICKOFF-spec §5.2): at the start of EVERY session, re-verify any policy/API claim the session will touch (LOOP-12 mini-run: DATA_SOURCES.md §1/§1.9 statuses, endpoints, rate limits); while coding, fetch official docs, real API samples, and code examples as needed; drift found → update the register + ledger before coding. Working offline without flagging affected claims UNVERIFIED is a process violation. The two gates of R-TRUTH-6 and R-SEC rules still apply to everything adopted.

## Section F — Security rules (R-SEC)

- **R-SEC-1.** Never log, commit, or echo API keys, passwords, tokens, cookies, or full personal data. Secrets go to the OS credential store via the CredentialReference port.
- **R-SEC-2.** All external input (job pages, downloaded files, AI output) is untrusted: sanitize HTML, validate sizes/types, prevent SSRF in URL fetchers (allowlist schemes, block private ranges, size+time caps).
- **R-SEC-3.** Network egress is opt-in per capability: the user sees *what* will be sent, *where*, and *why* before the first send of any kind. Default state: nothing leaves the device.
- **R-SEC-4.** Automation is stoppable at any instant (pause/stop is synchronous and honored before the next network or submit action).
- **R-SEC-5.** Security review checklist (SECURITY.md) applies to every PR that touches network, storage, automation, or secrets.

## Section G — UX honesty rules (R-UX)

- **R-UX-1.** First-run: no terminal, no manual DB setup, no API key required, no driver downloads.
- **R-UX-2.** Every consent dialog shows: destination, data categories, and the exact action. No dark patterns, no pre-checked consent boxes.
- **R-UX-3.** Status language is precise: "Drafted", "Ready for review", "Submitted (evidence: …)", "Failed (reason: …)". Never optimistic vagueness like "Processed".
- **R-UX-4.** Match scores show factor breakdown + missing requirements. Never a single deceptive percentage implying certainty.

---

## Rule interaction

- R-TRUTH rules outrank R-PROC rules: if following the process would force a false statement, stop and escalate.
- R-POLICY rules outrank everything: no product goal justifies violating site policy or law.
- R-ENV rules outrank convenience: "pip install worked from C:" is not a justification; redo it correctly.

## Enforcement

Violations found in review are treated as defects: the change is reverted or fixed, the incident is recorded in DEVELOPMENT_LEDGER.md (what happened, which rule, correction), and the corresponding loop gains a guard step if one was missing.
