# No_Loop Architecture

## Recommended stack

### Core
- Python 3.12+ (current stable validated by CI)
- Pydantic — typed domain models (purpose: validation + serialization; no ad-hoc dicts)
- SQLite — embedded persistence, auto-created, auto-migrated
- SQLAlchemy Core (SQLModel only if ADR-3 chooses it) — persistence abstraction, lean usage
- httpx — async HTTP with timeouts (sole HTTP client; no requests/aiohttp — R-ENV-3)
- selectolax — lightweight HTML parsing (sole parser; do NOT also install BeautifulSoup/lxml)
- PyMuPDF — PDF extraction (ADR-2 required: AGPL library decision) ; python-docx — DOCX
- rapidfuzz — fast deterministic text similarity
- click or argparse — CLI entry for dev/build scripts (argparse preferred: zero deps)
- pytest, ruff, mypy — quality toolchain
- Full dependency register with purposes lives in `pyproject.toml` comments + ARCHITECTURE §Dependencies below; single source of truth (R-ENV-3). No parallel requirements files.

### Desktop shell
Lightweight shell; evaluate in this order:
1. **PySide6** — mature native UI; larger footprint; must pass LOOP-11 footprint budget.
2. **PyWebView** — Python-centric, uses the OS webview; subject to platform webview availability.
3. **Tauri** — very light runtime but adds Rust/JS tooling to a Python-first project.
Electron is forbidden. Decision via ADR-1 after LOOP-11 benchmarks (RESEARCH.md §4).

### Browser automation
Playwright as an optional adapter-only dependency; browsers launch on demand and only for adapters that need them; never resident (R-ARCH-5). Browser binaries to `D:\DevCache\ms-playwright` in development (R-ENV-2). No browser code outside the adapter layer. **v0.1 scope: fill-only** — the adapter fills permitted forms (Greenhouse-hosted) and the user clicks Submit; auto-submit is v0.2.

### Packaging
**v0.1 ships a portable .zip from GitHub Releases — no installer** (user decision, NOLOOP_DEV_KICKOFF-spec §3 Round 3): PyInstaller onedir → zipped artifact + README with "run from any folder" instructions; data location chosen by the user at first run (per-user folder or portable toggle). Inno Setup installer + optional MSIX arrive in v0.2. Targets: Windows 10/11 x64 only in v0.1; Linux/macOS follow-up. No end-user Python/DB setup. C-drive rules during development per ENVIRONMENT.md §1; end-user install follows ENVIRONMENT.md §5.

### Optional local AI
Provider adapter for Ollama/llama.cpp-compatible runtimes. **v0.2** — v0.1 ships Tier 0 NoAI + Tier 1 RuleBased + Tier 2 Gemini BYOK (first cloud provider, user decision). Never required, never installed by No_Loop, never on 2 GB systems (auto-disable below 8 GB total RAM — RESEARCH.md S7). Rule-based path remains fully functional without any of it.

### Internationalization (NEW — v0.1 requirement)
UI languages: **English + Tamil + Hindi** shipping together (user decision). Architecture:
- Zero hard-coded user-facing strings; all strings externalized from the first line of UI code via string IDs + catalogs.
- If ADR-1 picks PySide6: Qt Linguist (.ts/.qm) workflow. If PyWebView/web-based shell: gettext-style JSON catalogs.
- English copy is finalized first (copy freeze), then translated; translation completeness (EN 100%, TA 100%, HI 100%) is a v0.1 release gate tracked in PROGRESS.md.
- Language switch lives in Settings; language does not affect parsing logic (parser is English-tolerant for mixed-script resumes).

## Layering (dependency direction — R-ARCH-1)

```
UI
 → Application Services
   → Domain (entities, invariants, pure logic)
     → Ports/Interfaces
       → Adapters
          - SQLite repository
          - HTTP client
          - Job source adapters
          - ATS/application adapters
          - Email providers
          - AI providers
          - Browser automation
       → Infrastructure (config, logging, keychain, migrations)
```

The domain layer imports nothing from adapters, UI, or vendor SDKs. Vendor/portal names never appear in domain or application-service code (R-ARCH-3) — only in adapters and their configuration.

## Component map (build order mapping)

