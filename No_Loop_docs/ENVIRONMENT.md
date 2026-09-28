# ENVIRONMENT.md — Machine & Environment Contract (MANDATORY)

**Read this file FIRST, before any other project file.** This document defines where the project lives, where it must never touch, and how the development machine must be kept clean. Violating any rule in this file is a build-blocking defect, regardless of code quality.

Project root: `D:\Kannan-Projects\NoLoop\`
Docs root: `D:\Kannan-Projects\NoLoop\No_Loop_docs\`
Research pack: `D:\Kannan-Projects\NoLoop\No_Loop_Open_Source_Reference_Research\`

---

## 1. The C-Drive Forbiddance (HARD RULE)

The user's operating system is installed on `C:`. The project and all of its tooling live on `D:`. **Nothing from this project may be installed, written, cached, or spawned on `C:`.**

### 1.1 Absolute prohibitions

| Forbidden | Why | Do instead |
|---|---|---|
| Installing Python, Node, JDK, Git, or any toolchain on `C:` (e.g. `C:\Python312`, `C:\Program Files\...`) | Pollutes the OS drive; user forbids C-drive installations | All toolchains pre-installed or installed under `D:\Tools\` only |
| Creating virtual environments on `C:` | Violates the same rule | Always `.venv` inside the project: `D:\Kannan-Projects\NoLoop\.venv` |
| `pip install` into the global/`C:` interpreter | Contaminates system Python, causes package duplication | Only ever `pip install` inside the project `.venv` (or `uv venv` on `D:`) |
| `npm install -g` / global node_modules on `C:` | Same | Local `node_modules` inside the project only, or `D:\Tools\` |
| Cache directories on `C:` (`C:\Users\...\AppData\Local\pip`, `uv`, `Playwright`, `ms-playwright`, `huggingface`, `torch`, `ollama`) | GBs of hidden growth on OS drive | Redirect every cache to `D:\DevCache\` via env vars (see §2) |
| Playwright browser downloads to default `C:` location | Playwright defaults to `C:\Users\<user>\AppData\Local\ms-playwright` | Set `PLAYWRIGHT_BROWSERS_PATH=D:\DevCache\ms-playwright` **before** `playwright install` |
| Ollama / model downloads to `C:` default locations | Model files are multi-GB | Ollama is an end-user optional component; never installed by this project. If a developer tests local AI, set `OLLAMA_MODELS=D:\DevCache\ollama-models` |
| Hugging Face model caches on `C:` | Same | `HF_HOME=D:\DevCache\huggingface` |
| Temp/build artifacts on `C:` | Hidden duplication | All `build/`, `dist/`, `__pycache__` stay inside the project on `D:` |
| Copying packages between environments "to fix" an import error | Duplicate packages = version drift = unexplainable bugs | Fix the environment, never clone it |

### 1.2 The No-Duplication Rule (packages)

- One dependency source of truth: `pyproject.toml` (PEP 621) + a lock file. No parallel `requirements*.txt` files with divergent pins. If a requirements export is needed for CI, it is *generated* from the lock and committed as generated output with a header saying so.
- Every dependency must be declared exactly once, with its purpose documented (see ARCHITECTURE.md §Dependencies).
- Installing a package that bundles another (e.g. two packages that each vendor a PDF parser) requires a ledger note explaining why the duplication is acceptable; otherwise pick one.
- Before adding a dependency, search the lock file for an existing package that already provides the capability. Duplicating capability across packages (two HTTP clients, two HTML parsers, two PDF libs) is forbidden without a written ADR.
- Never "fix" a missing module by copying files into site-packages or vendoring random repos into `app/`. Vendoring requires an ADR + license check (see the research pack's `references/LICENSE_NOTES.md`).

### 1.3 Portable toolchain layout (D: drive)

```
D:\Tools\                    # optional developer tooling, if not already installed
D:\DevCache\                 # ALL caches redirected here (never C:)
  pip\  uv\  ms-playwright\  ollama-models\  huggingface\  nuitka-cl cache\
D:\Kannan-Projects\NoLoop\   # the project
  .venv\                     # THE only virtualenv for this project
  .references\               # GITIGNORED: read-only clones of the 8 reference repos (R-ENV-6)
