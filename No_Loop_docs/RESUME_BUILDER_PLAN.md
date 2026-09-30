# Resume Builder — visual, editable, AI-assisted (plan 2026-09-30)

**Ask:** use GrapesJS + its newsletter preset, heavily customized, so the user's
resume is built visually with the *exact structure* the rest of the app already
uses, fully editable, with the AI selected in Settings proposing pinpoint
updates and adjustments — per position, per company the user applied to.
Explicitly **not automation**.

**Decisions locked with the user (2026-09-30):**

1. Write this plan, then build the first working slice in the same session.
2. AI is **propose-only**: it returns pinpoint suggestions; nothing changes
   until the human clicks Apply (every apply is recorded as a user decision).
3. Exports: **HTML + PDF + DOCX** (plus ATS plain text, which is free).

---

## 1. Goal and non-goals

**Goal.** A `#/builder` route where the resume is a live, drag-and-drop document
that (a) always starts from the same structure the app already assembles and
renders, (b) is fully editable — content, section order, layout, typography,
(c) can be tailored per job application, and (d) gets precise, grounded,
human-approved improvement proposals from the provider the user picked in
Settings.

**Non-goals (explicit).**

- No auto-writing into the document. No "apply all". No submission automation.
- No fabrication: proposals must be grounded in confirmed facts / KB entries /
  the job description; anything else is dropped before it reaches the screen.
- No new runtime dependencies, no CDN, no build step, no network at runtime —
  local-first as always (vendored, committed assets).
- No free-form CMS. The builder edits a *resume*, not arbitrary web pages.

**Principles preserved:** local-first, 2 GB RAM, no mandatory API key,
every fact traceable, raw resume text never persisted (only structure + spans +
user overrides, as today).

---

## 2. Why this tool, and exactly how it gets customized

### 2.1 What we verified (not assumed)

| Fact | Value | Why it matters |
|---|---|---|
| `grapesjs` | 0.23.6, **BSD-3-Clause** (`package/LICENSE` confirmed) | No license contamination (ADR-2 discipline: AGPL was rejected there too) |
| `grapesjs-preset-newsletter` | 1.0.2, **BSD-3-Clause** | Same |
| Build format | both publish UMD `dist/*.js` (+ `grapes.min.css`) | `<script>` in the browser — **no bundler**, matches the repo's zero-JS-tooling reality |
| Preset export shape | `window["grapesjs-preset-newsletter"].default` = `fn(editor, opts)` | Pass straight into `grapesjs.init({ plugins: [...] })` |
| Preset default blocks | `sect100, sect50, sect30, sect37, button, divider, text, text-sect, image, quote, link, link-block, grid-items, list-items` | This is our main customization seam (`opts.blocks`) |
| Preset extras | Style-manager sectors (Background/Font/Decorations…), an `export-template` command with an `export-code` modal | Reused as-is for layout editing and HTML export |
| Sizes | `grapes.min.js` 1.15 MB, `grapes.min.css` 61 KB, preset 396 KB | ~1.6 MB on disk, local `no-cache` fetch, well inside 2 GB RAM |

Node 22 + npm are present on this machine, so vendoring is a one-time script;
**runtime never touches npm or the network.**

### 2.2 Preset feature → NoLoop customization

