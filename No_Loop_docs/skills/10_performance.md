# Skill: Performance Engineer (10)

**Load for:** LOOP-10 (stage ends, pre-release), any hot-path change, ADR-1/ADR-2 benchmarks.
**Reads:** MASTER_SPEC §13, ARCHITECTURE.md stack rationale, AGENT_RULES R-TRUTH-1 (benchmarks), RESEARCH.md S5/S7.

## Role
Enforce the lightweight requirement. Measure startup, memory, parsing, matching, DB operations, network concurrency. Prefer caching, lazy imports, streaming and bounded queues. No heavyweight dependency without benchmark justification.

## Benchmark suite (owned by this skill; lives in tests/benchmarks/)
| Benchmark | What it measures | Target (MASTER_SPEC §13) |
|---|---|---|
| bench_db_lookup | indexed SQLite reads (jobs, applications) | sub-100 ms typical |
| bench_normalize_cached | cached job normalization | sub-100 ms typical |
| bench_match_1000 | full triangle on 1,000 jobs | sub-500 ms |
| bench_parse_pdf / _docx | corpus parsing throughput | recorded baseline; regressions flagged |
| bench_dedup_1000 | JobIdentity pipeline | recorded; within match budget |
| bench_ui_startup | shell start to ready | recorded; ADR-1 decides shell |
| bench_memory_baseline | RSS after typical flow on 2 GB profile | core usable on 2 GB |
| bench_fetch_concurrency | bounded async fetch throughput + fairness | no unbounded fan-out |

## Procedure
1. Record environment every run: CPU, RAM, OS, Python, versions, power plan (R-TRUTH-1: no invented numbers; real machine, real output).
2. Run suite before/after hot-path changes; ledger records both tables + delta.
3. Over budget → profile (cProfile/pyinstrument) → fix in order: SQL/index → cache → lazy import → algorithmic → streaming/bounded queue. Re-measure. Never "fix" by removing tests or turning off bounds.
4. Dependency proposals: require a benchmark delta (e.g. ADR-1 shell choice, ADR-2 PDF library) — numbers beat opinions.
5. Memory ceiling: run the 2 GB profile (capped VM/container) for the core flow (import → parse → match → draft); failures are release blockers.

## Design rules enforced
- Caches bounded (LRU/TTL) with visible sizes in Diagnostics.
- SQLite: WAL mode, prepared statements, indexes per query pattern; migrations tested for plan regressions.
- No full-resume re-sends to AI (fact slices only); no per-job AI in bulk loops.
- UI: render off the DB thread; no blocking calls on the UI loop; progress + cancel on all network/AI ops.

## Deliverables
Benchmark modules, recorded numbers in ledger + PROGRESS P014, regression verdicts, dependency benchmark memos for ADRs.
