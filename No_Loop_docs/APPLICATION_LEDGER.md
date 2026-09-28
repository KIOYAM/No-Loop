# Application Ledger (product feature)

The Application Ledger is a core product table (and this document defines its contract). Every application the user tracks — automated, assisted, **or fully manual** — has exactly one record, updated only through the Application state machine. The ledger is a complete job-search command center: applications the user submitted entirely outside No_Loop are first-class records too (NOLOOP_DEV_KICKOFF-spec §3 Round 6).

**Entry methods:** every record carries `entry_method ∈ {automated, assisted, manual}`:
- `automated` — a No_Loop adapter filled/submitted (v0.1: fill-only; evidence = AutomationRun).
- `assisted` — No_Loop prepared the package, the human submitted on the portal (evidence = user confirmation record).
- `manual` — created via **Quick-Add** without any No_Loop artifacts (see below).

**Quick-Add (first-class UI, not an afterthought):** minimal capture — company, role, date, status, application URL (optional), notes (optional), profile selection. Takes <30 seconds. Record can be enriched later (attach artifacts, JD, evidence) but never requires it. Quick-Add exists precisely so the user never needs a second tracker tool.

**Profile scoping:** every Application record carries `profile_id`; the tracker board filters and displays per named candidate profile, with an "All profiles" aggregate view.

## Record fields
- application_id (UUID)
- profile_id (FK → CandidateProfile; multiple named profiles)
- entry_method (automated | assisted | manual)
- job_id (FK → Job; nullable for manual entries with no discovered job; retains dedup cluster reference when present)
- company, title, source, source_url, application_url
- date/time created; date/time of each state change (AuditEvent list)
- canonical_resume_version (hash) — which profile version was current
- generated_artifact_ids (Derived Artifacts incl. tailored resume copy, cover letter)
- email_draft_id
- automation_run_id (null for assisted submissions)
- consent_envelope_id (per MASTER_SPEC §14/SECURITY.md)
- status (state machine below)
- submission_evidence: for automated — completion signal + snapshot hashes + timestamps; for assisted — user confirmation record
- follow_up_date
- notes (user-editable)
- failure_reason (structured: stage, reason, retryable, user_action, diagnostic_id — MASTER_SPEC §17)

## Status state machine (Readiness Gate)

```
DISCOVERED → SHORTLISTED → READY → DRAFTED → REVIEW_REQUIRED
    REVIEW_REQUIRED → SUBMITTED (automated, evidence present)
    REVIEW_REQUIRED → SUBMITTED (assisted, user confirmation recorded)
    REVIEW_REQUIRED → REJECTED_BY_USER / SKIPPED (reason stored)
    SUBMITTED → VERIFICATION_REQUIRED (no completion signal yet)
    VERIFICATION_REQUIRED → SUBMITTED (verified) | FAILED (with evidence)
    SUBMITTED → INTERVIEW → OFFER | REJECTED | CLOSED
    any → WITHDRAWN
    FAILED → READY (retry allowed, new consent required)
```

Statuses: DISCOVERED, SHORTLISTED, READY, DRAFTED, REVIEW_REQUIRED, SUBMITTED, VERIFICATION_REQUIRED, FAILED, WITHDRAWN, REJECTED, INTERVIEW, OFFER, CLOSED, REJECTED_BY_USER, SKIPPED.

## Invariants
1. No record enters SUBMITTED without submission_evidence (automated: verifiable completion signal; assisted: explicit user confirmation; manual: user assertion recorded at entry) — R-TRUTH-5.
2. Every artifact referenced must exist and pass its Evidence Map validation.
3. State transitions are append-only AuditEvents; no destructive edits.
4. Daily/weekly caps and threshold rules from TargetPreference are enforced at queue admission (DISCOVERED → SHORTLISTED → READY), not retroactively. Caps have NO defaults; queue stays disabled until the user sets them (MASTER_SPEC §4).
5. Export (CSV/JSON) includes all fields except credential references; delete-all removes records + artifacts + caches (verified by LOOP-9 test).
6. `manual` records are never modified by automation; only the user edits them.
7. Cross-profile leakage is forbidden: matching, queue, and tracker queries are always profile-scoped (tested; NOLOOP_DEV_KICKOFF-spec §8.5).