| Newsletter preset gives us | We customize it to |
|---|---|
| 15 layout blocks (100/50/30/37 columns, text, list, quote, button…) | `opts.blocks` trimmed to layout-only blocks **plus** custom resume blocks: `nl-header`, `nl-summary`, `nl-section`, `nl-role` (repeating experience entry), `nl-bullet`, `nl-skills` (chip list), `nl-timeline`, `nl-education`, `nl-cert`, `nl-project`, `nl-contact-row` |
| Free text components | Every text component can carry `data-nl-path` — a path into the assembled resume doc (`contact.email`, `experience[1].bullets[0]`) — so the canvas is **bound**, not a detached mock |
| Style Manager sectors (typography, background, spacing) | Styles write CSS variables (`--nl-accent`, `--nl-body`, `--nl-scale`) consumed by the resume stylesheet → theme changes are one token, applied to every section, and survive export |
| Layer manager = DOM tree | Becomes the **section order editor** (drag Experience above Skills etc.), which is exactly the "structure" requirement |
| `export-template` + `export-code` dialog | Rewired to our export panel: HTML (self-contained), ATS text, PDF, DOCX |
| Blocks palette (left sidebar) | Blocks palette = resume blocks + layout blocks; every dropped resume block starts *bound and empty*, with a hint "pull from profile" rather than fake content |
| Traits (component settings panel) | Traits: `data-nl-path` picker (select bound field), `nlRepeat` (for `experience`/`skills`), `nlSource` (facts ⇄ user-edited) |
| Undo/redo, clipboard, code editor (CodeMirror bundled) | Kept — it's free and it's what makes the builder feel real; the code editor stays available but shows a "bound fields break here" warning |
| Newsletter image/social/stock blocks | **Dropped** (`opts.blocks` list) — irrelevant to a resume, and they invite decoration that ATS parsers discard |

The preset is a *starting configuration*, not a product: we keep its engine
(layout blocks, style manager, export plumbing) and replace its domain
(blocks, bound content, resume stylesheet, export targets).

---

## 3. Architecture

### 3.1 One source of truth, three views

```
confirmed ResumeFact + KBEntry ──► ResumeAssembler.build() ──► doc (existing)
                                            │
                        ┌───────────────────┴──────────────────────┐
                        ▼                                          ▼
        render_resume_skeleton(doc, layout)            renderer.render_resume_pdf/docx(doc)
        (server: sections→HTML, bound paths)            (existing, ATS-safe)
                        │
                        ▼
             GrapesJS canvas  ◄── user edits (content, order, style)
                        │
              diff(canvas HTML vs doc) ──► overrides {path: text}
                        │
        ┌───────────────┼────────────────────────┐
        ▼               ▼                        ▼
  AI propose      variant store            exports (HTML / PDF / DOCX / ATS text)
```

- **doc** stays the semantic truth (facts, provenance, coverage).
- **canvas** is a *view* of doc + user overrides; it never invents fields.
- **overrides** are the only free-text the human owns, stored per variant.
- **PDF/DOCX** are produced from the *merged* doc (doc + overrides), so the
  structured renderer keeps working untouched.
- **HTML export** is produced from the canvas (the visual version).

### 3.2 Binding contract

```html
<div class="nl-role" data-nl-path="experience[1]" data-nl-repeat="experience">
  <h3 data-nl-path="experience[1].role">…</h3>
  <div data-nl-path="experience[1].employer">…</div>
  <ul data-nl-path="experience[1].bullets" data-nl-repeat-item="bullets">…</ul>
</div>
```

- `data-nl-path` — dot/index path into `doc`; the *only* way content is mapped.
- Server renders the skeleton (Python, `selectolax`-parseable, deterministic,
  unit-testable) → GrapesJS loads it as `components`.
- `POST /api/builder/save` sends `{project, html, css}`; the server walks `html`
  with selectolax and computes `overrides = {path: text}` by diffing against
  `doc`. **No override is created for text that matches doc** — provenance stays
  "came from a fact" until the human actually changes it.
- A "Refresh from profile" action re-seeds only paths that are *not* overridden
  (`nlSource=facts`), so a re-import never silently discards human edits.

### 3.3 State and lifecycles (SPA hazards, planned for)

- Route module loads `vendor/grapesjs/grapes.min.css` + `preset-newsletter.min.js`
  once (idempotent loader, `window.grapesjs` guard) — the repo has no dynamic
  script loader today, so this becomes `js/core/grapesjs_loader.js`.
- On `route:leave`: `editor.destroy()` + remove injected `<link>`/`<script>` and
  GrapesJS's appended styles — otherwise the next route inherits the editor's
  CSS and leak listeners (this is the classic GrapesJS-in-SPA bug).
- Autosave debounce (2 s) + explicit Save; unsaved-changes guard on leave.

---

## 4. Storage and API

### 4.1 Collections (JsonStore, same as everything else)

