# RESEARCH.md — Strategy, Terminology & Innovation Baseline

This document converts the reference research pack + live-web research into concrete design strategies for No_Loop. It defines the project's vocabulary (so all docs and code share one language), the innovated strategies that differentiate No_Loop, and the workable solutions chosen per problem area. It is an input to every loop: design decisions here are binding unless an ADR supersedes them.

Sources: `No_Loop_Open_Source_Reference_Research/` (8 public projects analyzed) + live-web verification recorded in DATA_SOURCES.md (accessed 2026-09-28). Update via LOOP-12/LOOP-15.

---

## 1. Canonical vocabulary (use these terms everywhere; no synonyms in code/docs)

| Term | Meaning |
|---|---|
| **Canonical Profile** | The single confirmed structured candidate profile. Source of truth. Nothing edits it automatically. |
| **Derived Artifact** | Any generated output (tailored resume copy, email, answer sheet). Traceable to Canonical Profile + one Job. |
| **Confirmed Fact** | Profile datum the user explicitly verified. |
| **Inferred Fact** | Datum the extractor/pipeline *thinks* is true. Stored with confidence, never displayed as fact until confirmed. |
| **Evidence Map** | Mapping from every generated claim → confirmed fact(s) + job requirement(s). |
| **Fact Ledger** | The store of confirmed/inferred facts with provenance (which document, which field, which user action). |
| **Source Adapter** | Discovers jobs from one external system. |
| **Application Adapter** | Automates application steps on one target system within its POLICY_STATUS. |
| **Assisted Flow** | No_Loop prepares everything; the human performs the submit; No_Loop records it. |
| **Policy Status** | ALLOWED_PUBLIC_API / PERMITTED_WITH_LIMITS / USER_ACCOUNT_REQUIRED / ASSISTED_ONLY / PROHIBITED. |
| **Match Triangle** | Hard constraints (boolean gate) + soft score (weighted factors) + explanation (factor breakdown). |
| **Readiness Gate** | The state machine an application passes: DISCOVERED → SHORTLISTED → READY → DRAFTED → REVIEW_REQUIRED → SUBMITTED/FAILED → … |
| **Consent Envelope** | The per-action consent record: what data, to whom, for what, when, user decision. |
| **Loop** | A mandatory unit of development process defined in LOOPS.md. |
| **Closing Checklist** | The 7-step end-of-loop verification (LOOPS.md §0). |

## 2. Innovated strategies (what No_Loop does differently — from the user's idea + market research)

### S1. Threshold-based supervised pipeline (from the user's own workflow)
`Profile → AI/deterministic matching → match ≥ user threshold → tailored resume → application → tracker`, exactly the flow the user described, but with the No_Loop guarantees: the threshold gates *recommendations*, never silent submissions; every arrow in that chain is a ledger record.
**Workable solution:** MatchEngine emits `MatchResult`; ApplicationQueue only admits jobs whose hard constraints pass AND soft score ≥ threshold; every queue transition writes APPLICATION_LEDGER row + Consent Envelope when leaving REVIEW_REQUIRED.

### S2. Truth-preserving tailoring (anti-keyword-stuffing)
Commercial auto-apply tools invent keywords to pass ATS. No_Loop structurally cannot: the generator selects *from existing confirmed facts* and re-weights emphasis; it never creates experience. If a JD requires something absent, the gap is surfaced ("Missing requirement: Kubernetes (not in profile) — skip / learn / address in cover text?") and the user decides.
**Workable solution:** generation operates over a *selection projection* of the Fact Ledger, not free text; factual fields are assembled from facts; free-text is confined to tone/framing sections and is still evidence-mapped (LOOP-7 guard tests).

### S3. Assisted-first automation posture
Market tools claim Naukri/LinkedIn automation (ToS-violating). No_Loop inverts the tradeoff: automate where unambiguously permitted (public APIs, discovery), assist everywhere else, record everything. Differentiator honestly marketed: "we don't risk your account."
**Workable solution:** policy register (DATA_SOURCES.md §9) drives UI capabilities per job source at runtime; PROHIBITED sources render only the Assisted Flow UI.

### S4. Fact Ledger with dual-layer confidence
Borrowed from JobSync/JobMatch AI profile flows, upgraded: every field carries provenance + confidence + confirmation state, enabling dynamic onboarding (questions only for real gaps) and the no-fabrication guarantee.
**Workable solution:** `ResumeFact(provenance, confidence, state ∈ {inferred, confirmed, rejected})`; onboarding question generator diffs confirmed facts against target-role requirements (O*NET/ESCO-informed) and asks only what is missing/ambiguous (MASTER_SPEC §4).

### S5. Two-stage matching: cheap gate first, semantics second
From Job Scraper/JobMatch AI lessons: rank/filter deterministically before any expensive analysis. 
**Workable solution:** Stage 1 hard constraints + SQL-side filters (indexed) eliminate non-viable jobs; Stage 2 rapidfuzz scoring on survivors; Stage 3 optional AI explanation only for top-N displayed results. AI never runs per-job in bulk.

