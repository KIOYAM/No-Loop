# Skill: Python Backend Engineer (02)

**Load for:** LOOP-2, LOOP-4 implementation steps, any service/adapter code.
**Reads:** ARCHITECTURE.md, AGENT_RULES.md §C/§E, skill 01 for boundaries.

## Role
Implement typed, testable Python services that honor the architecture and environment contracts.

## Standards
1. Python 3.12+, full type annotations; `mypy` clean is a merge condition.
2. Prefer the standard library when sufficient; Pydantic for validation and domain models; no ad-hoc dicts crossing boundaries.
3. Async I/O for network operations with **bounded concurrency** (semaphores; default caps in settings, e.g. 4 concurrent fetches).
4. No global mutable state. Configuration injected; time/random injectable for tests.
5. Every external call: timeout + size cap + typed exception mapping to domain errors (stage, reason, retryable, user_action).
6. Logging via the project logger; never log secrets or personal data (R-SEC-1); structured diagnostic IDs for failures.
7. Deterministic functions pure where possible; side effects live at adapter/service edges.
8. SQL via SQLAlchemy Core with indexes per query pattern; all schema changes through migrations (R-ARCH-7).

## Procedure (inside LOOP-2/4)
1. Restate acceptance criteria; cite the MASTER_SPEC section.
2. Write failing tests first for the behavior (table-driven; boundaries; invariants).
3. Implement the smallest change; run tests; run `ruff` + `mypy`.
4. Wire into the layer above; add contract tests if an adapter changed.
5. Update ledgers + PROGRESS with evidence.

## Guardrails
- Do not install packages globally or outside `.venv` (R-ENV-2/3/4). Verify interpreter path first.
- Do not vendor code without ADR + license check.
- Do not add a dependency before checking the lock file for an existing capability.
- Do not catch broad exceptions to "make it pass"; map failures per MASTER_SPEC §17.

## Deliverables
Typed modules, passing tests with names listed in the ledger, lock delta (or "none"), updated docs if behavior changed.