| Collection | Key | Contents |
|---|---|---|
| `resume_templates` | `tpl_<id>` | `{name, project, html, css, layout: {sections: [...]}, created_at, updated_at}` — the reusable "look" |
| `resume_variants` | `<profile_id>` or `<profile_id>:<application_id>` | `{profile_id, application_id?, template_id, overrides: {path: text}, applied: [{path, proposed, reason, provider, at}], updated_at}` |

Raw resume text is **still never stored**. Overrides are user-authored resume
text (like any other user entry), and each carries its own provenance record.

### 4.2 Endpoints (registered in `_register_routes`, tested through the tables)

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/builder/bootstrap?profile_id=&application_id=` | `{doc, skeleton_html, template, overrides, application, ai: {provider, available, label}, coverage, parseability}` |
| `POST` | `/api/builder/template` | create/update a template (project + html + css) |
| `POST` | `/api/builder/variant` | save `{profile_id, application_id?, project, html, css}` → server diffs → overrides |
| `POST` | `/api/builder/suggest` | AI propose-only list (below) |
| `POST` | `/api/builder/apply` | apply one suggestion → override + `applied[]` record + state publish |
| `POST` | `/api/builder/export` | `{format: html\|pdf\|docx\|text, profile_id, application_id?}` → base64 + filename + `ats_score` |
| `GET` | `/api/builder/list?profile_id=` | templates + variants for pickers |

- **Body limit:** `_MAX_JSON_BODY` is 64 KiB (`server.py:58`) and GrapesJS
  project JSON blows past it → add a per-route raised limit (2 MB) exactly the
  way `/api/resume/import` already does (`server.py:59,1574-1577`).
- SSE: publish `builder_saved` / `builder_suggested` via the existing broker so
  other views stay consistent.

---

## 5. AI assist (propose-only, grounded, works with no key)

### 5.1 Flow

```
POST /api/builder/suggest {profile_id, application_id?, jd_text?, focus?}
 1. facts (confirmed) + KB entries + doc text + JD  → bounded prompt (≤ 4k chars)
 2. AIRegistry(settings).resolve()  → gemini | local | rule   (what Settings picked)
 3. complete_async(..., json_mode=True)  → suggestions[]
 4. validation gate (schema + grounding)  → drop anything ungrounded
 5. response {provider, suggestions[]}
```

### 5.2 Suggestion shape

```json
{"id":"s1","path":"experience[0].bullets[2]","kind":"rewrite",
 "current":"Worked on payments","proposed":"Owned the payments API migration (Go, Kafka)",
 "reason":"Restates a vague duty as an owned outcome; matches JD term 'payments API'",
 "evidence":["Built payment APIs in C++, Python and Go serving 40k req/s","JD: payments API"],
 "priority":2,"grounded":true}
```

`kind ∈ {rewrite, reorder, drop, add_section, style, ats}`; `path` is a binding
path so the panel can **highlight the exact component** in the canvas (scroll +
outline) — that is the "pinpoint" requirement.

### 5.3 Grounding gate (non-negotiable)

- Every proposal must trace to a fact span, a KB entry, or the JD. Evidence
  strings are returned with it so the user sees *why*.
- Numbers and proper nouns in `proposed` that do not appear in the evidence set
  are rejected server-side (`ungrounded` → dropped; count reported honestly as
  `dropped` in the response).
- Never propose an employer, date, credential or metric that isn't in facts/KB.
- Applied suggestions are stored in `applied[]` with provider + reason (audit),
  and become *overrides* — i.e. the human's text, not the AI's fact.

### 5.4 No-key / no-network behaviour

If `resolve()` yields the rule provider (or raises `ProviderUnavailableError`),
the endpoint still answers with **deterministic local suggestions** built from
existing services:

- `tailoring_suggestions(jd)` → missing JD terms (each with the explicit
  "do NOT claim" guard already in the code),
- coverage/parseability gaps → "no projects section", "dates mixed",
- facts still `inferred` → "confirm this so it can be quoted",
- style/ATS checks on the canvas (single column, no tables, heading hierarchy).

So the panel is never dead; it just says `provider: rule` honestly.

### 5.5 Cost/latency bounds

One call per click (never a loop), `max_tokens ≈ 900`, `temperature 0.0`,
timeout 25 s, results cached per `(profile, jd_hash)` for the session. Local
provider gets the same contract (it may return fewer/no suggestions — reported,
not faked).

---

## 6. Exports

| Format | Produced from | Path | Notes |
|---|---|---|---|
| **HTML** | canvas `html` + `css`, inlined into one self-contained file | server-side | This is the *visual* resume — colours, columns, typography survive |
| **ATS text** | merged doc → `ResumeAssembler.resume_text()` | existing | What you paste into an application form |
| **PDF** | merged doc → `render_resume_pdf()` (reportlab, single column) | existing | **Honest limitation:** the PDF is the ATS-safe structured rendering, not a pixel copy of the canvas (ADR-7 rejected weasyprint; no headless browser). Plan documents this in the export dialog so nobody is surprised |
| **DOCX** | merged doc → `render_resume_docx()` | existing | Same |

The export dialog states which artifact is "visual" (HTML) and which is
"ATS-safe structured" (PDF/DOCX/text), with `ats_score` shown for the current JD.

---

## 7. Per-application variants (the "each position per company" part)

- Pipeline card (`#/applications`) gains **"Resume for this job"** →
  `#/builder?application=<id>`, which loads
  `resume_variants[profile_id:application_id]`, the application's JD text, and
  the application's company/title for the header line.
