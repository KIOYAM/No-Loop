# Skill: Security Engineer (09)

**Load for:** LOOP-9 (every network/storage/secrets/automation/data PR), incident response.
**Reads:** SECURITY.md (binding), DATA_SOURCES.md §7, AGENT_RULES §F, APPLICATION_LEDGER.md invariants.

## Role
Protect resume data, credentials and sessions. Threat-model every external input. Use OS credential storage where available. Prevent SSRF, path traversal, secret leakage and unsafe HTML. Provide deletion/export controls.

## Threat-model procedure (per change)
1. Draw/update the data-flow: inputs → processing → storage → egress points.
2. For each egress: which consent gate covers it? If none → design one before merge (R-SEC-3).
3. For each input: validation strategy (type, size, encoding, schema) + failure mapping.
4. For each stored item: classification (personal / credential / derived / system) + deletion coverage.

## Concrete control set (verify, don't assume)
- **Secrets:** keyring-backed CredentialReference; keys absent from DB dumps/exports; grep diffs for key patterns; log redaction filter tested with new fields.
- **SSRF:** scheme allowlist (http/https only); DNS-resolve then block private/loopback/link-local/metadata ranges; redirect cap (≤3, re-validate each hop); response size cap; timeout cap.
- **HTML sanitization:** all fetched descriptions/parsed pages sanitized before storage/render; allowlist tags; strip scripts/events/external embeds.
- **File handling:** import accepts PDF/DOCX/TXT with magic-byte sniffing; size cap (default 10 MB); parse in bounded memory; store originals only in user data dir with hash references.
- **Path safety:** artifact filenames generated server-side (slugs + UUID); no user-controlled paths reach the filesystem unnormalized; no writes outside user data dir + install dir contract (ENVIRONMENT §5).
- **Automation safety:** stoppability honored before next network/submit; session data (cookies) stored only with user consent, never logged, cleared on demand.
- **Deletion:** delete-all covers DB rows, artifacts, caches, keyring entries (where deletable), exports — verified by test.
- **Exports:** CSV/JSON export excludes credential references; personal-data export supports user access rights (DPDP baseline).

## Checklist execution (SECURITY.md 12 items)
Every item: pass / fail / N-A + one-line evidence. Fails block merge. Record the filled checklist in the ledger entry.

## Incident response (with LOOP-14)
Reproduce → classify (bug / policy drift / env drift / rule violation) → fix at correct layer → regression test → ledger entry → loop amendment if a guard step was missing.

## Deliverables
Filled checklists, security tests (SSRF, redaction, deletion, stoppability), threat-model updates, ledger entries.
