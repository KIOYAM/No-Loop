# DATA_SOURCES.md — Real-World Data & Policy Register (Live-Web Verified)

**Purpose:** the canonical register of external data sources, their endpoints, their legal/policy status, and the verification workflow. All coding and references for adapters must come from this file (or a ledger-updated revision of it). Every claim here carries a source URL + access date; anything unverified is marked UNVERIFIED (R-TRUTH-4). The Research Loop (LOOPS.md LOOP-12) re-verifies this register quarterly and before every release.

Last full register review: 2026-09-28.

---

## 1. Free / public job data APIs (discovery tier 1)

These are the default discovery sources. All are usable without payment; some require a free key.

### 1.1 Arbeitnow — public Job Board API
- Endpoint: `https://www.arbeitnow.com/api/job-board-api` (JSON; paginated; includes `remote` flag, company, location, tags, URL, posting date).
- Auth: none required for the public board endpoint.
- Policy status: `ALLOWED_PUBLIC_API`.
- Source: https://www.arbeitnow.com/blog/job-board-api (accessed 2026-09-28).
- Adapter notes: maps cleanly to the No_Loop Job model; use tags as raw skill keywords (normalize later — do not trust tags as canonical skills).

### 1.2 Remotive — public remote jobs API
- Endpoint: `https://remotive.com/api/remote-jobs` (JSON; `job_title`, `company_name`, `category`, `job_type`, `candidate_required_location`, `salary`, `publication_date`, `url`, description HTML).
- Auth: none required.
- Policy status: `ALLOWED_PUBLIC_API`.
- Source: https://remotive.com/remote-jobs/api (accessed 2026-09-28).
- Adapter notes: description is HTML — sanitize before storage/parsing (R-SEC-2). Limit fetch frequency; use `publication_date` for incremental pulls.

### 1.3 RemoteOK — public feed
- Endpoint: `https://remoteok.com/api` (JSON array; first element is a legal notice — adapters MUST read and respect it; subsequent elements are jobs with `position`, `company`, `location`, `tags`, `salary_min/max`, `url`, `date`).
- Auth: none; the API asks implementers not to spam and to respect rate limits.
- Policy status: `PERMITTED_WITH_LIMITS` (low frequency, identified User-Agent, obey their notice element).
- Source: https://remoteok.com/remote-api-jobs (accessed 2026-09-28).
- Adapter notes: cache aggressively; do not poll more than configured default (suggest ≥1 hour between pulls).

### 1.4 Jobicy — remote jobs feed
- Endpoint: `https://jobicy.com/api/v2/remote-jobs` (JSON; filters: `count`, `industry`, `region`).
- Auth: none.
- Policy status: `ALLOWED_PUBLIC_API`.
- Source: referenced from public API catalogs, e.g. https://github.com/ever-jobs/ever-jobs and https://jobspipe.dev/free-jobs-api (accessed 2026-09-28). Verify against Jobicy's own docs page during LOOP-12.

### 1.5 Adzuna — free-tier jobs API (many countries incl. India)
- Endpoint: `https://api.adzuna.com/v1/api/jobs/{country}/search/{n}.json` with `app_id` + `app_key`.
- Auth: free registration; default free tier documented around 2,500 calls/month (catalog claim).
- Policy status: `USER_ACCOUNT_REQUIRED` (free) — user enters their own key in Settings; the app never ships a key.
- Source: https://www.adzuna.com/ and catalog note https://jobspipe.dev/free-jobs-api (accessed 2026-09-28). Verify current quota in Adzuna dashboard docs during LOOP-12.
- Adapter notes: best free option for location-filtered Indian jobs; supports `what`, `where`, `max_days_old`, salary data.

### 1.6 Jooble — free-tier API
- Endpoint: REST API with partner key; free tier for approved apps.
- Policy status: `USER_ACCOUNT_REQUIRED` (free, application/approval may be needed).
- Source: https://jooble.org/api-documentation (listed in public API catalogs; accessed 2026-09-28). Verify approval flow during LOOP-12.
- Adapter notes: treat as optional secondary source; not required for first release.

