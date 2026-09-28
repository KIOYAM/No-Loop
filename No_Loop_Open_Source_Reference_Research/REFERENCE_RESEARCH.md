# No-loop Reference Research Pack — 2026-09-28

This pack is a research baseline for No-loop. It focuses on publicly inspectable projects that overlap with resume parsing, job discovery, matching, application tracking, browser automation, and AI-assisted applications.

IMPORTANT:
- Open-source repositories can be inspected/cloned according to their licenses.
- Closed-source products do NOT expose their proprietary source code. This pack therefore records only publicly documented behavior, architecture hints, public docs, screenshots/demo claims, and observable workflows. It does not claim access to private code or internal systems.
- Website automation must respect each site's terms, robots/access controls, authentication requirements, rate limits, and applicable law. No-loop must never bypass CAPTCHA, MFA, anti-bot systems, paywalls, or access controls.
- A feature being present in another project does not mean it is safe/legal/appropriate to copy its implementation. We use ideas and interfaces, not copyrighted source code unless the license permits reuse.

## High-value references

1. JobSync
GitHub: https://github.com/Gsync/jobsync
License: inspect repository LICENSE before reuse.
Why relevant:
- self-hosted job-search assistant
- resume import
- AI resume review
- job matching
- automated discovery
- Greenhouse, Lever, Ashby discovery
- application tracker
- local Ollama support
- optional cloud providers
- MCP integration
- backup/restore

Key No-loop lessons:
- AI provider abstraction
- source adapters
- confirmation before saving AI-created jobs
- local-first data
- discovery first, review before application
- use fast deterministic relevance before expensive AI analysis

2. JobMatch AI
GitHub: https://github.com/SamlyticsDS/jobmatch-ai
License: MIT (as stated by repository)
Why relevant:
- local job search assistant
- CV parsing
- 10+ job-board discovery claims
- matching
- tailored CV/cover letter
- application tracker
- SQLite/local architecture

Key No-loop lessons:
- keep matching reusable
- deduplicate jobs
- separate search from ranking
- AI calls are expensive/slow; rank/filter first

3. Aipply
GitHub: https://github.com/attdobi/aipply
Why relevant:
- Python
- Playwright
- LinkedIn job discovery
- browser-based application automation
- resume/cover-letter tailoring
- application tracking

Key No-loop lessons:
- isolate browser automation from domain logic
- use Playwright only on demand
- store application evidence
- never let browser selectors leak into core business logic

4. AutoApply
GitHub: https://github.com/AbhishekMandapmalvi/AutoApply
Why relevant:
- local job application platform
- LinkedIn/Indeed search claims
- scoring
- tailored documents
- knowledge base
- multiple ATS workflows including Greenhouse, Lever, Workday, Ashby

Key No-loop lessons:
- knowledge base + deterministic retrieval
- adapter-per-ATS architecture
- configurable application criteria
- local-first workflow

5. JobMatch AI Chrome Extension
GitHub: https://github.com/wadekarg/JobMatchAI
License: MIT (as stated by repository)
Why relevant:
- job analysis
- skill gaps
- auto-fill
- cover letters
- resume bullet tailoring
- application tracking

Key No-loop lessons:
- analyze a page without requiring a full job-board crawler
- browser context can be a separate optional integration
- useful fallback: user opens a job and No-loop analyzes it

6. Job Scraper
GitHub: https://github.com/ScottCoffin/Job_Scraper
License: AGPL-3.0 (as stated by repository)
Why relevant:
- no server/paid-service approach
- scheduled scraping
- multi-source aggregation
- deduplication
- salary normalization
- triage dashboard
- CSV export
- optional AI scoring
- local execution

Key No-loop lessons:
- configuration-driven sources
- optional AI layer
- source enable/disable switches
- source-specific failure isolation
- no single source should break the system

7. AI Job Application Bot
GitHub: https://github.com/Vigneshyadala/ai-job-application-bot
Why relevant:
- Python/Flask
- Gemini integration
- Playwright
- multi-platform claims
- resume parsing
- application tracking
- success verification

