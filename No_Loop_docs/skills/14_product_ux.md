# Skill: Product UX Engineer (14)

**Load for:** LOOP-4 UI slices, onboarding design, consent flows, tracker/dashboard design.
**Reads:** MASTER_SPEC §16, AGENT_RULES §G (R-UX), APPLICATION_LEDGER.md state machine, RESEARCH.md S1/S3/S9, SECURITY.md (consent).

## Role
Design a fast, understandable first-run flow. Minimize configuration. Never expose implementation details such as database setup. Make consent, automation state and external data movement obvious.

## First-run flow (MASTER_SPEC §16; no terminal, ever)
```
Install → Open → Import Resume → Parse (progress, cancelable)
→ Review facts (confirm / reject / edit chips; inferred clearly labeled)
→ Targeted questions (only real gaps; skippable)
→ Target roles (accept/reject/edit suggested + custom)
→ Sources (checkboxes with plain-language policy labels)
→ Start discovery (works immediately; URL-import path works with zero sources)
```

## Screen inventory + honesty rules
Dashboard (counts + next actions), Profile (fact ledger with provenance), Resume (canonical + derived artifacts), Targeting (preferences/threshold/limits), Jobs (list with match bands + factor drill-down), Job Detail (JD sanitized view, requirements split, missing-requirements panel, research summary), Application Queue (Readiness Gate columns), Email Drafts (evidence map side-by-side), Tracker (state machine board + export), Automation Runs (evidence viewer), Settings (sources, AI tiers, privacy panel, limits, data export/delete), Diagnostics (redacted; cache sizes; version).

Rules per screen:
- Status language exact (R-UX-3): "Drafted", "Ready for review", "Submitted — evidence recorded", "Verification pending", "Failed — reason shown". Banned: "Processed", "Almost done", vague spinners.
- Match display: band + factor breakdown + missing list; never a lone percentage (R-UX-4).
- Every AI involvement labeled; every external send preceded by a consent dialog naming destination + data (R-UX-2); no pre-checked boxes.
- POLICY_STATUS surfaced per source in plain words: "Public API — automated", "Assisted — you submit, we prepare", "Automation not permitted here — assisted flow provided".
- Degrade visibly, not silently: provider down → banner + fallback notice; source failing → source card shows failure state, others unaffected.

## Interaction patterns
- Long operations: progress + cancel; cancel honored before the next network/submit step (R-SEC-4).
- Destructive actions: type-to-confirm (delete-all).
- Low-memory care: virtualized lists for 1,000+ jobs; no giant DOM trees; images lazy.

## Test discipline (with skill 12)
UI smoke suite per screen; consent-flow assertions (no egress without recorded Consent Envelope); first-run walkthrough test from packaged build.

## Deliverables
Wireframes/spec sections in docs, UI component tasks mapped to MASTER_SPEC §16, copy deck (exact status strings), usability checklist, ledger entries.
