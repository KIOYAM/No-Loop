# CODING_STANDARDS.md — Canonical Coding Standards for No_Loop

**Authority:** binding for all AI agents and human contributors, same rank as AGENT_RULES.md. AGENT_RULES says *how to work*; this file says *how the code itself must look and behave*. Referenced by LOOPS.md exit criteria (lint/types/tests gates) and enforced by CI.

Applies to: `app/`, `tests/`, `scripts/`, `migrations/`, `packaging/`. Does not apply to `.references/` (read-only, never ours) or generated files (marked as such).

Tooling versions are pinned in `pyproject.toml` — this document defines the *policy*, the config files define the *settings*.

---

## 1. Language & toolchain policy

| Concern | Standard | Enforcement |
|---|---|---|
| Python version | 3.12+ (per pyproject `requires-python`) | CI matrix |
| Formatting | ruff format (black-compatible), line length 100 | `ruff format --check` |
| Linting | ruff with rules: E,F,W,I,N,UP,B,SIM,C4,DTZ,T20,PTH,S | `ruff check .` (zero warnings policy) |
| Type checking | mypy, `strict = true` for `app/domain/`, default for rest | `mypy app tests` |
| Testing | pytest + pytest-asyncio; coverage gate: domain ≥90%, application ≥80%, adapters ≥70% (recorded, per skill 12) | `pytest --cov` |
| Imports | absolute imports only (`from app.domain...`); no relative-import gymnastics | ruff I rules |
| Commits | conventional commits: `feat|fix|refactor|test|docs|chore(scope): message` | review |

Forbidden tool invocations: `pip install` outside `.venv` (R-ENV-2/4); any toolchain write to `C:` (R-ENV-2).

## 2. Project layout rules

Exactly as ARCHITECTURE.md §Repository. Layout laws:
1. **One module, one responsibility.** A module >400 lines is a refactor candidate; >800 lines requires a ledger justification.
2. **File naming:** `snake_case.py`; classes `PascalCase`; functions/variables `snake_case`; constants `UPPER_SNAKE`.
3. **`__init__.py` exports:** explicit `__all__`; no side effects at import time (no DB connections, no config reads at import).
4. **Domain purity:** `app/domain/` imports only stdlib + pydantic. Never httpx, sqlalchemy, playwright, or any vendor module (R-ARCH-1/3; CI grep gate).
5. **Vendor-name gate:** no portal/AI-vendor names (linkedin, naukri, gemini, ollama, greenhouse…) in `app/domain/` or `app/application/` — adapters only (R-ARCH-3; CI grep gate).

## 3. Typing standards

1. Every function signature fully annotated: parameters, return type (including `-> None`).
2. Public domain/service APIs use Pydantic models or typed dataclasses — never bare dicts across boundaries (skill 02).
3. `dict[str, X]` / modern generics syntax (`list[str]`, not `List[str]`).
4. `Optional[X]` → `X | None`. Avoid `Any`: if unavoidable, isolate it behind a typed façade with a comment justifying it.
5. Typed exceptions: every custom exception subclasses a domain base and carries structured context (see §7).
6. No silent `# type: ignore` — each one needs a same-line reason comment; >5 in a file is a defect.

## 4. Error handling standards (MASTER_SPEC §17 is the law)

1. **Never silently fail, never silently swallow.** Bare `except:` is forbidden; `except Exception` only at adapter/service boundaries with re-raise or structured handling.
2. **Error taxonomy:** every failure raised across a boundary is a domain error with:
   - `stage` (pipeline stage identifier, e.g. `discovery.fetch`, `parse.pdf`, `match.score`)
   - `reason` (human-readable)
   - `retryable: bool`
   - `user_action` (what the user can do, or None)
   - `diagnostic_id` (UUID for log correlation)
3. **Adapter error mapping:** external exceptions never leak past an adapter — map to domain errors at the edge (skill 04 step 8).
4. **Retries:** only for idempotent operations; exponential backoff + jitter; max 3 by default; retry policy is configuration, not hard-coded.
5. **Logging:** structured logging via the project logger; log stage + diagnostic_id + sanitized context; NEVER log secrets/personal data/full resume text (R-SEC-1); `log_debug` redaction filter is mandatory for anything user-derived.
6. **Fail fast in dev, degrade gracefully in product:** configuration errors crash at startup; runtime external failures degrade with UI feedback per MASTER_SPEC §17.