### 1.7 Hacker News (Algolia) — hiring threads search
- Endpoint: `https://hn.algolia.com/api/v1/search_by_date?query=%22hiring%22&tags=story` (public, no key; useful for "Ask HN: Who is hiring" style monthly threads).
- Policy status: `ALLOWED_PUBLIC_API` (public read API).
- Source: https://hn.algolia.com/api (accessed 2026-09-28).
- Adapter notes: low-priority experimental source; requires thread parsing + dedup strength. Not for first release.

### 1.8 Company career pages & ATS public job boards (discovery tier 2)

Public, documented JSON endpoints published for candidate consumption:

- **Greenhouse Job Board API:** `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` — public JSON of published jobs, departments, offices; no auth. Source: https://docs.greenhouse.io/job-board.html (accessed 2026-09-28). Status: `ALLOWED_PUBLIC_API` (per-board).
- **Lever postings API:** `https://api.lever.co/v0/postings/{company}?mode=json` — public JSON of active postings. Source: https://github.com/lever/postings-api (documented public endpoint; accessed 2026-09-28). Status: `ALLOWED_PUBLIC_API` (per-company).
- **Ashby:** public posting API `https://api.ashbyhq.com/posting-api/job-board/{org}` (documented publicly; referenced by multiple aggregator projects). Status: `ALLOWED_PUBLIC_API` (per-org) — verify shape during LOOP-12.
- **Workday:** no stable public unauthenticated job-listing API; career sites are JS-rendered. Status: `ASSISTED_ONLY` (user opens the page; No_Loop can parse a pasted URL/page where permitted). Source: practitioner reports, e.g. https://www.reddit.com/r/workday/comments/1gq6n15/ (accessed 2026-09-28; UNVERIFIED-PRIMARY — treat as assumption until a primary Workday doc is found).
- Generic company career pages: fetch + parse where robots.txt and terms permit; status `PERMITTED_WITH_LIMITS` default, re-classified per domain by the policy register.

### 1.9 Prohibited / restricted portals (hard classification)

| Portal | Status | Basis |
|---|---|---|
| LinkedIn | `PROHIBITED` (automation), `ASSISTED_ONLY` (compliant workflow) | LinkedIn User Agreement §8.2 prohibits scraping and unauthorized automated access; "Prohibited software and extensions" help page lists auto-apply tools as violations. Sources: https://www.linkedin.com/legal/user-agreement (effective Nov 3, 2025) and https://www.linkedin.com/help/linkedin/answer/a1341387 (accessed 2026-09-28). |
| Naukri.com | `PROHIBITED` (automation), `ASSISTED_ONLY` | Terms & conditions prohibit using content/automated derivative use without written consent. Source: https://www.naukri.com/termsconditions (accessed 2026-09-28). No public candidate-side job API exists for this use. |
| Indeed | `ASSISTED_ONLY` | No public candidate-side API; ToS restrict scraping/automated access. Primary ToS URL to be pinned during next LOOP-12 run. |
| Foundit / Hirist / Instahyre | `ASSISTED_ONLY` | No public APIs; assume ToS restrictions until verified otherwise. Flagged UNVERIFIED — verify each during LOOP-12 before any adapter work. |
| Any site with CAPTCHA/anti-bot on application flow | `ASSISTED_ONLY` minimum | R-POLICY-2: never bypass; pause and hand control to the user. |

**Compliant assisted workflow for PROHIBITED/ASSISTED_ONLY portals (this is a product feature, not a gap):** No_Loop prepares the complete application package (tailored resume artifact, field-by-field answer sheet generated from confirmed facts, job-specific email, evidence summary), the user opens the portal and submits manually, then No_Loop records company/role/date/artifact version/status from user confirmation. This mirrors the user's own workflow: match → threshold → tailored resume → apply → tracker, with the human always the submitter where policy demands it.

---

