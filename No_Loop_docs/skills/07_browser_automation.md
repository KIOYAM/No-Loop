# Skill: Automation Engineer (07)

**Load for:** LOOP-8 (application adapters, browser runs), assisted-flow design.
**Reads:** MASTER_SPEC §11, CURSOR_MASTER_PROMPT Automation contract, DATA_SOURCES.md §1.8/§1.9/§9, RESEARCH.md S3/S6, AGENT_RULES §D/§F.

## Role
Build isolated, on-demand browser/application adapters. Use Playwright only when necessary. No always-running browser. Stop on CAPTCHA/MFA/ambiguous fields. Never bypass access controls or anti-bot protections. Always provide manual fallback and evidence logging.

## Hard prerequisites (order matters)
1. LOOP-3 completed for the target with POLICY_STATUS ∈ {ALLOWED_PUBLIC_API, PERMITTED_WITH_LIMITS, USER_ACCOUNT_REQUIRED} on the *application* surface. If PROHIBITED/ASSISTED_ONLY (LinkedIn, Naukri, Indeed, foundit/hirist/instahyre, CAPTCHA-gated flows) → build the **Assisted Flow** only: package preparation (tailored resume artifact, field answer sheet from confirmed facts, email draft, evidence summary) → user submits on the portal → user records outcome → ledger updated with user-confirmed evidence. This is a first-class feature, not a failure (S3).
2. Consent gate implemented: per-run Consent Envelope showing company, role, URL, artifacts, answers, fields paused for review.
3. Stop/pause mechanism proven synchronous (R-SEC-4).

## Run contract (ApplicationAdapter)
```
discover_fields() -> FieldMap
map_fields(FieldMap, profile_subset) -> MappingResult  # + ambiguous/unmapped lists
upload_resume(artifact) -> UploadReceipt
fill(MappingResult, dry_run: bool) -> FillReport
submit(dry_run: bool) -> SubmissionResult              # only if policy+settings allow
verify(SubmissionResult) -> VerificationOutcome        # completion signal heuristics
record() -> AutomationRun                              # evidence[], timestamps, hashes
```

## Runtime rules
- Playwright launches on demand; browser binaries under `D:\DevCache\ms-playwright` in dev (R-ENV-2); context isolated per run; closed in `finally`; no resident processes (R-ARCH-5).
- Identified automation: default UA truthful for the app; no fingerprint spoofing; no stealth plugins (R-POLICY-2/4) — if the site blocks it, that is a policy stop, not an arms race.
- Hard-stop triggers: CAPTCHA, MFA, anti-bot challenge, login walls, payment walls, unknown page state, unmapped required fields → pause, snapshot state, hand to user with exact instructions (MASTER_SPEC §11/§17).
- Dry-run default in all tests and first-run-per-site for users.
- Daily/weekly caps from TargetPreference enforced before any run.
- Evidence per run: field-by-field fill report, DOM snapshot hash + screenshot at key steps, submission response marker, verification outcome (S6). Stored with AutomationRun; referenced by Application Ledger.

## Test discipline
- All tests run dry-run or against local fixture pages (recorded/redacted); no live site tests in CI.
- Hard-stop tests: fixture page with CAPTCHA marker → assert pause + user handoff + no submit.
- Stoppability test: cancel mid-fill → no submit, clean teardown.

## Deliverables
Adapter module(s), consent gate wiring, evidence recorder, assisted-flow UI service, tests, ledger entry with decision record.
