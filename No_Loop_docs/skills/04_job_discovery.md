# Skill: Job Discovery Engineer (04)

**Load for:** LOOP-3 (source adapters), dedup work, policy classification.
**Reads:** DATA_SOURCES.md (all), MASTER_SPEC §6/§7, RESEARCH.md S5/S8, AGENT_RULES §D, skill 07 for assisted flows.

## Role
Build pluggable job source adapters; normalize, fingerprint, and deduplicate jobs; enforce per-source policy. Never make one website a hard dependency.

## Adapter checklist (per adapter, inside LOOP-3)
1. **Policy first:** classify per R-POLICY-1 using DATA_SOURCES.md §1/§9; fetch live policy/API pages (LOOP-12) and record URL + access date. If status ∈ {PROHIBITED, ASSISTED_ONLY} → build assisted flow only; stop automation work.
2. **Capability declaration:** DISCOVERY / PARSING / APPLICATION / EMAIL / CAPABILITIES / POLICY_STATUS as adapter metadata the UI can query.
3. **Fetcher:** httpx async, identified User-Agent (`No_Loop/<version>; +repo URL`), timeouts, size caps, bounded concurrency, retry with backoff (idempotent GETs only), rate limiter (per-source config; RemoteOK ≥1 h default per DATA_SOURCES §1.3).
4. **Normalizer:** external shape → domain Job (title, company, location, work mode, salary min/max/currency, description sanitized, posted date, source URL, native ID, raw evidence). HTML → text via selectolax; sanitize (R-SEC-2).
5. **Incremental sync:** use posted-date/cursors; store last-sync state per source; no full re-pulls when incremental is available.
6. **Dedup contribution:** emit JobIdentity keys (canonical URL, native ID, company+title fuzzy, content fingerprint) for the S8 pipeline.
7. **Failure mapping:** every HTTP/parse error → domain error with stage/reason/retryable/user_action; source failure isolates — one broken source never breaks discovery (Job Scraper lesson).
8. **Contract tests:** recorded fixtures (redacted) cover: happy path, empty page, partial fields, HTML-laden description, error responses, pagination ends.

## First-release adapter set (per DATA_SOURCES §9)
arbeitnow, remotive, remoteok, jobicy, adzuna (user key), greenhouse, lever, ashby (discovery), URL/JD import. Everything else: not-yet-implemented sources must be visibly labeled "Not available — assisted flow only" in the UI with a documented fallback — never fake data (R-TRUTH-3).

## Guardrails
Respect robots.txt for page fetches; no scraping behind auth; no rate-limit evasion; no UA spoofing; no CAPTCHA/anti-bot interaction (R-POLICY-2). API terms read + recorded before first fetch.

## Deliverables
Adapter modules + metadata, fixtures, contract tests, policy register row updates, source isolation tests (kill one adapter in test, others still function), ledger entry.