- First open seeds from the profile's default variant + template (fast start),
  then edits and AI proposals are scoped to *that* company's JD.
- `GET /api/builder/list` shows per-application variants so switching is one
  click; deleting an application leaves its variant (recorded, not orphaned).
- **This is assistance, not automation:** nothing is submitted, nothing is
  rewritten without a click, and the ATS score / suggestions are advisory.

---

## 8. Phases, each with acceptance criteria

**P0 — vendored editor that opens and edits (this session, first slice)**
- `scripts/vendor_grapesjs.ps1` pulls the two npm tarballs once and writes
  `app/ui/static/vendor/grapesjs/{grapes.min.js,grapes.min.css,preset-newsletter.min.js,NOTICE.md}`
  (licenses, versions, source URLs). Files committed; runtime offline.
- `#/builder` route + nav entry + i18n keys + loader with `destroy()` teardown.
- Skeleton rendered from `ResumeAssembler.build()`; bound `data-nl-path`
  components; blocks palette (resume + layout blocks); Style Manager on CSS vars.
- `GET /api/builder/bootstrap` + `POST /api/builder/variant` (save → server-side
  override diff).
- *Accept:* open builder → see own resume → drag Experience above Skills → type
  into a bullet → reload → changes persist → `overrides` contains exactly the
  changed paths → leaving the route removes GrapesJS CSS → suite green.

**P1 — AI propose panel**
- `suggest` / `apply` endpoints + schema + grounding gate + rule fallback.
- Panel UI: grouped by priority, each row shows current → proposed, reason,
  evidence, provider; click a row to highlight the bound component; Apply /
  Dismiss / Dismiss-all; `dropped` count shown honestly.
- *Accept:* with no key, panel still fills (rule provider); with Gemini, a
  grounded proposal applies and lands in `applied[]`; a proposal containing an
  invented number is dropped by the gate (unit test proves it).

**P2 — exports + per-application entry**
- Export panel (HTML / ATS text / PDF / DOCX) + `ats_score` for the active JD.
- Pipeline card link, variant picker, JD-aware suggestions.
- *Accept:* HTML opens standalone in a browser; PDF/DOCX match the merged doc;
  `#/applications` → builder loads that company's variant + JD.

**P3 — polish (documented, not blocking)**
- Template gallery (save/duplicate/rename), section visibility toggles,
  print-preview at A4/Letter, keyboard shortcuts, a11y pass on GrapesJS panels
  (aria-labels on icon buttons), mobile "best on desktop" notice.

### Verification strategy (every phase)

1. `pytest -q` (must stay green; every commit runs it).
2. Unit: skeleton render (paths present, no raw resume text leak), override diff
   (only changed paths), AI gate (grounded pass / ungrounded drop / rule path).
