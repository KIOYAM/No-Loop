# Skill: Application Communication Engineer (08)

**Load for:** LOOP-7 (email drafts, recruiter messages, generation guards).
**Reads:** MASTER_SPEC §9/§10, CURSOR_MASTER_PROMPT Email contract, RESEARCH.md S2, DATA_SOURCES.md §6, AGENT_RULES R-UX-2/3.

## Role
Generate job-specific email drafts from actual requirements and verified candidate evidence. Never fabricate. Preview before send by default. Keep SMTP/mail-client providers optional.

## Generation contract
Inputs: job record (title, company, location, requirements with required/preferred split), confirmed-fact projection (skills, projects, achievements relevant to the JD — selection, not invention), tone settings.
Output: editable draft + Evidence Map (each factual sentence → fact IDs) + specificity report.

## Job-specificity guards (automated, tested in LOOP-7)
1. Draft must reference: role title, company name, ≥2 actual JD requirements, ≥2 evidence-backed candidate facts. Guard rejects generic-template-only output.
2. Factual fields (years of experience, employers, technologies claimed, dates) are assembled from facts only; free-text generation is confined to framing/connective text and remains evidence-mapped (S2).
3. No fabricated qualifications, no invented keywords, no experience inflation — gap requirements are surfaced as gaps, not papered over.
4. Prohibition list scan: draft must not contain certainty-spam ("guaranteed", "100% match", "expert in X" when X is not a confirmed production skill — flag for user decision instead).

## Provider abstraction (email)
| Provider | Behavior | Policy |
|---|---|---|
| local-draft (default) | writes .eml/txt draft to user data dir; opens in user's mail client on request | no network |
| mail-client handoff | `mailto:`/file handoff with attachments | no network from app |
| SMTP (user-configured) | sends only after explicit per-send consent + settings opt-in | USER_ACCOUNT_REQUIRED; credentials via keyring |
| connected provider (future) | adapter behind the same port | USER_ACCOUNT_REQUIRED; ADR-5 required first |

Sending rules: preview is mandatory; consent per send (R-UX-2); every send recorded (EmailDraft → Application Ledger link); failures mapped per MASTER_SPEC §17; attachment = derived resume artifact only.

## Test discipline
- Guard tests: generic email rejected; fabricated-fact injection blocked; evidence map complete.
- Golden drafts: (synthetic profile + JD fixture) → expected draft structure (not exact wording for AI path; exact for rule-based path).
- Provider contract tests with fake SMTP; no real sends in tests ever.

## Deliverables
Generator module + guards, email providers, consent wiring, tests, ledger entry.
