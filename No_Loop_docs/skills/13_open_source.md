# Skill: Open Source Maintainer (13)

**Load for:** release preparation, community docs, licensing questions, contribution intake.
**Reads:** LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, RESEARCH.md (references/licensing), DATA_SOURCES.md, research pack LICENSE_NOTES.md.

## Role
Documentation, contribution standards, licensing, issue templates and reproducible setup. Keep proprietary/paid assumptions out of core. Document optional integrations clearly.

## Release documentation set (per release)
1. README (user-facing): what it is, honest capability table (automated / assisted / not supported per source), install, first-run, FAQ, license.
2. CHANGELOG.md: user-visible changes only; no internal jargon.
3. SECURITY.md with a disclosure contact (security.txt optional).
4. Upstream notices: THIRD_PARTY_NOTICES.md generated from the dependency register + lock (licenses + copyrights); AGPL note if ADR-2 keeps PyMuPDF — reviewed by the human.
5. Sample data: synthetic only; zero personal information (CI grep guard on fixtures).
6. Reproducible setup: dev quickstart that *is* ENVIRONMENT.md §2/§3 compliant and testable from a clean clone.

## Issue/PR templates
- Bug: environment (OS/RAM/version), steps, expected vs actual, diagnostic ID, redacted logs only.
- Feature: MASTER_SPEC section it maps to; policy implications; no-AI-mode impact.
- Adapter proposal: DATA_SOURCES.md §1/§9 row, policy evidence URLs with dates, POLICY_STATUS proposal, fallback design.
- PR: tests run, ledgers updated, security checklist if applicable, files changed list.

## Licensing rules
- Apache-2.0 for the project; inbound contributions under the same (LICENSE §5).
- Reuse of reference-pack code only within license terms; prefer reimplementing ideas (research pack rule). AGPL/strong-copyleft code: reference-only unless a human-signed ADR accepts the obligations.
- Site terms/robots respected in every advertised capability; never market automation for PROHIBITED portals (LinkedIn/Naukri) — marketed as assisted.

## Community hygiene
Label good-first-issues with the loop + skill to load; enforce CoC; keep discussions technical; record maintainer decisions in the ledger when they change rules/docs.

## Deliverables
Release doc set, templates, notices file, license reviews, community reports (stars/issues triage notes optional).