3. Integration: endpoints exercised through the real route tables
   (`tests/integration/test_builder_api.py`, mirroring `test_ui_api.py`).
4. Real-browser pass with the `agent-browser` skill (precedent in the ledger):
   open builder, drag a section, edit a bullet, apply one AI suggestion,
   export HTML — screenshot as evidence.
5. Manual checklist in the phase section of the ledger entry.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| GrapesJS in a hash-SPA leaks CSS/listeners | explicit `destroy()` on `route:leave`, loader with refcount, integration test that head has no leftover `grapesjs` assets after leaving |
| Project JSON > 64 KiB body cap | per-route raised limit (2 MB) as `/api/resume/import` already does |
| 1.15 MB editor + CodeMirror, 2 GB budget | lazy-load only on `#/builder`; measured in the browser pass (memory readout logged in the ledger); no second editor instance ever alive |
| AI fabricates a metric | server-side grounding gate + `evidence` + drop-and-report; never writes to the canvas without a click |
| No API key ⇒ dead panel | deterministic rule-provider suggestions (tailoring + coverage + confirmations) |
| Canvas style ≠ PDF style (reportlab) | export dialog states it plainly; ATS text/PDF derive from the same merged doc so *content* is always identical across formats |
| Editor feels like a website builder (off-target) | custom `nl*` blocks only; newsletter/social/image blocks removed; palette shows resume semantics |
| Bound component deleted by the user | `data-nl-path` records are kept in a side map; deleting a bound component offers "hide section" (visibility off) instead of losing the path; restoring re-seeds from doc |
| Overrides drifting from facts after re-import | `nlSource` split (facts vs user), Refresh only touches non-overridden paths, and the variant shows "N fields differ from profile" |
| GrapesJS a11y/mobile limits | documented limitation + P3 mitigations; the app stays usable without the builder |

---

## 10. Out of scope (recorded so it isn't quietly assumed)

- Headless-browser PDF that pixel-matches the canvas (needs Chromium;
  incompatible with the 2 GB local-first target today).
- Auto-tailoring that writes the resume for the user.
- Collaborative/multi-user editing, cloud sync, template marketplace.
- OCR (P2.14 of `RESUME_PROCESSING_UPGRADE.md`) and the local small-model tier
  (P2.13) — orthogonal, still pending there.

---

## 11. References

- GrapesJS 0.23.6 (BSD-3-Clause) — `registry.npmjs.org/grapesjs`, `dist/grapes.min.js`,
  `LICENSE` verified locally from the tarball (2026-09-30).
- GrapesJS preset-newsletter 1.0.2 (BSD-3-Clause) — `dist/index.js` UMD default
  export `(editor, opts)`; default `opts.blocks` list read from the bundle.
- NoLoop: `No_Loop_docs/RESUME_PROCESSING_UPGRADE.md` (structure/extraction
  contract), `app/services/resume_builder.py` (doc shape), `app/services/renderer.py`
  (PDF/DOCX), `app/services/ai_registry.py` (provider resolution),
  `app/ui/server.py` (route tables, body limits, static serving).
- Evidence for ATS structure constraints: EDLIGO 2025 / ATSChecker 2026 figures
  cited in `app/adapters/parseability.py` (two-column 31% failure vs ~4% plain).

---

## 12. Implementation status (first slice: built and verified 2026-09-30)

P0 + P1 + most of P2 are delivered, tested, and exercised in a real browser.
P3 (template gallery UI, Style Manager, a11y pass) is deliberately not started.

