# Resume Processing Upgrade — full analysis & roadmap (2026-09-30)

Goal: take LOOP-5 (resume intelligence) from ★★★☆☆ to ★★★★★ ("very high"),
without breaking the binding principles: local-first, tiered optional AI,
fill-only profile merge, **no fabrication ever**, ledger-recorded.

Every rating below comes from reading the current code, running the current
parser, and checking it against external research (references in §10).

---

## 0. Implementation status (2026-09-30, end of day)

The analysis below was written first, then executed as P0–P2 core. Reproduce
every number with `python scripts/bench_resume.py` (or
`python -m pytest tests/benchmarks -q`).

| Roadmap item | State | Evidence |
|---|---|---|
| P0.1 boundary-safe matching (`c++`, `c#`, `node.js`) | done | `skill_taxonomy.extract_skills` uses `(?<!\w)…(?!\w)`; `tests/unit/test_skill_taxonomy.py` |
| P0.2 `imported_at`, dead code, reportlab pin | done | `profile_service.ProfileService` uses `datetime.now(UTC)` |
| P0.3 fuzzy + alias headings | done | `resume_sections.split_sections` — "WORK EXPERENCE" → `experience`, prose never a heading |
| P0.4 `provenance.span` / `.page` | done | every rule-path fact carries a span; PDFs carry page offsets |
| P0.5 open-vocabulary skills + `normalized_name` | done | `skill_taxonomy` — 148 canonical skills / 293 surface forms, ambiguity-gated |
| P0.6 stale audit entries | done | `IMPROVEMENT_AUDIT.md` rows 8/15/17 + suggested task 3 refreshed |
| P1.7 golden harness + CI gate | done | 5 fixtures + hand-written `gold.json`, micro **F1 0.997** (P 1.000 / R 0.993), floors 0.90/0.85 + zero-hallucination rule |
| P1.8 layout-aware PDF ordering | done | column split before y-clustering + 60% word-count safety net; `tests/unit/test_layout_extraction.py` |
| P1.9 employment/education/certs/dates/projects as facts | done | `resume_records.py`; live sample went 9 → 26 facts, coverage 77% |
| P1.10 coverage + parseability in the import result | done | `parseability.py`; surfaced in `ImportResult` and the profile/resume UI |
| P1.11 AI pass: window, grounding, agreement confidence | done | `resume_pipeline._select_window` + `source_text` grounding (0.9 / 0.7 / 0.8 legacy) |
| P2.12 taxonomy normalizer → `MatchEngine` | done | both sides canonicalise in `match_engine.py` |
| P2.15 timeline intelligence (ISO ranges, computed tenure) | done | `find_date_ranges` / `tenure_years`, month arithmetic |
| P2.16 `ResumeDocument` entity (structure only, no raw text) | done | `profile_service` persists `resume_documents` |
| P2.13 local small-model tier | **not started** | gated by the eval harness |
| P2.14 optional OCR extra | **not started** | `RESUME_PROCESSING_UPGRADE.md` §L2 keeps it an honest refusal until then |
| P3.17–19 ATS panel / semantic score / multilingual | **not started** | ES/PT section + title seeds shipped as a preview, full multilingual remains P3 |