Key No-loop lessons:
- explicit verification after submission
- daily limits
- configurable thresholds
- keep provider keys user-owned

8. job-apply-bot
GitHub: https://github.com/dsharm9148/job-apply-bot
Why relevant:
- scrape -> tailor -> apply -> log pipeline
- Playwright
- resume tailoring
- application threshold
- tracking

Key No-loop lessons:
- pipeline separation
- application threshold
- evidence logging

## Reference matrix

| Capability | JobSync | JobMatch AI | Aipply | AutoApply | JobMatch Extension | Job Scraper | No-loop |
|---|---|---|---|---|---|---|---|
| Resume import | Yes | Yes | Yes | Yes | Yes | Profile/config | Yes |
| Structured profile | Yes | Yes | Partial | Yes | Yes | Config | Yes |
| Job discovery | Yes | Yes | Yes | Yes | Page-based | Yes | Yes |
| Matching | Yes | Yes | Yes | Yes | Yes | Optional | Yes |
| Tailored docs | Yes | Yes | Yes | Yes | Yes | Prompt-based | Yes |
| Email drafting | Partial | Partial | Partial | Partial | Partial | Optional | Core |
| Application tracking | Yes | Yes | Yes | Yes | Yes | Yes | Core |
| Browser automation | Not core | Not core | Yes | Yes | Extension context | No | Adapter |
| Local AI | Ollama | Provider-based | No/varies | Provider-based | Provider-based | Optional | Optional |
| No AI mode | Yes for core flows | Partial | Limited | Limited | Limited | Yes | REQUIRED |
| Embedded DB | Yes/local | SQLite | Varies | Varies | Browser storage | Files | SQLite |
| Desktop-first | Not primarily | Local web app | Script | Local web app | Browser | Static dashboard | REQUIRED |
| No hosted backend | Yes/self-hosted | Yes/local | Yes | Yes/local | Yes | Yes | REQUIRED |

## What No-loop should borrow conceptually

A. From JobSync:
- provider abstraction
- company-source tracking
- local AI option
- confirmation gates
- backup/restore

B. From JobMatch AI:
- resume-to-job matching workflow
- job aggregation
- document generation
- local persistence

C. From Aipply / AutoApply:
- adapter-driven browser automation
- ATS-specific flows
- application evidence
- threshold-based application queue

D. From Job Scraper:
- source isolation
- configuration-driven discovery
- deduplication
- no-server operation
- optional AI

E. From JobMatch AI extension:
- analyze current job page
- auto-fill as a convenience layer
- skill-gap view

## No-loop differentiators

1. Single canonical candidate profile.
2. Dynamic onboarding based on resume gaps.
3. Job-specific email based on actual requirements.
4. No AI/API key required.
5. Optional BYOK provider support.
6. Optional local model support.
7. 2 GB RAM-aware core.
8. Desktop installer with automatic local DB setup.
9. Source/ATS/browser adapters isolated from domain logic.
10. Application evidence ledger.
11. Development/progress ledger.
12. User can add custom job targets and notes.
13. Assisted fallback for unsupported/blocked automation.
14. No fabricated candidate facts.
15. No silent submissions.

## Closed-source research rule

For commercial/closed products, inspect:
- public product pages
- help center
- API documentation
- terms
- privacy policy
- public demos/videos
- browser-visible behavior
- public technical talks/blogs
- job postings describing their stack, when relevant

Do NOT attempt to obtain private source code, credentials, internal endpoints, bypasses, or restricted data.

## Suggested next research targets

- Simplify/ATS adapter patterns
- Greenhouse public job-board behavior
- Lever public job-board behavior
- Ashby public job-board behavior
- Workday public career pages
- company career pages
- email provider abstractions
- PDF/DOCX extraction libraries
- Playwright reliability patterns
- local model runtimes suitable for low-memory machines