### S6. Evidence-first automation runs
From Aipply/AutoApply/ai-job-application-bot lessons (verification after submission, evidence logging), formalized: every AutomationRun captures structured evidence (field-by-field submission record, DOM snapshot hash, timestamps, outcome verification step). An application is SUBMITTED only with a completion signal (confirmation page marker, email receipt, or user confirmation); else VERIFICATION_REQUIRED.
**Workable solution:** `AutomationRun` schema with `evidence[]`; verifier heuristics per ATS adapter + user-confirmation fallback; ledger states per APPLICATION_LEDGER.md.

### S7. No-key, low-memory core with optional intelligence tiers
Tier 0 deterministic (always), Tier 1 rule-based NLG (template + selection, no model), Tier 2 BYOK cloud, Tier 3 local model. Each tier independently switchable; UI never blocks on a missing tier. Local-model guidance grounded in measured RAM needs (~1B≈1–2 GB, 3B≈2.5–4 GB, 8B≈5–7 GB) — auto-disabled below 8 GB total RAM.
**Workable solution:** provider interface from CURSOR_MASTER_PROMPT (`available/generate/structured_generate/explain/estimate_cost/privacy_info`); capability negotiation at startup; 2 GB machines run Tier 0/1 only (MASTER_SPEC §13).

### S8. Deduplication pipeline
Five-key dedup normalized across sources: (1) canonical URL, (2) source native ID, (3) company+title fuzzy pair (rapidfuzz ≥ threshold), (4) content fingerprint (normalized JD shingle hash), (5) cross-source company resolution (domain from ATS board token / career URL). Survivors of any two signals merge with provenance list.
**Workable solution:** `JobIdentity` resolver + `JobCluster` table; deterministic, tested on synthetic cross-source fixtures (LOOP-6 co-run).

### S9. Progressive onboarding (questions from gaps, not forms)
Instead of a 20-question wizard: parse resume → show inferred profile for one-click confirm/reject → ask only the questions generated from (target roles × missing data) → done. The user's profile (Python/AI-ML associate developer, Coimbatore/Chennai/Bangalore/Remote, 1+ yr, actual notice period, target salary) is the kind of data captured here.
**Workable solution:** question engine with rule templates per missing field class; every question editable/skippable; answers write Confirmed Facts.

### S10. Development truthfulness loop (the ledgers)
The project's own development is run like the product: PROGRESS.md gates claims, DEVELOPMENT_LEDGER.md records evidence, loops enforce process. This mirrors the user's "development/progress ledger" requirement and makes the repo self-auditing.

## 3. Competitor/reference capability map (what exists → what No_Loop adopts/rejects)

| Reference | Has | Adopt | Reject / upgrade |
|---|---|---|---|
| JobSync | provider abstraction, source adapters, local AI, confirmation gates, backup | Provider interface shape, discovery-first review gate | Self-hosted server assumption → pure local |
| JobMatch AI | CV parsing, multi-board discovery, tailored docs, tracker | Aggregation + doc-gen flow | AI-for-everything → deterministic-first (S5) |
| Aipply | Playwright automation, LinkedIn discovery | Isolated browser adapter pattern (LOOP-8) | LinkedIn automation → PROHIBITED (S3) |
| AutoApply | ATS workflow set, knowledge base, scoring | Adapter-per-ATS concept, knowledge-base retrieval | Blind submission → Readiness Gate + evidence (S6) |
| JobMatchAI (ext) | page analysis, auto-fill, skill gaps | Skill-gap view; analyze-current-page fallback | Extension-context assumptions → desktop app + assisted flow |
| Job Scraper | config-driven sources, dedup, no-server, CSV export | Source isolation, dedup pipeline, export | File-based store → SQLite with migrations |
| ai-job-application-bot | verification after submit, daily limits, thresholds | Verification, limits, thresholds as first-class settings | Gemini hard-wiring → provider abstraction (S7) |
| job-apply-bot | scrape→tailor→apply→log pipeline | Pipeline separation, threshold, logging | Log-only → full ledger + consent envelopes |

## 4. Open design decisions (ADR-required; do not silently pick)

1. **UI shell:** PySide6 vs PyWebView vs Tauri — decide by LOOP-11 footprint benchmark on the 2 GB profile. Lean PySide6 unless packaged footprint > budget.
2. **PDF library:** PyMuPDF (fast, AGPL) vs pypdf/pdfminer.six (permissive, slower) — ADR with license reasoning before P004.
3. **Persistence layer:** SQLModel vs raw SQLAlchemy Core — ADR; raw Core acceptable for lean memory.
4. **Taxonomy bundling size:** ESCO/O*NET subset curation — measure, then decide full vs subset bundle.
5. **Email send path:** SMTP-in-app vs mailto/client handoff first — draft-first is fixed; send path ADR at P009.

Each decision: use the Decision record template in DEVELOPMENT_LEDGER.md.

## 5. Terminology for legal/policy surfaces (consistent UI wording)

- "Automated" = performed by No_Loop without per-step human action (only on ALLOWED_PUBLIC_API / PERMITTED_WITH_LIMITS surfaces).
- "Assisted" = No_Loop prepares, human acts.
- "Verified" = evidence exists (automation) or user-confirmed (assisted).
- Never use: "auto-pilot", "100% automatic", "guaranteed pass ATS", "undetectable".