## 5. Async & concurrency standards

1. `async def` for all network I/O (httpx); sync for pure computation.
2. **Bounded concurrency everywhere:** every fetcher/worker uses a semaphore or bounded queue (default 4, configurable) — unbounded `asyncio.gather` is forbidden.
3. Timeouts on every external call (connect + read; defaults in settings, never `None`).
4. No blocking calls in async contexts (`time.sleep` → `asyncio.sleep`; sync file/DB I/O kept off the event loop or in executors).
5. Injectable clocks/sleeps for tests (`fake_clock` fixtures), no real sleeps in tests (skill 12 guardrail).
6. Cancellation-safe: every long-running coroutine checks cancellation between steps; automation loops check the stop flag before every network/submit-adjacent step (R-SEC-4).

## 6. Data & persistence standards

1. **Single source of schema truth:** Pydantic domain models; SQLAlchemy Core table definitions mirror them; migrations generated/reviewed against both (R-ARCH-7).
2. **Migrations:** numbered, reversible (`upgrade()` + `downgrade()`), never edited after release; every migration has a round-trip test.
3. **Indexes:** every query pattern in services must have a matching index (verified in code review + `EXPLAIN QUERY PLAN` tests for hot paths).
4. **WAL mode** for SQLite; foreign keys ON; no cross-profile queries (invariant 7, APPLICATION_LEDGER.md) — enforced by repository-layer filters, tested.
5. **No ORM lazy-loading surprises:** explicit selects; no N+1 patterns in list views (use `selectinload`-style batching or explicit joins).
6. **Personal data minimization:** store facts + hashes + references, not whole documents, in the DB (skill 03 guardrail); documents live in the user data dir.
7. **profile_id discipline:** every profile-scoped table carries `profile_id` with FK + composite indexes `(profile_id, ...)` per query pattern.

## 7. Security coding standards (SECURITY.md operationalized)