```

### 1.4 Reference library (`.references/`)
- Location: `D:\Kannan-Projects\NoLoop\.references\` — inside the project, **gitignored, never committed, never shipped**.
- Contents: read-only clones of the 8 audited reference repos + `PROVENANCE.md` (clone date, commit hash, LICENSE content, reuse verdict per repo — NOLOOP_DEV_KICKOFF-spec §5.1).
- Rule (R-ENV-6): study-only. Code may leave `.references/` only through the two gates (R-TRUTH-6 license gate + LOOP-9 security review) with in-code attribution and a ledger record. The AGPL repo (ScottCoffin/Job_Scraper) is ideas-only, always.

---

## 2. Required environment variables (development shell)

Set these in every shell that runs project commands (put them in a `scripts/devenv.ps1` / `scripts/devenv.sh` helper; the AI agent must run these before `pip`, `playwright`, or test commands):

```bash
export NOLOOP_DEV=1
export PLAYWRIGHT_BROWSERS_PATH="D:/DevCache/ms-playwright"
export PIP_CACHE_DIR="D:/DevCache/pip"
export UV_CACHE_DIR="D:/DevCache/uv"
export HF_HOME="D:/DevCache/huggingface"
export OLLAMA_MODELS="D:/DevCache/ollama-models"   # only if testing local AI
export PYTHONDONTWRITEBYTECODE=0                   # pycache stays inside project anyway
export NOLOOP_DATA_DIR="D:/Kannan-Projects/NoLoop/.local-data"  # app data during dev
```

The application, when run as a packaged product, must honor `NOLOOP_DATA_DIR` (or OS-appropriate per-user app-data dirs) and must never write to its own install directory.

---

## 3. Project directory contract

```
D:\Kannan-Projects\NoLoop\
  No_Loop_docs\                          # this documentation pack (canonical rules)
    skills\                              # 16 role cards the AI must load by task
    README.md AGENT_RULES.md CURSOR_MASTER_PROMPT.md LOOPS.md
    MASTER_SPEC.md ARCHITECTURE.md DEVELOPMENT.md
    DATA_SOURCES.md RESEARCH.md NOLOOP_DEV_KICKOFF-spec.md
    PROGRESS.md DEVELOPMENT_LEDGER.md APPLICATION_LEDGER.md
    SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md LICENSE
  No_Loop_Open_Source_Reference_Research\  # external reference research (read-only input)
  app\  tests\  scripts\  migrations\  packaging\  docs\  data\  .github\   # created by build order in DEVELOPMENT.md
  .references\                           # gitignored reference clones (see §1.4)
  .venv\                                 # project virtualenv (D: only)
  pyproject.toml + lock file             # single dependency source of truth
```

`.gitignore` must include `.references/` from LOOP-1 onward (verified in the LOOP-1 exit criteria).

---

## 4. Command hygiene for AI agents

- Run all commands with the project root as cwd, using the project `.venv` (`.venv/Scripts/python.exe` on Windows).
- Never use `sudo`/admin elevation for project work.
- Never delete or modify anything outside `D:\Kannan-Projects\NoLoop` and `D:\DevCache`.
- Never move, rename, or "clean up" `No_Loop_docs/` or the research pack without explicit human instruction — they are the canonical rule books.
- Network access during development is allowed for: dependency installation from the lock file, Playwright browser download (to `D:`), fetching public job data through adapters in tests marked as network tests, and research. Everything else offline-first.
- Before declaring any task done, verify: no files created on `C:` (check tool output for `C:\` paths), no packages installed outside `.venv`, lock file updated for any new dependency.

### 4.1 Verification snippet (run after dependency or cache-heavy tasks)

```bash
# 1) Assert the active python is the project venv on D:
python -c "import sys; assert sys.executable.lower().startswith('d:/kannan-projects/noloop/.venv'), sys.executable; print('venv OK:', sys.executable)"

# 2) Assert pip cache is on D:
pip config list | grep -i cache || true

# 3) List any accidental C: writes from this session (manual review)
#    Look for C:\ paths in tool output; if found, delete them and redo the step with correct env vars.
```

---

## 5. End-user installation contract (why this rule exists)

The product itself must, after installation:
- Keep its executable + resources in its install directory (typically `C:\Program Files\No_Loop` **chosen by the human user**, or a per-user location) — that is the user's choice at install time, not a development activity.
- Keep all *user data* (SQLite DB, resume files, ledger, settings) in the OS per-user app-data directory or `NOLOOP_DATA_DIR`. Never in `Program Files`, never in the repo, never scattered.
- Keep caches small and bounded; document every cache location in Settings → Diagnostics so a user can see and clear them.
- The C-drive forbiddance in §1 applies to **project development**. The end-user installer may follow standard OS conventions at the user's discretion; the installer must never silently write outside the chosen install dir + per-user app data.

---

## 6. Related rules

- AGENT_RULES.md — R-ENV rules (Section A) reference this file; all other sections cite it.
- LOOPS.md — every loop begins with "verify environment per ENVIRONMENT.md".
- DEVELOPMENT.md — build order assumes the §2 env vars are set.
- ARCHITECTURE.md — dependency-addition procedure (no duplication rule lives there too).