## 2. Skill & occupation taxonomies (for matching + resume intelligence)

- **O*NET Web Services** (US DOL): free REST API; register for a developer key; occupation keyword search, crosswalks (incl. ESCO crosswalk). Sources: https://services.onetcenter.org/ and https://services.onetcenter.org/about (accessed 2026-09-28). Status: `USER_ACCOUNT_REQUIRED` (free). Use for title/occupation normalization.
- **O*NET database files**: full dataset downloads available; can be bundled (license/attribution per their terms) for offline-first operation — preferred so matching works with zero network.
- **ESCO API / dataset** (European Commission): ~3,000 occupations, ~14,000 skills; free API + downloadable CSVs, multilingual. Sources: https://esco.ec.europa.eu/en/use-esco/use-esco-services-api (accessed 2026-09-28). Status: `ALLOWED_PUBLIC_API` / open data. Use for skills normalization (extract skills from JDs and resumes, canonical skill IDs).
- **Offline strategy:** bundle a curated subset (skills for target tech roles) with the app; full taxonomy refresh is an optional user-triggered download. Keeps 2 GB baseline and no-key operation intact (R-ARCH-5, MASTER_SPEC §12).

---

## 3. AI providers (optional, user-owned)

| Mode | Status | Notes |
|---|---|---|
| NoAIProvider / RuleBasedProvider | Default, always available | App fully useful with zero AI (MASTER_SPEC §12). |
| BYOK cloud (e.g. Gemini/OpenAI-compatible) | `USER_ACCOUNT_REQUIRED` | User's own key in OS keychain; never bundled; privacy panel shows exactly what data would be sent (R-SEC-3). |
| Local model (Ollama/llama.cpp) | Optional | Only on machines with RAM headroom. Documented reality: ~1B models ≈ 1–2 GB RAM; 3B ≈ 2.5–4 GB; 7–8B Q4 ≈ 5–7+ GB. Sources: https://modelfit.io/models/llama/ and https://localllm.in/blog/ollama-vram-requirements-for-local-llms (accessed 2026-09-28). Never installed by No_Loop; only *used* if the user already runs it. |

---

## 4. Documents & extraction libraries (verified rationale)

