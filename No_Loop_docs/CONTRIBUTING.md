# Contributing

1. Read in order: ENVIRONMENT.md → README.md → AGENT_RULES.md → LOOPS.md → MASTER_SPEC.md → ARCHITECTURE.md.
2. Set up the dev environment strictly per ENVIRONMENT.md (project on `D:`, `.venv` inside the project, caches redirected to `D:\DevCache`, nothing installed on `C:`, no duplicate packages).
3. Create a focused branch per task; run the loop for that task type (LOOPS.md selection table).
4. Add tests for behavior changes; include failure paths and no-AI-mode coverage where relevant.
5. Do not introduce paid services as mandatory dependencies; do not add capability-duplicate packages.
6. Keep adapters isolated; vendor names never enter the domain layer.
7. Do not add automation against websites that prohibit it; check DATA_SOURCES.md §9 first.
8. Update PROGRESS.md + DEVELOPMENT_LEDGER.md with evidence; list exact files changed.
9. Run lint, tests, and (for release PRs) packaging checks; record benchmark deltas for hot paths.
10. Explain security/privacy implications in the PR (SECURITY.md checklist if applicable).

AI contributors: CURSOR_MASTER_PROMPT.md is your entry point; AGENT_RULES.md is binding on you exactly as on humans.