1. **Secrets:** only via the keyring-backed CredentialReference port; never in code, config files, DB rows, logs, or error messages. String literals resembling keys in tests are obviously-fake fixtures only.
2. **URL fetching (SSRF guard, mandatory helper):** scheme allowlist (http/https), DNS resolve + block private/loopback/link-local/metadata ranges, ≤3 redirects re-validated per hop, response size cap (default 5 MB), timeout cap. User-supplied URLs always go through this helper — no raw `httpx.get` on user input, ever.
3. **HTML handling:** fetched HTML is parsed with selectolax → plain text/sanitized fragment before storage; raw HTML never re-rendered in the UI.
4. **File imports:** magic-byte sniffing (not extension), size cap (default 10 MB), parse in bounded memory, originals stored only in user data dir with hash reference.
5. **Path safety:** filenames for artifacts generated (slug + UUID); user input never concatenated into paths; all writes confined to user data dir + temp.
6. **Subprocess/exec ban:** no `eval`, `exec`, `pickle.loads` on external data, no dynamic imports from user input, no subprocess from adapters (browser adapters use Playwright's API, not shell).
7. **Consent points:** every code path that sends data off-device calls the consent service first and records a ConsentEnvelope — enforced by review checklist + integration tests (R-SEC-3).

## 8. Testing standards

1. **Structure:** `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/benchmarks/`, `tests/fixtures/` (ARCHITECTURE layout).
2. **Naming:** `test_<unit>_<scenario>_<expected>()` e.g. `test_matchengine_location_mismatch_excludes_with_reason`.
3. **One behavior per test**; table-driven with `pytest.mark.parametrize` for input families; AAA pattern (Arrange-Act-Assert).
4. **Fixtures:** synthetic only — no real personal data ever committed (CODE_OF_CONDUCT §2); fixtures carry a provenance comment (synthetic or source).
5. **Contract tests:** every adapter has recorded/redacted fixtures covering: happy path, empty, partial fields, malformed, error responses, pagination end (skill 04).
6. **No-AI-mode suite:** every user-facing flow has a test running with NoAIProvider/RuleBasedProvider only (hard gate).
7. **Network tests:** marked `@pytest.mark.network`, skipped by default (CI and local), rate-limited when enabled.
8. **No real sends:** email/automation tests run dry-run or against fakes — a test that could reach a real portal/SMTP server is a defect.
9. **Benchmarks:** every benchmark prints machine specs (CPU, RAM, OS, versions) with results (R-TRUTH-1); numbers go to the ledger, never invented.
10. **Flaky = bug:** a flaky test is quarantined immediately with a LOOP-14 task, not tolerated.

## 9. Documentation standards

1. Every public module has a docstring: purpose, boundaries, and the MASTER_SPEC section it serves.
2. Every adapter module docstring includes its POLICY_STATUS + source URL + review date.
3. Every non-obvious decision gets a short comment citing the rule/spec it implements (e.g. `# fill-only per MASTER_SPEC §11 (v0.1)`).
4. `docs/ATTRIBUTIONS.md` is append-only; entries follow its header template.
5. Doc changes ride with the code change in the same PR (LOOP-15).
6. User-facing strings never live in code — string IDs + catalogs (i18n standard, NOLOOP_DEV_KICKOFF-spec §8.4); hard-coded UI strings fail review.

## 10. Dependency standards (R-ENV-3/R-ARCH-4 operationalized)

1. New dependency requires ALL of: no existing-package capability overlap (checked against ARCHITECTURE dependency register), license compatible with Apache-2.0, purpose row added to the register, lock file updated in the same PR, ledger note.
2. Capability-duplicate packages forbidden (second HTTP client, second HTML parser, second PDF lib) — retirement ADR required first.
3. No transitive-dependency surprises: after adding, run `pip list` diff; unexplained new top-level packages are investigated before merge.
4. Prefer stdlib: if the stdlib covers it (dataclasses, hashlib, sqlite3…), justify why not.
5. Optional extras (playwright) stay optional: core imports must not fail without them; extras guarded behind lazy imports in adapters only.

## 11. Reference-code adoption workflow (R-ENV-6/R-TRUTH-6 operationalized)

When adapting anything studied from `.references/` or the live web:
1. Confirm the source's verdict in `.references/PROVENANCE.md` — AGPL/unknown → stop, ideas-only.
2. Re-type/adapt into our style; never paste files wholesale; keep snippets minimal (a pattern, not a module).
3. Add attribution line: `# Adapted from <repo>@<commit> (<license>) — <what changed>`.
4. Append an entry to `docs/ATTRIBUTIONS.md` (template in that file).
5. Run the LOOP-9 security checklist items 2/4/5/11 on the diff.
6. Record the adoption in the session ledger entry (source, license, changes, tests).

## 12. Git & CI standards

1. Branch names: `feat/<slug>`, `fix/<slug>`, `adr/<n>-<slug>`, `docs/<slug>`.
2. CI (GitHub Actions) gates on every PR: ruff format check, ruff check, mypy, pytest (no network marks), coverage gate, domain-purity grep, vendor-name grep, `.gitignore` integrity (`.references/` still ignored), license-header check on new files carrying attributions.
3. Commits reference the loop: e.g. `feat(matching): hard-gate filters [LOOP-6]`.
4. No force-push to shared branches; no commits directly to main after bootstrap.
5. PR template requires: tests run, ledgers updated, files changed list, security checklist (when applicable) — mirroring CONTRIBUTING.md.

## 13. Definition of clean (the bar for "done" on any code task)

```
[ ] ruff format --check .            → clean
[ ] ruff check .                     → zero warnings
[ ] mypy app tests                   → zero errors (strict in domain)
[ ] pytest                           → all green, no skipped-without-reason
[ ] new behavior has named tests     → listed in ledger
[ ] failure paths tested             → §17 fields present
[ ] no-AI mode proven (if user-facing)
[ ] profile isolation proven (if profile-scoped)
[ ] docs/ledgers updated             → LOOP-15 done
[ ] environment audit                → no C: writes, no dup packages, lock updated if deps changed
```