- PDF: **PyMuPDF** — fast text extraction; check AGPL licensing implications (PyMuPDF is AGPL-3.0; using it as an unmodified library in a larger work is generally treated as separate work, but record the license decision in an ADR and evaluate alternatives (pdfminer.six, pypdf) if the human wants zero copyleft dependencies. Decision recorded in DEVELOPMENT_LEDGER.md before P004 implementation.
- DOCX: **python-docx** (MIT) — paragraph/table extraction.
- HTML/JD pages: **selectolax** (fast, low-memory) or **BeautifulSoup4**; pick one, do not install both (R-ENV-3).
- Similarity: **rapidfuzz** — deterministic fuzzy matching.
- HTTP: **httpx** — async, timeouts, HTTP/2 optional.

## 5. Desktop packaging references

- PyInstaller (onedir mode) + Inno Setup for Windows installer; MSIX optional later. Sources: https://pyinstaller.org/ and https://jrsoftware.org/isinfo.php (accessed 2026-09-28).
- UI shell decision space: PySide6 vs PyWebView vs Tauri per ARCHITECTURE.md; PySide6 is heavier — decide by benchmark (LOOP-11 footprint budget).

## 6. Resume formatting evidence (for generated artifacts)

ATs parse single-column layouts with standard headings most reliably; tables/columns/graphics/headers-footers break parsers; standard fonts (Arial/Calibri/Times) preferred. Sources (accessed 2026-09-28): https://www.jobscan.co/blog/ats-formatting-mistakes/ , https://resumeoptimizerpro.com/blog/ats-friendly-resume-tips . Generator templates (LOOP-7) must follow these rules; golden tests assert single-column structure.

## 7. Privacy law baseline

India DPDP Act 2023: consent must be free, specific, informed, unconditional, unambiguous; purpose limitation; data-principal rights incl. erasure. Sources: https://fpf.org/blog/the-digital-personal-data-protection-act-of-india-explained/ and https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Act,_2023 (accessed 2026-09-28). No_Loop treats these as design floor: explicit consent before any data leaves the device; export; delete-all (SECURITY.md).

---

## 8. Verification workflow (operates LOOP-12)

For each claim: (1) fetch primary source; (2) quote the operative text; (3) store URL + access date + quote in the register or ledger; (4) set review date; (5) if changed → update adapter POLICY_STATUS via LOOP-3 and open LOOP-8 review if it was automated. Claims not yet primary-verified are marked UNVERIFIED and must not gate any feature decision.

## 9. Reference-repo license register (cross-ref to PROVENANCE.md)

The 8 reference repositories (see `No_Loop_Open_Source_Reference_Research/`) were audited live on 2026-09-28 (NOLOOP_DEV_KICKOFF-spec §2). Licenses marked "stated" come from repo READMEs and MUST be re-verified from the LICENSE file at clone time; the authoritative record is `.references/PROVENANCE.md` (created at first clone, per R-ENV-6).

| Repo | Stated license | Reuse posture |
|---|---|---|
| Gsync/jobsync | UNVERIFIED at audit | Ideas-only until MIT confirmed on clone |
| SamlyticsDS/jobmatch-ai | MIT (stated) | MIT snippets OK with attribution |
| attdobi/aipply | UNVERIFIED | Ideas-only (LinkedIn automation: architecture study only, never ported) |
| AbhishekMandapmalvi/AutoApply | UNVERIFIED | Ideas-only until license confirmed |
| wadekarg/JobMatchAI | MIT (stated) | MIT snippets OK with attribution |
| ScottCoffin/Job_Scraper | AGPL-3.0 (stated) | **NO CODE REUSE EVER — ideas-only** (AGPL contamination risk) |
| Vigneshyadala/ai-job-application-bot | UNVERIFIED | Ideas-only until license confirmed |
| dsharm9148/job-apply-bot | UNVERIFIED | Ideas-only until license confirmed |

Gate for any snippet adoption: R-TRUTH-6 (in-code attribution + `docs/ATTRIBUTIONS.md` + ledger) + LOOP-9 security review. Unknown license = all-rights-reserved = ideas-only.

## 10. Adapter policy register (code-facing summary)

| Adapter | Discovery | Parsing | Application | Email | POLICY_STATUS |
|---|---|---|---|---|---|
| arbeitnow | API | API | manual-fallback | n/a | ALLOWED_PUBLIC_API |
| remotive | API | API | manual-fallback | n/a | ALLOWED_PUBLIC_API |
| remoteok | API | API | manual-fallback | n/a | PERMITTED_WITH_LIMITS |
| jobicy | API | API | manual-fallback | n/a | ALLOWED_PUBLIC_API |
| adzuna | API | API | manual-fallback | n/a | USER_ACCOUNT_REQUIRED |
| greenhouse | API | API | assisted-first | n/a | ALLOWED_PUBLIC_API (discovery) |
| lever | API | API | assisted-first | n/a | ALLOWED_PUBLIC_API (discovery) |
| ashby | API | API | assisted-first | n/a | ALLOWED_PUBLIC_API (discovery) |
| workday | none | none | assisted | n/a | ASSISTED_ONLY |
| linkedin | none | none | assisted | n/a | PROHIBITED (automation) |
| naukri | none | none | assisted | n/a | PROHIBITED (automation) |
| smtp | n/a | n/a | n/a | send-by-consent | USER_ACCOUNT_REQUIRED |
| local-draft | n/a | n/a | n/a | draft-only | ALLOWED_PUBLIC_API (no network) |

"assisted-first" for ATS application: opening the ATS application form is the user's action; No_Loop may pre-fill/copilot where the ATS's own terms permit browser assistance, else guided manual. Default release posture: discovery-automated, application-assisted.
