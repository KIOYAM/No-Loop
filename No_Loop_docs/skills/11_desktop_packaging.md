# Skill: Desktop Release Engineer (11)

**Load for:** LOOP-11 (packaging), ADR-1 shell benchmark, release artifact builds.
**Reads:** ARCHITECTURE.md packaging, ENVIRONMENT.md §1/§5, MASTER_SPEC §2/§16, DATA_SOURCES.md §5.

## Role
Package a no-terminal installation. Evaluate PyInstaller/Nuitka and the chosen desktop shell. Automate dependency/runtime setup. Test clean-machine installation. Keep installer footprint reasonable.

## Pipeline
1. **Shell decision (feeds ADR-1):** build the same smoke UI on PySide6 and PyWebView; measure installer size, installed size, startup, RSS (with skill 10). Pick the one within the footprint budget with acceptable UX; record numbers in the ADR.
2. **Bundle:** PyInstaller **onedir** (not onefile — slower startup + AV friction) with version file, icon, exclusion of test/dev modules; verify no telemetry; Nuitka only if onedir fails budget.
3. **Installer:** Inno Setup (open-source, JRsoftware) — per-user or per-machine choice, install dir respected, app-data location per ENVIRONMENT §5, uninstall leaves only documented app-data. MSIX as a later optional target (store signing).
4. **First-run:** DB auto-create + auto-migrate; onboarding wizard (MASTER_SPEC §16); no terminal output required anywhere; crash handler writes a redacted diagnostic file.
5. **Clean-VM test (mandatory):** Windows VM snapshot → install → first-run wizard → import sample resume → discovery dry-run (no network sources configured → URL import path) → generate draft → uninstall → verify leftover inventory matches documentation.
6. **Environment compliance:** build machine follows ENVIRONMENT.md (no C: caches; build artifacts under `D:\Kannan-Projects\NoLoop\packaging\build`). The *product* may follow OS conventions on the user's machine (their choice), but must never write outside install dir + per-user app data.

## Footprint budget (record, don't guess)
Installer ≤ 150 MB and installed ≤ 400 MB for core (no browsers, no models) as the working budget; adjust only with benchmark evidence in the ADR. Playwright browsers and any model runtimes are user-side optional components, never bundled (R-ARCH-5).

## Test discipline
- Installer build reproducible from CI script (`scripts/build_windows.(ps1|sh)`).
- Version stamping: single source (pyproject) → installer metadata → About screen.
- Smoke suite run against the installed build (not the dev tree).

## Deliverables
Build scripts, installer config, clean-VM checklist results, footprint numbers, signed-off artifact path in the ledger + PROGRESS P012.
