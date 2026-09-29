# Gap Analysis vs References + Platform Automation Map (2026-09-29)

Sources: the 8 `.references/` repos (license-gated per R-ENV-6), DATA_SOURCES.md §1.9,
R-POLICY-1..6, and 2026 market research (auto-apply tools, India portals).
Scale: ★☆☆☆☆ missing → ★★★★★ production-ready. "Adoptable" = the reference is MIT
(snippets/ideas usable); "ideas-only" = unlicensed/AGPL, we learn concepts only.

## Part A — Important things the references have that No_Loop still lacks

| # | Capability (source repo) | Stars in No_Loop today | What the reference does | The improvement we should build | Adoptable? |
|---|---|---|---|---|---|
| A1 | **Knowledge Base with reuse** (AutoApply) | ★☆☆☆☆ | Upload career documents once (projects, achievements, blurbs); entries categorized; TF-IDF ranks the most relevant entries per job; zero API calls | A `knowledge_base` collection in our store: typed entries (project / achievement / story / blurb), selected per-JD by our match engine's skill overlap + a TF-IDF rank (pure Python, stdlib `math`), injected into drafting with evidence maps | **MIT — adopt fully** |
| A2 | **Interview-prep pack per job** (jobmatch-ai Next.js) | ★☆☆☆☆ | One click generates a `.docx` prep pack: likely questions from the JD, answer outlines from confirmed facts | "Prep" artifact type in the pipeline: JD-derived question list + fact-grounded answer sketches; rendered with the ADR-7 renderer (same DOCX path as resumes) | MIT (jobmatch-ai ext is ideas-only, but the Next.js repo IS MIT) |
| A3 | **Resume tailoring / per-JD rewrite** (AutoApply, aipply, job-apply-bot) | ★★☆☆☆ | AI rewrites bullet points targeted at each JD's keywords; exports tailored PDF/DOCX per application | v0.1-compliant version: **tailoring suggestions** (which confirmed facts to emphasize, which keywords are missing) + assemble a tailored variant from Knowledge Base entries. Full auto-rewrite is AI-tier work we can do with Gemini — but every rewritten claim must trace to a confirmed fact (R-POLICY-6) | MIT + ideas |
| A4 | **ATS match score for your resume** (AutoApply `resume_scorer.py`, JobMatchAI) | ★★☆☆☆ | TF-IDF cosine similarity between resume text and JD text → 0-100 "ATS score" before you apply | Add `ats_score` to MatchResult as a *text-similarity* factor (cheap, local, stdlib). Distinct from our structured skill-overlap; useful when JD text is free-form | **MIT — adopt the math** |
| A5 | **Application documents library** (jobsync) | ★★☆☆☆ | Resume library with versioning + export templates (Simple/Professional PDF) | We have version history; missing **template rendering to PDF/DOCX** — that's exactly ADR-7 (`reportlab` already registered). One template, three sections, done | MIT |
| A6 | **H1B / employer-intel lookup** (JobMatchAI) | ★☆☆☆☆ | Checks employer's sponsorship history from public datasets before you apply | India-first variant: company notes (exclusion list exists; add per-company metadata: notes, blacklist, past-outcome stats from our own ledger) — no external dataset needed, our ledger IS the dataset | MIT ext is unlicensed → ideas-only, but our own-ledger variant is cleaner |
| A7 | **Scheduled unattended runs** (AutoApply scheduling, Job_Scraper GitHub Actions) | ★☆☆☆☆ | Set days/hours for the bot to run; or cron-driven scrapes with a triage dashboard | Bounded scheduler: per-profile windows (already have active-hours gate in queue!), auto-discover + auto-match on schedule, results waiting for review. All caps still apply; assisted flow only | MIT concepts |
| A8 | **Email alerts / notifications** (Job_Scraper phone notifications) | ★☆☆☆☆ | Optional phone/email notification on new matches | Optional local SMTP notify with explicit consent (R-SEC-3): "N new matches above threshold" — send only what user approved | MIT concept |
| A9 | **Company exclusion across discovery** (aipply) | ★★★☆☆ | Skip-list applied during search | We have `excluded_companies` in TargetPreference — but verify it's enforced in the discovery gate, not just matching | (already partly ours) |
| A10 | **MCP / external agent integration** (jobsync) | ★☆☆☆☆ | Local MCP server so Claude Desktop can add jobs/questions from chat | Interesting but v0.2+; our CLI already covers the "external tool" role | MIT concept |
| A11 | **Test depth** (AutoApply: 1385 tests) | ★★★☆☆ | Massive suite incl. i18n, accessibility, security, migration tests | We have 239 — good ratio for our size, but add: i18n completeness test, SSE backpressure, migration/corruption tests when SQLite lands | n/a (practice, not code) |
| A12 | **Resume PDF/DOCX export** (all 4 doc-producing repos) | ★☆☆☆☆ | Every reference exports real documents | **ADR-7 is the single biggest blocker** — reportlab is already in the dependency register, nothing built. Blocks A2, A3, A5 | adopt pattern |

