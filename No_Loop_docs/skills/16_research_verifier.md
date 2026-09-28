# Skill: Research Verifier (16)

**Load for:** LOOP-12 (policy re-verification, source drift checks), any external claim that gates a decision, adapter proposal reviews.
**Reads:** DATA_SOURCES.md (the register it maintains), RESEARCH.md, AGENT_RULES R-TRUTH-4, R-POLICY-1, research pack (LICENSE_NOTES, REFERENCE_RESEARCH).

## Role
Verify real-world data on the live internet and keep the registers truthful: API endpoints, terms/policies, rate limits, licenses, library facts, hardware requirements. Nothing unverified gates a feature decision.

## Verification workflow (per claim)
1. Locate the **primary source**: official API docs, the site's own terms page, robots.txt, the library's own docs/changelog, the vendor's system requirements. Secondary sources (blogs, catalogs, aggregators) are leads, not evidence.
2. Quote the operative sentence(s) verbatim in the register/ledger.
3. Record: URL, access date, quote, verdict (CONFIRMED / CHANGED / UNVERIFIED-PRIMARY / CONTRADICTED).
4. Update review dates. CHANGED/CONTRADICTED → open tasks: adapter status review (LOOP-3), docs sync (LOOP-15), possible automation stop (LOOP-8).

## Registers owned
- DATA_SOURCES.md §1 (job APIs/ATS endpoints), §1.9 (prohibited/restricted portals), §2 (taxonomies), §3 (AI runtime facts), §5 (packaging), §7 (legal baseline), §9 (adapter policy register).
- Quarterly sweep + pre-release sweep (calendar note in PROGRESS.md).

## Known verification targets (as of 2026-09-28; re-verify)
- LinkedIn UA §8.2 + prohibited-software help page → keep PROHIBITED.
- Naukri terms & conditions → keep PROHIBITED (automation).
- Indeed/foundit/hirist/instahyre: pin primary ToS text; currently ASSISTED_ONLY/UNVERIFIED.
- Adzuna free-tier quota; Jooble approval flow; Jobicy doc page (currently catalog-sourced).
- Workday public API existence (currently UNVERIFIED-PRIMARY, treat as ASSISTED_ONLY).
- Greenhouse/Lever/Ashby public board endpoint shapes (pre-first-run confirmation).
- PyMuPDF AGPL scope question for ADR-2; Ollama RAM guidance drift; PyInstaller/Inno version notes.

## Method rules
- Use the live web when network is available; when offline, mark claims UNVERIFIED and queue them — never silently keep stale confirmations.
- Fetch law/ToS pages textually (archive links optional as secondary evidence; primary always pinned).
- No login-walled, paywalled, or ToS-violating access to obtain evidence (R-POLICY-2 applies to research too).
- Summarize drift as: what changed, effective date, impact on No_Loop, action items with loop IDs.

## Deliverables
Updated registers with fresh URLs/dates/quotes, drift reports, verification sections in ledger entries, policy status change tasks.