| Piece | Where | State |
|---|---|---|
| Vendored editor | `scripts/vendor_grapesjs.ps1` -> `app/ui/static/vendor/grapesjs/` (GrapesJS 0.23.6 + preset-newsletter 1.0.2, BSD-3-Clause, UMD, committed) | done, runtime offline: no CDN, no build step |
| Loader + teardown | `js/core/grapesjs_loader.js` (idempotent load, `unloadGrapesJS()` on `route:leave`) | done - verified CSS and editor are gone after leaving, rebuilt on return |
| Route | `#/builder`, `js/routes/builder.js` (846 lines), nav entry, `css/builder.css`, `builder.*` i18n keys | done |
| Skeleton + diff | `services/builder_template.py`: `render_skeleton` -> `bound_values` -> `diff_overrides` -> `merge_doc` -> `section_order` / `html_export` / `text_export` | done, unit-tested |
| AI propose-only | `services/builder_ai.py`: prompt, JSON parse, grounding gate, `local_suggestions` for the no-key tier | done, unit-tested; the rule tier never invents wording |
| API + service | `services/builder_service.py`, 7 routes in `app/ui/server.py` (`bootstrap`, `list`, `variant`, `template`, `suggest`, `apply`, `export`) + a 20 MB body cap for the save routes | done, integration-tested (`tests/integration/test_builder_api.py`) |
| Exports | HTML from the canvas; PDF / DOCX / ATS text from the merged doc | done - all four downloaded in the browser with correct MIME types |
| Per-application variants | key `profile_id[:application_id]`, picker in the toolbar, `ats_score` when the application has a JD | done - verified against a seeded application |

### Deviations from this plan (deliberate, and disclosed in the UI)

1. **Canvas structure is rebuilt from the profile on every visit** (the P0 limitation
   accepted at build time). `bootstrap` returns `structure` (section -> bound paths) plus the
   skeleton HTML; a block the human *adds* to the canvas that has no fact behind it does not
   come back after a reload. Saved **overrides do**, section order does, and the HTML export
   always contains whatever was on the canvas at export time. The UI states this in
   `builder.structureHint`. Next step: persist `variant.html` and merge it over the skeleton
   on boot.
2. **ATS plain text comes from a new `text_export()`, not `ResumeAssembler.resume_text`.**
   That function is the flat *scoring* string (no contact line, no dates, no headings) and
   would have shipped a resume nobody can answer. `text_export` keeps contact, section
   headings, employers, periods and bullets and follows the canvas section order;
   `resume_text` still feeds `ats_score`.
3. **Only the Resume block category is registered** (`opts.blocks: []` disables the
   newsletter blocks): Text / Bullets / Job entry / Skill chips / Divider. Keeps this a
   resume, not a CMS (section 1 non-goal). A separate layout-block palette is P3.
4. **No Style Manager / CSS-variable editor yet** (a P0 line item): the preset's own panels
   are used as-is, `showDevices` is off, typography comes from the resume stylesheet. P3.
5. **GrapesJS chrome stays dark in the light theme** - cosmetic: the preset ships its own
   panel styles and overriding them is P3 polish.
6. **Template gallery UI is not built.** `GET /api/builder/list` and
   `POST /api/builder/template` exist and are tested, so templates can be saved over the
   API; the picker is P3.

### Verification (2026-09-30: browser + suites)

- Boot -> own resume on the canvas, 7 sections, blocks palette, **zero console errors**.
- Type into a bullet -> 900 ms chained autosave -> `overrides` holds exactly that path;
  type the fact text back -> the override disappears (it is a diff, not a history).
- Move Experience above Skills (structure panel) -> persists, and every export follows the
  new order.
- Suggest with no key -> 1 Confirm + filler-bullet rewrites with **empty `proposed`**
  (pointed at, never ghost-written) + one ATS note with clean terms; with a JD attached the
  ATS note names the missing terms and says "do NOT claim them".
- Apply (a fetch-intercepted response standing in for a configured provider) -> POST apply
  -> canvas re-renders -> toast "saved as your decision" -> `override_count` 1.
- Leave the route mid-edit -> the pending save fires before teardown; returning rebuilds
  the editor; GrapesJS CSS and the `window.nlBuilder` debug handle are gone after leave.
- Exports: `ada-lovelace.{html,pdf,docx,txt}` all downloaded; the `.txt` carries name,
  contact, `EXPERIENCE`, employers, periods and bullets.
- Gates: `pytest -q` green, `ruff check` clean, `ruff format` clean on every file touched
  (repo-wide it still flags only `app/adapters/gemini_provider.py`, someone else's
  uncommitted edit), `mypy app` clean, `node --check` on all five changed JS files.