**Known gap the harness refuses to hide:** `nonstandard-headings` misses one
project (`Traceview: …`) because it sits under an invented heading ("SOME
THINGS I'VE BUILT"). Headings we do not recognise are still reported verbatim
in `structure.unrecognized_headings`, but their *content* is not yet
classified — that is the next item on this thread (content-based section
classification), and the F1 floor is what will tell us we closed it.

---

## 1. What resume processing does today

```
UI/CLI → POST /api/resume/import (app/ui/server.py:445) → background thread
  └─ ResumePipeline.run (app/services/resume_pipeline.py:212) — 11 SSE stages
       upload → validate → dedupe → detect → extract → parse → persist
             → autofill → ai → profile → done
       ├─ ResumeService.import_resume (app/services/profile_service.py:66)
       │     hash-dedupe · magic-byte / encryption detection · extractors
       ├─ extractors: TxtExtractor | DocxExtractor(python-docx) | PdfExtractor(pypdf)
       ├─ facts_from_resume.parse_resume_text   ← section aliases + regex + 53-skill vocab
       ├─ profile_autofill.suggest_profile_fields (fill-only)
       └─ optional AI pass (Gemini / local OpenAI-compatible / rule fallback)
  state==confirmed facts → MatchEngine · ResumeAssembler · ats_score · ATSFillPlanner · QuestionAnswerer
```

**What is genuinely good (keep it):**
honest-failure extraction contract (`app/ports/__init__.py:76-92`), encrypted /
scanned / corrupt-PDF detection, SHA-256 + normalized-hash dedupe, encoding
fallback chain with mojibake guard (`resume_edgecases.py:30`), staged observable
pipeline over SSE, fill-only autofill, fact state machine with mandatory
provenance (`domain/facts.py`), raw text never persisted, AI-never-fails design.
That is ★★★★ architecture and ★★★ discipline.

## 2. Scorecard

| # | Area | Stars | Evidence |
|---|---|---|---|
| 1 | Pipeline orchestration, stages, SSE, honest failures | ★★★★★ | `resume_pipeline.py:212-401`, 35 tests in `test_resume_pipeline.py` |
| 2 | Format / edge-case intake (encoding, encryption, hash) | ★★★★☆ | `resume_edgecases.py`, `test_platform_and_resume.py:72-113` |
| 3 | Fact ledger + provenance invariants | ★★★★☆ | `facts.py:87-155` — but `page`/`span` are **never populated** |
| 4 | **Layout / reading order (PDF, columns, tables)** | ★★☆☆☆ | pypdf `extract_text()` in content-stream order; no bboxes, no column logic |
| 5 | **Field extraction coverage** | ★★☆☆☆ | only `skill` + `experience_years` become facts (`facts_from_resume.py:161-197`) |
| 6 | Section detection | ★★☆☆☆ | exact alias, `len(line) < 60`, 6 headings (`:107-130`) |
| 7 | Skill vocabulary | ★★☆☆☆ | closed 53-skill tuple (`:26-79`); everything else silently dropped |
| 8 | **Evaluation / benchmarking** | ★☆☆☆☆ | no golden files, no `tests/benchmarks/`, no P/R/F1, no `fail_under` gate |
| 9 | OCR for scanned / image resumes | ☆ | deliberate v0.1 deferral (`MASTER_SPEC.md:45`); `<20 words` heuristic only |
| 10 | AI-tier quality controls | ★★★☆☆ | good anti-fabrication prompt, but head 9k + tail 3k trim **loses the middle of long resumes**; confidence fixed at 0.8 |

### Live evidence of the ceiling

Running `parse_resume_text` on a realistic resume (name, email, phone, city,
LinkedIn, summary, two employers with titles and date ranges, 10 skills
including C++/C#, degree, certification):

```
facts produced : 8 skills + 1 experience_years  = 9
sections       : skills, education, certifications
ambiguities    : "Section 'experience' not found — confirm manually"
```

MASTER_SPEC §3 requires name, contact, summary, education, employment, dates,
titles, achievements, projects, technologies, certifications, links and
locations. Expected ≈ 18–20 facts; produced 9 (≈45%), of which **0** cover
education/employment/title/date. `email`/`phone` come back as strings and never
become provenance-bearing facts.

## 3. Defects found during this analysis (fix first)

1. **`c++` and `c#` can never be detected.** `_KNOWN_SKILLS` matching uses
   `r"\b" + re.escape(skill) + r"\b"` (`facts_from_resume.py:166`). `\b` after
   a non-word character never asserts, so `'Skills: C++'` does not match.
   Verified: `re.search(r'\bc\+\+\b', 'Skills: C++')` → `None`. Two of the 53
   skills are dead, and the same pattern drives level detection.
2. **`imported_at` is never a timestamp** — `"imported_at": version and None`
   (`profile_service.py:174`).
3. **`_naive_text_layer` is dead code** (`extractors.py:167-179`).
4. **pyproject/lock mismatch** — `reportlab>=4,<5` (`pyproject.toml:11`) vs
   `reportlab==5.0.1` (`requirements.lock.txt:32`).
5. **`IMPROVEMENT_AUDIT.md:15` is stale** — it claims `resume_pipeline.py` does
   not use `resume_edgecases`; the pipeline delegates to
   `ResumeService.import_resume`, which calls `decode_bytes`
   (`profile_service.py:118`). The decoder *is* on the path.
6. Phone regex is India-only (`facts_from_resume.py:85`) and no ambiguity is
   raised when a non-Indian number fails to match.

## 4. What "very high" means — measurable targets

| Metric | Today (est.) | Target | Reference bar |
|---|---|---|---|
| Field-level F1 (skills, experience, education, contact) | ~0.45 recall | ≥0.90 micro | Layout-aware LLM pipeline: Claude-4 naive 0.927 → 0.946 F1 (arXiv 2510.09722) |
| Contact-info accuracy | ~0.90 | ≥0.97 | Open-source LeverParser claims 95% contact / 90% experience / 85% education / 80% skills |
| Section detection | fragile exact match | ≥0.95 incl. typos & non-standard headings | ATS studies: non-standard headings are a top parse-failure cause |
| Fact coverage per import | ~45% | ≥90% of §3 fields found or explicitly flagged | — |
| Layout robustness (2-column, tables, header/footer) | unknown | ≥0.90 on an adversarial fixture set | EDLIGO 2025: tables/multi-column fail **31%+** vs ~4% plain DOCX |
| Confirmation time | unmeasured | <60 s median, ≥70% confirmed first pass | UX KPI |
| Regression | none | CI blocks any drop >1 pp on the golden set | `LOOPS.md:95` |

Commercial parsers market 95–98% (Affinda, DaXtra ~95%, Parseur ~95%,
Hirize ~98%) — marketing figures, but they set user expectations.

## 5. Gap analysis by layer

### L1 — Text extraction & layout (largest structural gap)
pypdf returns text in *creation* order, not reading order: no bboxes → no
column detection, no header/footer detection, no table structure. Two-column
resumes (38% of real resumes in the ATSChecker 2026 sample; 31% parse-failure
rate) interleave. DOCX tables are flattened to `" | "` rows
(`extractors.py:81-87`) — exactly the "cells merge / order shuffles" ATS failure.

Options and licences:
* **pdfplumber / pdfminer.six (MIT/BSD)** — per-character coordinates, word
  bboxes, `layout=True`, table extraction. Benchmarks: PyMuPDF ~180 pages/s vs
  pdfplumber ~18 pages/s, but pdfplumber wins table accuracy (TEDS 0.847 vs
  0.692) and is permissive. For 1–10 page resumes, speed is irrelevant and
  licence matters (ADR-2 already rejected PyMuPDF/AGPL).
* **pypdf visitor API (already a dependency)** — `page.extract_text(visitor_text=…)`
  yields `(text, cm, tm, font, size)` so bboxes can be derived with **zero new
  dependencies**; enough for line clustering + column reordering.
* **Layout models** (PyMuPDF-Layout, Docling — DocLayNet overall F1 0.827–0.836
  vs 0.810) — real quality, but model weight conflicts with the 2 GB RAM
  baseline. Defer behind an optional extra.

### L2 — OCR (currently a hard stop)
`<20 words` → refuse. Correct for v0.1; "very high" means converting the
refusal into a path: detect image-only → optional local OCR (RapidOCR
Apache-2.0/ONNX, or Tesseract Apache-2.0) → same pipeline with
`extraction_rule="ocr"`, confidence 0.5–0.6, mandatory user confirmation.
Opt-in extra only (RAM + honest-dependency rules); OCR noise + LLM is the
single biggest fabrication risk, so every OCR-sourced fact must be confirmed.

### L3 — Section detection
Exact alias + `<60 chars` is the highest-leverage cheap fix: fuzzy match
(RapidFuzz is already a dependency), alias/prefix variants ("work experience",
"employment history", "professional journey", "my story"), decoration stripping
(`====`, colons, bullets), and layout/font signals as a second signal. Must run
on layout-ordered text, or a sidebar "Skills" heading grabs the wrong block.

### L4 — Entity extraction coverage (the spec gap)
Only skills + experience-years become facts. Employment records, education,
certifications, projects, date ranges, tenure, name, location and
international phone are either absent or live as low-confidence autofill
suggestions parked in `profile.extra.resume_suggestions` **with no
provenance** — so they can never be confirmed and never feed the assembler.

### L5 — Skill vocabulary & taxonomy
53 hard-coded skills silently drop everything else, from the **rule and AI
paths alike** (`_facts_from_ai` gates to `KNOWN_SKILLS`). `SkillClaim.normalized_name`
exists in the schema and is never populated — the swap-point already flagged
in `IMPROVEMENT_AUDIT.md:24`. Direction: open-vocabulary detection → normalizer
→ canonical name + optional ESCO/O*NET id. Reference: ESCoE Skills Extractor
Library (6% inappropriate extractions, 88% correct ESCO mapping — a realistic
ceiling), ESCO v1.2 (~13,500 concepts with preferred/non-preferred/hidden
terms = a ready-made alias source), O*NET with the official O*NET↔ESCO crosswalk.

### L6 — AI tier
Head 9k + tail 3k trimming never shows the model the middle of a long resume —
often exactly where experience lives. No self-verification of claims. Fixed
0.8 confidence. Fixes: section-aware window selection, grounding verification
(every extracted string must occur in the source, else drop), JSON-schema
output, agreement-based confidence (rule+LLM 0.9 / LLM-only 0.7 / OCR 0.5),
and a small local model tier (the Alibaba paper shows a fine-tuned 0.6B model
reaches top-tier accuracy — the right shape for "no mandatory API key").

### L7 — Evaluation (the actual multiplier)
Nothing exists. You cannot improve what you do not measure, and `LOOPS.md:95`
plus `skills/03_resume_intelligence.md:19` both require golden files.

## 6. Target architecture

```
intake (magic bytes · size · encoding · hash dedupe)
  └─ LAYOUT EXTRACT     pypdf visitor / pdfplumber words+bboxes | python-docx | txt
        → line clustering → column clustering → reading order → header/footer strip
  └─ OCR? (image-only, optional extra, rule="ocr", conf ≤0.6, always confirm)
  └─ SEGMENT            fuzzy heading detection + layout signals → sections (with spans)
  └─ EXTRACT (tiered)
        T0 deterministic: contact, open-vocab skills + aliases, date ranges, tenure,
                          employment/education/cert/project records → facts + spans
        T1 section-aware: record assembly (title | employer | dates lines)
        T2 BYOK/local LLM: JSON schema per document + grounding verification
  └─ NORMALIZE          skill → canonical + ESCO id · dates → ISO · location → gazetteer
  └─ REPORT             per-field confidence · ambiguity list · coverage % · parseability
  └─ CONFIRM UX         source-highlighted review → confirmed facts
  └─ PERSIST            ResumeDocument (structure + spans + hashes, NO raw text) + facts
  └─ EVAL (CI)          golden set → field P/R/F1 → regression gate
```

## 7. Roadmap

**P0 — quick wins (no new dependencies)**
1. Fix the `\b` boundary bug; boundary-safe matching for `c++`, `c#`, `node.js`.
2. `imported_at` timestamp; remove dead `_naive_text_layer`; reconcile reportlab pin.
3. Fuzzy + alias section headings (RapidFuzz already installed).
4. Populate `provenance.span` (and `page` where available) from the rule path.
5. Open-vocabulary skill extraction with an alias → canonical table; populate `SkillClaim.normalized_name`.
6. Correct the stale audit entries (item 5 above).

**P1 — correctness (1–2 weeks)**
7. **Golden-file evaluation harness + CI gate** (build before/with everything else).
8. Layout-aware PDF ordering: bboxes → lines → columns → reading order.
9. Extract employment / education / certifications / date ranges / projects as facts.
10. Coverage + parseability report surfaced in the import result and UI.
11. AI pass: section-aware window, grounding verification, agreement-based confidence.

**P2 — "very high" (2–6 weeks)**
12. Skill taxonomy normalizer feeding `SkillClaim.normalized_name` and `MatchEngine`.
13. Local small-model Tier behind `LocalLLMProvider`, gated by the same eval.
14. Optional OCR extra with OCR-flagged low confidence + mandatory confirmation.
15. Timeline intelligence: ISO date ranges, computed tenure, gap detection.
16. `ResumeDocument` entity + ADR-6 SQLite move (structure + spans, still no raw text).

**P3 — differentiation**
17. "What an ATS sees" panel: run our parser over our own rendered resume and
    show the extracted field stream + parseability score (renderer is already
    single-column/ATS-safe — now we can *prove* it).
18. Semantic ATS score beyond TF-IDF cosine (local embeddings or LLM judge),
    keeping TF-IDF as deterministic Tier 0.
19. Resume↔JD gap analysis: missing must-have skills with "add if true" prompts.
20. Multilingual resumes (Hindi/Tamil transliteration; ESCO ships 29 languages).

## 8. Evaluation harness design

* **Golden set:** 30–60 fixtures — single-column, two-column, table-based,
  header/footer-heavy, icon/skill-bar, scanned/image, UTF-16/BOM, non-standard
  headings, Indian/US/EU formats, fresh-grad, career-changer, 2-page,
  multilingual — each with a `gold.json`. `.references/jobsync/evals/resume-import/fixtures/`
  is exactly this shape (reference only, licence-gated, per `ATTRIBUTIONS.md`).
* **Metrics:** field-level precision/recall/F1 + alignment accuracy (separating
  "alignment wrong" from "field rule wrong") as in arXiv 2510.09722; per-field
  diagnostics for omission vs hallucination vs mismatch (as in
  `FAIRmat-NFDI/extract-eval`).
* **Harness:** `scripts/bench_resume.py` runs all tiers and writes a JSON
  report; CI compares to a baseline and fails on >1 pp regression; add
  `fail_under` to coverage config.
* **Human loop as metric:** confirmation rate and time-to-confirm are the real
  product KPIs — low confirmation = low trust even when the parse was correct.
* Honest note: **there is no public standard resume-extraction dataset** (the
  Alibaba paper had to build SynthResume 2,994 + RealResume 13,100). Our golden
  set is the moat; grow it from every opt-in user correction (structure +
  corrections only — never the raw resume, per skill 03).

## 9. User-facing suggestions (UX)

1. **Source-highlighted confirmation** — click a fact, highlight the exact line
   it came from (`provenance.span`). Biggest trust lever; possible precisely
   because we never store raw text (re-derive in-session).
2. **Coverage meter, not a bare list** — "12 of 18 fields found, 3 need your
   eyes"; turn ambiguities into a checklist wizard that asks only what is missing.
3. **Confidence with a basis** — tier + rule ("found under Skills",
   "LLM: gemini-2.0-flash", "OCR — please verify"), never a bare number;
   <0.6 hidden behind "needs your eyes".
4. **One-click paste fallback** on any failure, file retained for retry.
5. **Repair guidance on failure** — explain *why* (scanned → print-to-PDF;
   two-column → interleaved columns detected → try single-column export).
6. **Round-trip proof** — "see what an ATS would read" (P3 #17).
7. **Import diff** — when a changed resume is imported, show added/removed/
   rejected facts ("this skill was removed; still confirmed?").
8. **Never silently drop** — out-of-taxonomy skills surface as "unrecognized
   skill — add to your profile?" instead of vanishing.
9. **Privacy badge on the import screen** — "processed locally unless you
   enable AI", with a live indicator of which tier ran.
10. **Undo/reset per import** so re-importing never fears ledger pollution.

## 10. Constraints & risks

* **2 GB RAM / no mandatory API** rules out torch NER, big embedding models and
  cloud-only OCR. pdfplumber-or-pypdf-visitor + RapidFuzz + alias tables +
  optional ONNX OCR + optional tiny local LLM fits.
* **Licences:** PyMuPDF (AGPL) rejected in ADR-2. Clean: pdfplumber (MIT),
  pdfminer.six (BSD), pypdf (BSD), RapidOCR (Apache-2.0), reportlab (BSD),
  python-docx (MIT). ESCO data is CC-BY 4.0 → attribution required in
  `docs/ATTRIBUTIONS.md`. Tesseract is Apache-2.0 but a system dependency →
  optional extra.
* **No-fabrication is the hardest constraint and the best feature.** Grounding
  verification makes LLM extraction *provably* non-fabricating — build it,
  never weaken it.
* **Don't chase 95–98% marketing numbers** — report our own F1 from our own
  golden set, the way the spec demands.

## 11. References

**In-repo:** `MASTER_SPEC.md:40-49` (§3), `LOOPS.md:86-99` (LOOP-5 exit
criteria), `skills/03_resume_intelligence.md` (per-fact provenance, golden
files, "never store full documents"), `DATA_SOURCES.md:102-117`,
`IMPROVEMENT_AUDIT.md:15,24`, `PROGRESS.md:9`, `app/adapters/facts_from_resume.py`,
`app/services/resume_pipeline.py`, `app/domain/facts.py`, `.references/`
(read-only: AutoApply, jobsync eval fixtures), `No_Loop_Open_Source_Reference_Research/REFERENCE_RESEARCH.md`.

**External:**
1. Zhu et al., *Layout-Aware Parsing Meets Efficient LLMs* — arXiv:2510.09722 (2025). https://arxiv.org/abs/2510.09722
2. pdfmux, *PyMuPDF vs pdfplumber (2026)* — speed/licence/table-accuracy benchmarks. https://pdfmux.com/blog/pymupdf-vs-pdfplumber
3. pdfplumber docs (MIT). https://pypi.org/project/pdfplumber/
4. PyMuPDF-Layout vs Docling on DocLayNet. https://pymupdf.io/blog/pymupdf-layout-performance-on-doclaynet-a-comparative-evaluation
5. ESCoE Skills Extractor Library. https://www.escoe.ac.uk/the-skills-extractor-library
6. ESCO skills pillar (v1.2, ~13,500 concepts). https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia/skills-pillar
7. O*NET ↔ ESCO crosswalk (EC 2022). https://esco.ec.europa.eu/system/files/2022-12/ONET%20ESCO%20Technical%20Report.pdf
8. EDLIGO 2025 parsing analysis (via aiatschecker): plain DOCX ~4% vs PDF ~18% vs tables/multi-column 31%+ failure. https://aiatschecker.com/research/ats-resume-study-2026
9. ATSChecker 2026 study (n=2,417): 62% ≥1 formatting issue; two-column 38.1% / 31.2% failure. https://www.atschecker.ai/research/ats-resume-study-2026
10. ATSHiring — why ATS reject resumes. https://www.atshiring.com/en/learn/why-ats-systems-reject-resumes
11. LeverParser (open source accuracy claims). https://pypi.org/project/leverparser
12. FAIRmat `extract-eval` — per-field P/R/F1 for JSON extraction. https://github.com/FAIRmat-NFDI/extract-eval
13. Commercial bars (marketing): Affinda https://affinda.com/resume-parser · DaXtra · Parseur · Hirize
14. Tesseract (Apache-2.0) https://github.com/tesseract-ocr/tesseract · RapidOCR https://github.com/RapidAI/RapidOCR
