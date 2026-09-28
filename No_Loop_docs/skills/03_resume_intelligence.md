# Skill: Resume Intelligence Engineer (03)

**Load for:** LOOP-5 (parser, fact ledger, onboarding engine).
**Reads:** MASTER_SPEC §3/§4, DATA_SOURCES.md §2/§6, RESEARCH.md S4/S9, AGENT_RULES R-POLICY-6.

## Role
Extract structured facts from PDF/DOCX/TXT into the fact ledger; generate dynamic onboarding questions from real gaps. Keep extraction separate from inference. Never invent candidate facts. Optimize for low memory and incremental parsing.

## Capabilities to build
1. **Text extraction:** PyMuPDF for PDF (pending ADR-2), python-docx for DOCX, plain read for TXT. Streaming/bounded memory; size caps (default 10 MB); file-type sniffing not extension trusting.
2. **Structure detection:** section heading recognition (standard headings first: Summary, Experience/Employment, Education, Skills, Projects, Certifications, Links), date parsing (ranges, present), contact/URL extraction (email/phone/LinkedIn/GitHub/portfolio), location fields.
3. **Fact ledger ingestion:** every extracted field → `ResumeFact` with provenance (document, page, span), confidence (0–1 with rule basis), state = `inferred`. Normalization to taxonomy surface forms (ESCO/O*NET-informed skill names; keep raw text too).
4. **Confirmation workflow:** inferred facts presented for confirm/reject/edit; only confirmed facts enter the Canonical Profile; rejections recorded (never re-inferred from the same doc).
5. **Ambiguity/gap report:** missing standard sections, conflicting dates, unverified technologies → drives onboarding questions (MASTER_SPEC §4); questions concise, editable, skippable.
6. **Derived resume rendering:** single-column, standard headings, standard fonts, no tables/graphics (DATA_SOURCES.md §6); golden-file tests assert structure.

## Test discipline
- Synthetic corpus only in repo (no real personal data); provenance recorded in RESEARCH.md.
- Golden files: input → expected facts; parser changes re-run all goldens.
- Invariant tests: an inferred fact can never render in the UI as fact; generator cannot consume unconfirmed facts (paired with skill 06 guard tests).

## Guardrails
Never auto-confirm. Never infer dates/experience claims beyond evidence. Never store full documents in DB — store extracted facts + file hash reference; documents live in user data dir.

## Deliverables
Extractor modules, fact-ledger service, confirmation UI service hooks, question engine, golden tests, ledger entry with sample outputs (synthetic).
