# Security & Privacy

No_Loop handles resumes, contact details, credentials (email/BYOK keys), and — if the user enables automation — session contexts. This document is the binding security baseline; LOOP-9 enforces it per change.

## Threat model summary
| Asset | Threat | Control |
|---|---|---|
| Resume/profile data | theft, leakage via AI providers | local-first; Consent Envelope before any egress; privacy_info shown before BYOK activation |
| Credentials/keys | logging, commit leakage, memory scraping | OS keychain via keyring; never logged; diagnostics redaction (R-SEC-1) |
| Automation sessions | account risk on prohibited sites | POLICY_STATUS gating; assisted flow on PROHIBITED portals (LinkedIn §8.2, Naukri ToS) |
| Fetched job pages/files | malicious content, SSRF, huge payloads | sanitize HTML; size+time caps; scheme allowlist; block private ranges (R-SEC-2) |
| Local DB | accidental loss | export + backup; delete-all verified |
| Supply chain | dependency compromise | lock file; minimal deps; license+purpose register; no duplicates (R-ENV-3/ARCHITECTURE) |

## Rules
- Never commit credentials. Never log API keys, passwords, cookies, or session tokens.
- Use OS credential stores where available (Windows Credential Manager via keyring).
- Redact secrets in diagnostics/export with a tested redaction filter.
- Treat job pages and downloaded documents as untrusted input; sanitize all HTML before rendering or storage.
- Prevent SSRF in URL fetchers: allowlist http/https, resolve+block private/loopback/link-local ranges, cap redirects, cap size and time.
- Restrict file types (PDF/DOCX/TXT for import) and file sizes; parse in bounded memory.
- Require explicit Consent Envelope before sending email or submitting applications; consent records are stored and auditable.
- Make automation stoppable at any instant; stop is honored before the next network or submit action (tested).
- Provide local data export and a working delete-all action (DB, artifacts, caches).
- Document exactly what leaves the device when a BYOK provider is enabled; show it in the UI at activation and in Diagnostics.
- Installer and app write only to the chosen install dir + per-user app data (ENVIRONMENT.md §5).

## Security review checklist (LOOP-9; every network/storage/secrets/automation PR)
1. Data-flow diagram of the change drawn/updated
2. All inputs untrusted-validated (types, sizes, encodings)
3. SSRF cases tested on URL fetcher paths
4. Secret-scan clean on diff; log grep clean
5. Redaction filter covers new fields
6. Consent gates cover any new egress
7. Stoppability tested for any new automation step
8. Error messages leak no sensitive data
9. Migration reversibility + data integrity checked
10. Delete-all still removes everything new
11. New dependency: license, purpose, lock updated, duplicates checked
12. Environment audit: no C: writes introduced

## Privacy law baseline
India DPDP Act 2023 consent principles (free, specific, informed, unconditional, unambiguous; purpose limitation; erasure rights) are the design floor for consent flows, purpose tagging, and deletion. Sources: DATA_SOURCES.md §7.