| Component | Layer | Purpose | Loops |
|---|---|---|---|
| Candidate profiles (named, multi) | domain+app | profile_id scoping across all entities | LOOP-2 |
| Domain models (15+ entities) | domain | invariants, validation | LOOP-2 |
| Fact Ledger + profile service | domain+app | S4 dual-confidence facts | LOOP-5 |
| Resume extraction | adapters+app | PDF/DOCX/TXT → facts; scanned-PDF error path | LOOP-5 |
| Onboarding question engine | app | gap-driven questions + mandatory limits setup | LOOP-5 |
| Targeting engine | app | preferences → search plans (India-first presets) | LOOP-4 |
| JobIdentity/dedup | domain | S8 5-key dedup | LOOP-6 |
| Source adapters ×N | adapters | discovery per DATA_SOURCES | LOOP-3 |
| MatchEngine | domain+app | Match Triangle | LOOP-6 |
| Content generator | app | S2 truth-preserving artifacts | LOOP-7 |
| Document renderers | adapters | tailored resume DOCX + PDF (ADR-7) | LOOP-7 |
| Email providers | adapters | draft/mail-handoff (v0.1), SMTP (v0.2) | LOOP-7 |
| ApplicationAdapter(s) | adapters | fill-only automation (v0.1) | LOOP-8 |
| Quick-Add manual entry | app+ui | all-applications ledger | LOOP-4 |
| i18n service | infra | EN/TA/HI catalogs | LOOP-1/4 |
| AI provider registry | app | Tier 0/1/2 (Gemini first) | LOOP-3/4 |
| Security services | infra | keychain, SSRF guard, redaction | LOOP-9 |
| Migrations | infra | numbered, reversible | LOOP-1/2 |
| UI shell + screens | ui | MASTER_SPEC §16 | LOOP-4 |
| Packaging | packaging | onedir + portable zip | LOOP-11 |

## Repository

```
No_Loop/
  app/
    domain/          # entities, value objects, invariants, pure services
    application/     # use-case services orchestrating domain + ports
    infrastructure/  # config, logging, migrations, keychain, settings, i18n
    adapters/
      sources/       # job source adapters (one module per source)
      applications/  # ATS/application adapters (fill-only in v0.1)
      email/         # email providers
      ai/            # AI providers (NoAI, RuleBased, Gemini BYOK)
      documents/     # DOCX/PDF renderers for derived artifacts
      browser/       # browser automation (optional, on-demand)
    ui/              # desktop shell + screens + i18n catalogs
    services/        # cross-cutting application services
  tests/
    unit/ contract/ integration/ benchmarks/ fixtures/
  scripts/           # devenv, build, benchmark, policy-check helpers
  docs/              # user + developer docs (incl. ATTRIBUTIONS.md)
  skills/            # role cards (mirrored from No_Loop_docs for agents)
  data/              # bundled taxonomy subsets, sample data (no personal data)
  migrations/        # numbered reversible DB migrations
  packaging/         # portable-zip build scripts, icons, version files
  .references/       # GITIGNORED: read-only clones of the 8 reference repos (R-ENV-6)
  .github/           # CI workflows
  pyproject.toml     # single dependency source of truth (+ lock file)
  README.md LICENSE SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md
```

## Dependency register (living; mirrored in pyproject.toml comments)

| Package | Purpose | License | Justification vs 2 GB baseline |
|---|---|---|---|
| pydantic | domain validation | MIT | core, small |
| sqlalchemy | persistence | MIT | core, import-lazy |
| httpx | HTTP | BSD-3 | sole HTTP client |
| selectolax | HTML parse | MIT | fast/low-mem, sole parser |
| pymupdf (pending ADR-2) | PDF text | AGPL — ADR required | core capability |
| python-docx | DOCX text | MIT | core capability |
| reportlab (pending ADR-7) | PDF **writing** (tailored resume PDF) | BSD — preferred over weasyprint (heavier); benchmark decides | DOCX+PDF output requirement |
| rapidfuzz | fuzzy match | MIT | core capability |
| playwright (optional extra) | browser automation | Apache-2.0 | adapter-only, on demand |
| pyside6 (pending ADR-1) | UI shell | LGPL-3.0 — ADR required | footprint benchmark decides |
| keyring | OS credential store | MIT | security requirement |

Rule: no package enters without this row + lock update + ledger note (R-ARCH-4). Capability duplicates (2nd HTTP client, 2nd HTML parser, 2nd PDF lib) are forbidden without an ADR explicitly retiring the old one.

## Data flow (happy path)

```
resume file → extractor → facts(inferred) → user confirm → Canonical Profile
targeting prefs → search plan → source adapters → jobs(raw) → normalizer → Job
Job → JobIdentity/dedup → unique jobs → MatchEngine → MatchResult(+explanation)
MatchResult ≥ threshold → ApplicationQueue → generator → artifacts(+evidence map)
review+consent → [automated adapter | assisted flow] → AutomationRun/confirmation
→ Application Ledger update → tracker/export
```

Every arrow writes audit records; every external arrow passes policy + security gates.
