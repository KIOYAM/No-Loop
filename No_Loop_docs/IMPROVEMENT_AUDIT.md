# No_Loop Improvement Audit — star-wise (2026-09-29)

Evidence-based: every rating comes from reading the current code (not from plans or claims).
Scale: ★☆☆☆☆ missing/stub → ★★★★★ production-ready and verified live.

| # | Capability | Stars | Verified state (evidence) | The improvement needed |
|---|---|---|---|---|
| 1 | **UI: Settings route** | ★☆☆☆☆ | `app.js` registers `settings: () => import("./routes/settings.js")` but **the file does not exist** → clicking Settings throws a lazy-load error | Create `routes/settings.js`: Gemini key form (write-only), AI provider/model picker, limits editor, data-location, language switcher. Reuse existing endpoints `/api/settings/gemini-key`, `/api/settings/ai`, `/api/ai/status`, `/api/ai/test` |
| 2 | **Sources / job discovery** | ★★☆☆☆ | Only `arbeitnow` (Germany-heavy — wrong region for an India-first product) + JD paste. Dedup + policy metadata are solid | Add 2 India-relevant sources behind the same port: **remotive** (free API, has remote-India) and **adzuna IN** (free key, `country=in`). Bounded pages + delay already in the fetcher pattern |
| 3 | **Packaging (LOOP-11)** | ★☆☆☆☆ | Nothing built — app runs only from a dev venv | Portable `.zip`: launcher script + embedded Python + `.local-data` beside the exe; relocation test in CI |
| 4 | **ATS fill-only automation** | ★☆☆☆☆ | `agent_run.py` classifies `ats_fill` targets but no fill adapter exists (v0.2 per spec — honest deferral) | v0.2: Playwright-based fill-only adapter, field-reliability log, dry-run first (spec §11). NOT before assisted flow is polished |
| 5 | **AI in the pipeline** | ★★☆☆☆ | GeminiProvider is real (REST, mock-transport tests) and the registry works — **but `agent_run.py` line 351 hardcodes `EmailDrafter(RuleBasedProvider())`** so the user's Gemini key is never actually used in drafting | Route drafter + answerer through `AIRegistry` (auto → gemini → local → rule) with per-call fallback + cost estimate shown in UI. Then validate once with a real key |
| 6 | **Live-ops: discovery refresh** | ★★☆☆☆ | Every discovery is manual; no scheduling | Optional bounded auto-refresh (per-profile interval, max pages, cooldown respected) with a UI toggle — default OFF, respects caps |
| 7 | **Assisted flow (LinkedIn/Indeed)** | ★★★☆☆ | Policy registry + `build_assisted_package` + agent-run integration + ledger recording all exist | UI surface: package viewer with copy-per-answer buttons and "mark outcome" flow; today the package is stored but has no dedicated screen |
| 8 | **Resume handling** | ★★★★☆ | TXT/DOCX/PDF all real (pypdf — ADR-2 closed, BSD); layout-aware reading order (column split *before* y-clustering, DOCX body order, page offsets for `provenance.page`); decoder (BOM/UTF-16/encrypted-detect) wired where files enter + hash-dedup + version history; layered extraction (`resume_sections` → `resume_records` → `skill_taxonomy`) with coverage + ATS parseability reports; golden harness measures it (5 fixtures, micro F1 0.997 / precision 1.000) | OCR extra for scanned PDFs; content-based classification of headings we do not recognise (today the project under "SOME THINGS I'VE BUILT" is missed); source-highlighted confirmation UI — see `No_Loop_docs/RESUME_PROCESSING_UPGRADE.md` |
| 9 | **Dynamic question answering** | ★★★☆☆ | `QuestionAnswerer` wired into agent runs; no-fabrication guards + ambiguity flags tested | Add AI tier for free-text questions (currently rule-based fact lookup only); cache repeated answers per profile |
| 10 | **Storage** | ★★★☆☆ | JSON behind a swappable port (honest interim); works at current scale | Execute **ADR-6 benchmark** (already the declared first ADR) → decide SQLite; write-behind cache for UI upserts |
| 11 | **Memory across the process** | ★★★☆☆ | Facts ledger + profiles + resume versions persist; fact-sheet feeds matching/drafting | Cross-run learning: per-question answer memory (never re-ask), match-feedback loop (thumbs up/down adjusts weights) |
| 12 | **Reports** | ★★★☆☆ | Backend CSV/JSON/HTML + reports.js exist; downloads verified | Add funnel visualization (discovered→submitted) on the dashboard using existing counts |
| 13 | **Live UI (SSE)** | ★★★☆☆ | Push-based, no polling; slow-client drop tested; heartbeat | Backpressure benchmark (LOOP-10) + reconnect-with-backoff on the client (partial in sse.js — verify) |
| 14 | **i18n** | ★★★☆☆ | i18n.js + `data-i18n` attributes; EN/TA/HI catalogs present | Complete untranslated strings audit; release gate per ARCHITECTURE (grep for hardcoded user-facing strings) |
| 15 | **Test/CI gates** | ★★★★☆ | 368 tests (unit + contract + integration + a golden resume benchmark with F1 floors); ruff + mypy clean; contract+integration suites | Add `fail_under` coverage gate (currently unset) + one real-browser smoke (Chrome headless) |
| 16 | **Domain + invariants** | ★★★★★ | Evidence rules, consent gates, caps gate, transitions — all enforced in domain and proven at runtime | Keep as-is; only extend (e.g., per-source caps) |
| 17 | **Matching engine** | ★★★★★ | Hard gates verified against live data (German-onsite correctly rejected vs Chennai/Remote); explainable factors; both sides now canonicalise through `app/adapters/skill_taxonomy.py` (148 canonical skills / 293 surface forms, boundary-safe C++/C#, prose-word gating), so "REST api" ≈ "REST APIs" | Weights tuning UI; ESCO URI mapping stays `None` on purpose (no guessing) |

## Suggested next 5 tasks (highest impact first)

1. **Fix the Settings route (P0 bug)** — file missing; ~1 hour; unblocks key entry from UI.
2. **Route AI through the registry** — replace the hardcoded `RuleBasedProvider` in `agent_run.py`; your Gemini key then actually drives drafting/answers, with rule fallback.
3. ~~**Wire `resume_edgecases` into the import pipeline** + pick BSD-licensed PDF library (closes ADR-2).~~ **DONE 2026-09-30** — decoder runs in `profile_service.import_resume` (the path where bytes enter), ADR-2 closed on pypdf 6.19.0 (BSD); the parser itself was then rebuilt (sections/records/skills + golden F1 harness). Next in that thread: source-highlighted fact confirmation (P1 of `RESUME_PROCESSING_UPGRADE.md`).
4. **Add remotive + adzuna-IN sources** — makes discovery India-relevant instead of Germany-heavy.
5. **Assisted-package UI screen** — makes the compliant LinkedIn/Indeed flow usable end-to-end by a human.