**Top 3 by impact:** A12 (document export — unblocks 3 other features), A1 (Knowledge Base — multiplies drafting quality), A4 (ATS text score — cheap, differentiating).

## Part B — Platform & company-portal automation map (the honest version)

This is where most references cheat. AutoApply, aipply, job-apply-bot all auto-submit on
LinkedIn/Indeed/Naukri — which **violates those platforms' ToS** (their own READMEs admit it:
AutoApply line 212: "may violate the Terms of Service... you are solely responsible").
LinkedIn's help page literally lists auto-apply extensions as "Prohibited software" (§8.2,
verified in DATA_SOURCES §1.9). We will not build that. Here is what we build instead,
per platform:

| Platform (India relevance) | Automation status | What No_Loop does today | What we add | Who's already doing it (and the risk they take) |
|---|---|---|---|---|
| **LinkedIn** | 🔴 PROHIBITED (UA §8.2) — assisted only | Assisted package + manual record | **Easy-Apply question sheet**: the standard Easy-Apply question set (years, salary, notice, location) pre-filled from confirmed facts, copy-per-answer; "open LinkedIn" deep link per job; paste-back outcome recording | Every bot tool (LoopCV, EasyApply exts, aipply...) — account-restriction/ban risk is documented; we stay out |
| **Naukri.com** | 🔴 PROHIBITED — assisted only | Assisted package | Naukri profile-completeness checklist (their recruiter-search ranks complete profiles higher) + resume-headline suggestions from confirmed facts; assisted package mirrors their application form fields | "Naukri AutoApply" bots on GitHub — ToS violation, flagged in their own posts |
| **Indeed** | 🟡 ASSISTED_ONLY | Assisted package | Quick-Apply answer sheet (Indeed's flow is short; a 5-question sheet covers ~90% of it) | Indeed auto-apply tools — same ToS problem |
| **Instahyre / Hirist / Foundit** | 🟡 ASSISTED_ONLY (UNVERIFIED — verify in LOOP-12) | Assisted package | One-click "open job" + package; Instahyre's "one click apply" is genuinely one click for humans — our job is to have everything ready | No verified automation path exists publicly |
| **Wellfound (AngelList)** | 🟡 ASSISTED_ONLY | — | Startup-specific answers (equity expectations, why-startup) from KB entries | — |
| **Cutshort** | 🟡 ASSISTED_ONLY | — | Their skill-quiz style screening prep from facts | — |
| **Company career portals (the real volume): Workday, Greenhouse, Lever, Ashby, SuccessFactors, Taleo** | 🟢 FILL-ONLY allowed (public candidate forms; the candidate is *meant* to fill them) | `platform_policy` registry knows these; agent classifies `ats_fill` | **This is our automation sweet spot** (see Part C) | AutoApply + job-apply-bot auto-submit here — allowed by most ATS ToS but we still keep the human click until fill-telemetry is proven (spec §11) |
| **SMTP email applications** | 🟢 permitted with consent (R-SEC-3) | Draft only | One-click "open in mail client" with to/subject/body pre-filled (`mailto:`) — zero server, zero risk | — |

### Part C — Company-portal (ATS) fill-only plan — our differentiator

Most Indian product companies + all MNCs run their own career portals on Workday /
Greenhouse / Lever / Ashby. These are **public candidate forms** — automating the *fill*
is the normal expected use; only the final Submit stays human (v0.1 contract, spec §11).

Build order (this is the v0.2 auto-submit decision path):
1. **Greenhouse fill adapter** (MIT reference exists in AutoApply's `apply/` module — MIT, adoptable): parse the public job-board JSON API for the form schema, fill via Playwright, log every field's reliability
2. **Lever** (same pattern, simpler form)
3. **Workday** (heaviest; session-based; do last)
4. Every fill run records: field id → value → source fact → confidence → whether the field errored. That telemetry is the **field-reliability log** that the spec says gates the v0.2 auto-submit decision.
5. CAPTCHA/MFA anywhere → `AutomationBlockedError` → pause + hand to user (already built in domain)

What we do NOT build, ever (R-POLICY-2/3): LinkedIn/Naukri bots, CAPTCHA solving, fingerprint
spoofing, fake "human-like" delay patterns to evade detection, scraping behind login walls.

## Part D — Priority order combining A + C

| Rank | Work | Why now |
|---|---|---|
| 1 | **ADR-7 document rendering** (A12) → PDF/DOCX export + tailored resume variant | Unblocks A2, A3, A5; reportlab already registered |
| 2 | **Knowledge Base + TF-IDF selection** (A1, A4) | Biggest drafting-quality multiplier; pure local code |
| 3 | **Greenhouse fill-only adapter** (C1) | The lawful automation story; MIT reference code to adapt; telemetry feeds v0.2 |
| 4 | **Easy-Apply/Naukri answer sheets** (B rows 1-2) | Makes the assisted flow actually fast on the biggest platforms |
| 5 | **Scheduler** (A7) | "Works while you sleep" — bounded, capped, assisted |
| 6 | Employer intel from own ledger (A6) | Differentiator that no reference has cleanly |
