/* builder.js — the visual resume canvas (GrapesJS, vendored, offline).
 *
 * Contract with the server (see RESUME_BUILDER_PLAN.md):
 *
 * - The canvas shows the *bound skeleton*: every editable piece of content
 *   carries a `data-nl-path` (`experience[1].bullets[0]`). Drag, restyle and
 *   retype freely — on save the server diffs the markup against the assembled
 *   doc and keeps only the paths the human actually changed.
 * - The AI proposes. Nothing is written until the human clicks Apply, and the
 *   applied text becomes an override with an audit record.
 * - PDF / DOCX / plain text are rendered from the merged doc (facts + your
 *   overrides); HTML is rendered from this canvas.
 */

import api from "../core/api.js";
import { get } from "../core/store.js";
import t from "../core/i18n.js";
import { el, clear, toast, esc, ICONS, busy, modal, emptyState } from "../core/ui.js";
import { loadGrapesJS, presetPlugin, unloadGrapesJS } from "../core/grapesjs_loader.js";

const SAVE_DEBOUNCE_MS = 900;

/** Events that mean the human changed something worth persisting. */
const DIRTY_EVENTS = [
  "component:add",
  "component:remove",
  "component:update",
  "component:content",
  "component:move",
  "component:paste",
  "component:clone",
  "component:input",
  "canvas:drop",
  "style:property:add",
  "style:property:remove",
  "style:property:update",
  "undo",
  "redo",
];

/** Insertable resume structure. Deliberately UNBOUND: no `data-nl-path`, so a
 *  dropped-in block never masquerades as a confirmed fact — its text lives in
 *  the HTML export only, until the matching fact exists. */
const BLOCKS = [
  {
    id: "nl-text",
    label: "Text",
    content: '<p class="nl-summary-text">New paragraph</p>',
  },
  {
    id: "nl-bullets",
    label: "Bullets",
    content: '<ul class="nl-bullets"><li>First point</li><li>Second point</li></ul>',
  },
  {
    id: "nl-role",
    label: "Job entry",
    content:
      '<article class="nl-role" data-nl-repeat="experience">'
      + '<div class="nl-role-head"><h3 class="nl-role-title">Job title</h3>'
      + '<span class="nl-period">Dates</span></div>'
      + '<div class="nl-company">Company</div>'
      + '<ul class="nl-bullets"><li>What you achieved</li></ul></article>',
  },
  {
    id: "nl-chips",
    label: "Skill chips",
    content: '<ul class="nl-skills" data-nl-repeat="skills"><li class="nl-chip">Skill</li></ul>',
  },
  {
    id: "nl-divider",
    label: "Divider",
    content: '<div style="height:1px;background:var(--nl-accent);opacity:.4;margin:14px 0"></div>',
  },
];

const SECTION_LABELS = {
  header: "builder.section.header",
  summary: "builder.section.summary",
  skills: "builder.section.skills",
  experience: "builder.section.experience",
  projects: "builder.section.projects",
  education: "builder.section.education",
  certifications: "builder.section.certifications",
};

/* ------------------------------------------------------------------ state -- */
let editor = null;
let boot = null;
let metaBox = null;
let profileId = "";
let appId = "";
let saveTimer = 0;
let saveChain = Promise.resolve();
let lastSaved = "";
let dirty = false;
let saveState = "idle";

/* -------------------------------------------------------------- dom utils -- */
const childrenOf = (comp) => {
  if (!comp || typeof comp.components !== "function") return [];
  const col = comp.components();
  if (!col) return [];
  if (Array.isArray(col)) return col;
  if (Array.isArray(col.models)) return col.models;
  try {
    return Array.from(col);
  } catch {
    return [];
  }
};

/** Depth-first search for the component bound to `path`. */
function findBound(path) {
  if (!editor || !path) return null;
  let hit = null;
  const walk = (comp) => {
    if (hit || !comp) return;
    const attrs = (comp.getAttributes && comp.getAttributes()) || {};
    if (attrs["data-nl-path"] === path) {
      hit = comp;
      return;
    }
    for (const child of childrenOf(comp)) walk(child);
  };
  walk(editor.getWrapper());
  return hit;
}

function sectionComponents() {
  const out = [];
  if (!editor) return out;
  const walk = (comp) => {
    const attrs = (comp.getAttributes && comp.getAttributes()) || {};
    if (attrs["data-nl-section"]) {
      out.push({ name: attrs["data-nl-section"], comp });
      return; // sections do not nest
    }
    for (const child of childrenOf(comp)) walk(child);
  };
  walk(editor.getWrapper());
  return out;
}

function selectComponent(comp) {
  if (!comp) return;
  try {
    if (typeof editor.select === "function") editor.select(comp);
    else if (typeof comp.set === "function") comp.set("selected", true);
  } catch {
    /* selection is a nicety; never break the panel over it */
  }
  const node = comp.getEl && comp.getEl();
  if (node && typeof node.scrollIntoView === "function") {
    node.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

/* -------------------------------------------------------------- lifecycle -- */
function teardown() {
  clearTimeout(saveTimer);
  if (editor) {
    try {
      editor.destroy();
    } catch (err) {
      console.warn("[builder] destroy failed", err);
    }
    editor = null;
  }
  if (window.nlBuilder) delete window.nlBuilder;
  unloadGrapesJS();
}

export async function render(params = new URLSearchParams()) {
  teardown();
  const state = get();
  profileId = state.activeProfileId || "";
  appId = params.get("application") || "";

  const page = el("div.page.builder");
  if (!profileId) {
    page.append(
      el("div.page-head", {}, [
        el("div.page-head__text", {}, [
          el("h1", { text: t("builder.title") }),
          el("p", { text: t("builder.sub") }),
        ]),
      ]),
      emptyState({
        icon: ICONS.file,
        title: t("builder.noProfile"),
        body: t("builder.noProfileBody"),
      }),
    );
    return page;
  }

  boot = await api.builderBootstrap(profileId, appId);
  const gfx = await loadGrapesJS().catch((err) => err);
  buildPage(page, gfx instanceof Error ? gfx : null);
  exposeDebug();
  page.addEventListener("route:leave", onLeave, { once: true });
  return page;
}

function onLeave() {
  saveNow(); // payload is snapshotted synchronously, before destroy()
  teardown();
}

/** Diagnostics handle for devtools/automation: the live editor instance. */
function exposeDebug() {
  window.nlBuilder = {
    editor: () => editor,
    boot: () => boot,
    save: () => saveNow(),
    markup: () => currentMarkup(),
  };
}

/* ------------------------------------------------------------ page layout -- */
function buildPage(page, gfxError) {
  clear(page);

  /* head ------------------------------------------------------------ */
  const head = el("div.page-head");
  const text = el("div.page-head__text");
  text.append(el("h1", { text: t("builder.title") }), el("p", { text: t("builder.sub") }));

  const actions = el("div.page-head__actions");
  const appSel = el("select.select.builder__apps", { "aria-label": t("builder.appLabel") });
  appSel.append(el("option", { value: "", text: t("builder.appNone") }));
  for (const a of get().snapshot?.kanban || []) {
    appSel.append(
      el("option", {
        value: a.full_id || a.id,
        text: `${a.title || t("builder.appUntitled")} · ${a.company || ""}`,
      }),
    );
  }
  appSel.value = appId;
  appSel.addEventListener("change", () => {
    const v = appSel.value;
    location.hash = v ? `#/builder?application=${encodeURIComponent(v)}` : "#/builder";
  });
  actions.append(appSel);
  actions.append(
    el("button.btn.btn--ghost", {
      type: "button",
      text: t("builder.save"),
      onclick: (e) => {
        const done = busy(e.currentTarget, "");
        saveNow().finally(done);
      },
    }),
    el("button.btn.btn--primary", { type: "button", text: t("builder.export"), onclick: openExport }),
  );
  head.append(text, actions);
  page.append(head);

  /* status line ------------------------------------------------------ */
  const meta = el("div.builder__meta");
  metaBox = meta;
  page.append(meta);
  paintMeta(meta);

  if (gfxError) {
    page.append(
      el("div.notice.notice--bad", {
        html: `${ICONS.alert}<span><strong>${esc(t("builder.engineFailed"))}</strong> ${esc(
          gfxError.message || "",
        )}</span>`,
      }),
    );
    return;
  }

  /* grid ------------------------------------------------------------- */
  const grid = el("div.builder__grid");
  const main = el("div.builder__main");
  const canvas = el("div.builder__canvas#nl-canvas");
  main.append(canvas);

  const side = el("aside.builder__side");
  const tabs = el("div.segmented.builder__tabs");
  const tabAi = el("button", { type: "button", text: t("builder.tabAi") });
  const tabSt = el("button", { type: "button", text: t("builder.tabStructure") });
  tabs.append(tabAi, tabSt);

  const panelAi = el("div.builder__panel");
  const panelSt = el("div.builder__panel");
  panelSt.hidden = true;

  const showAi = () => {
    panelAi.hidden = false;
    panelSt.hidden = true;
    tabAi.classList.add("is-active");
    tabSt.classList.remove("is-active");
  };
  const showSt = () => {
    panelSt.hidden = false;
    panelAi.hidden = true;
    tabSt.classList.add("is-active");
    tabAi.classList.remove("is-active");
  };
  tabAi.addEventListener("click", showAi);
  tabSt.addEventListener("click", showSt);
  showAi();

  side.append(tabs, panelAi, panelSt);
  grid.append(main, side);
  page.append(grid);

  initAiPanel(panelAi);
  initStructurePanel(panelSt);

  try {
    initEditor(canvas);
  } catch (err) {
    console.error("[builder] init failed", err);
    canvas.replaceWith(
      el("div.notice.notice--bad", {
        html: `${ICONS.alert}<span><strong>${esc(t("builder.engineFailed"))}</strong> ${esc(
          err?.message || String(err),
        )}</span>`,
      }),
    );
    return;
  }

  paintStructure();
  paintSelection();
}

/* ------------------------------------------------------------------ meta -- */
function paintMeta(node = metaBox) {
  const box = node || document.querySelector(".builder__meta");
  if (!box || !boot) return;
  clear(box);

  if (boot.ats_score != null) {
    box.append(
      el("span.tag.tag--accent", {
        text: `${t("builder.ats")} ${Math.round(Number(boot.ats_score) * 100)}%`,
        title: t("builder.atsHint"),
      }),
    );
  }
  const edits = boot.override_count ?? 0;
  box.append(
    el("span.tag", {
      text: edits ? t("builder.overrides", { n: edits }) : t("builder.overridesNone"),
    }),
  );
  if (boot.ai?.label) {
    box.append(el("span.tag.tag--info", { text: `${t("builder.ai")}: ${boot.ai.label}` }));
  }
  if (boot.pending_facts) {
    box.append(
      el("span.tag.tag--warn", {
        text: t("builder.pending", { n: boot.pending_facts }),
        title: t("builder.pendingHint"),
      }),
    );
  }
  if (boot.application) {
    box.append(
      el("span.tag.tag--manual", {
        text: `${boot.application.title || ""} · ${boot.application.company || ""}`,
      }),
    );
  }
  box.append(el("span.builder__save-state", { text: saveStateText() }));
}

function saveStateText() {
  if (saveState === "saving") return t("builder.saving");
  if (saveState === "error") return t("builder.saveError");
  if (dirty) return t("builder.unsaved");
  if (lastSaved) return t("builder.savedAt", { time: lastSaved });
  return t("builder.saved");
}

function setSaveState(next, isDirty = false) {
  saveState = next;
  dirty = isDirty;
  const node = document.querySelector(".builder__save-state");
  if (node) node.textContent = saveStateText();
  if (metaBox && next !== "saving" && next !== "error") paintMeta(metaBox);
}

/* ------------------------------------------------------------- persistence -- */
function currentMarkup() {
  if (!editor) return "";
  let html = "";
  try {
    html = editor.getHtml();
  } catch {
    return "";
  }
  const body = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  if (body) html = body[1];
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  // GrapesJS-generated ids are noise in an export; user-set ids stay.
  tpl.content.querySelectorAll("[id]").forEach((node) => {
    const id = node.getAttribute("id") || "";
    if (/^i\d+$/.test(id) || id === "wrapper") node.removeAttribute("id");
  });
  return tpl.innerHTML;
}

function currentCss() {
  if (!editor) return "";
  try {
    return typeof editor.getCss === "function" ? editor.getCss() : "";
  } catch {
    return "";
  }
}

function scheduleSave() {
  dirty = true;
  setSaveState(saveState === "error" ? "error" : "idle", true);
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveNow(), SAVE_DEBOUNCE_MS);
}

/** Saves are chained so two quick edits never race each other. */
function saveNow() {
  clearTimeout(saveTimer);
  if (!editor) return saveChain;
  const payload = {
    profile_id: profileId,
    application_id: appId || "",
    html: currentMarkup(),
    css: currentCss(),
    project: editor.getProjectData ? editor.getProjectData() : null,
    template_id: boot?.template_id || "",
  };
  saveChain = saveChain.then(async () => {
    setSaveState("saving");
    try {
      const res = await api.builderSave(payload);
      if (boot) boot.override_count = res.override_count;
      lastSaved = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setSaveState("saved", false);
      paintStructure();
    } catch (err) {
      setSaveState("error", true);
      console.warn("[builder] save failed", err);
      toast(err.message || t("builder.saveError"), "bad");
    }
  });
  return saveChain;
}

/* --------------------------------------------------------------- editor ---- */
function initEditor(container) {
  const preset = presetPlugin();
  const plugins = [];
  if (preset) {
    plugins.push((ed) => {
      try {
        // `blocks: []` switches off the newsletter blocks — this canvas only
        // offers resume structure (added below).
        preset(ed, { blocks: [] });
      } catch (err) {
        console.warn("[builder] preset failed to start", err);
      }
    });
  }

  editor = window.grapesjs.init({
    container,
    plugins,
    height: "100%",
    width: "auto",
    storageManager: false, // no localStorage copy of the resume
    fromElement: false,
    style: boot?.css || "",
    assetManager: { upload: "", assets: [] },
    showDevices: false,
  });

  editor.setComponents(boot?.skeleton || "");
  for (const evt of DIRTY_EVENTS) editor.on(evt, scheduleSave);
  editor.on("component:selected", paintSelection);
  editor.on("component:deselected", paintSelection);
  editor.on("load", () => {
    addBlocks();
    paintStructure();
  });
  addBlocks();
}

function addBlocks() {
  if (!editor || !editor.BlockManager) return;
  const bm = editor.BlockManager;
  for (const block of BLOCKS) {
    try {
      bm.add(block.id, {
        label: block.label,
        content: block.content,
        category: t("builder.blocksCategory"),
      });
    } catch (err) {
      console.warn("[builder] block add failed", block.id, err);
    }
  }
}

/* ------------------------------------------------------------ AI propose --- */
function initAiPanel(panel) {
  const focus = el("input.input", {
    type: "text",
    placeholder: t("builder.focusPlaceholder"),
    "aria-label": t("builder.focus"),
  });
  const go = el("button.btn.btn--primary", {
    type: "button",
    text: t("builder.suggest"),
    onclick: (e) => runSuggest(e.currentTarget, focus.value),
  });
  focus.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSuggest(go, focus.value);
  });

  const note = el("div.builder__note");
  const list = el("div.builder__list");

  if (!boot?.ai?.can_generate) {
    note.append(el("p.muted.small", { text: t("builder.localHint") }));
  }

  panel.append(
    el("div.stack", {}, [
      el("p.muted.small", { text: t("builder.proposeOnly") }),
      el("div.builder__suggest-row", {}, [focus, go]),
      note,
      list,
    ]),
  );
}

async function runSuggest(button, focus) {
  const done = busy(button, "");
  const list = document.querySelector(".builder__list");
  const note = document.querySelector(".builder__note");
  try {
    const res = await api.builderSuggest({
      profile_id: profileId,
      application_id: appId || "",
      jd_text: boot?.jd_text || "",
      focus: focus || "",
    });
    if (list) renderSuggestions(list, res);
    if (note) renderNote(note, res);
  } catch (err) {
    toast(err.message || t("builder.suggestFailed"), "bad");
  } finally {
    done();
  }
}

function renderNote(note, res) {
  clear(note);
  const badges = el("div.row", { style: { gap: "6px", "flex-wrap": "wrap" } });
  badges.append(
    el(`span.tag.${res.mode === "ai" ? "tag--ok" : "tag--info"}`, {
      text: res.mode === "ai" ? t("builder.modeAi") : t("builder.modeLocal"),
    }),
  );
  if (res.provider) badges.append(el("span.tag", { text: res.provider }));
  if (res.dropped) badges.append(el("span.tag.tag--warn", { text: t("builder.dropped", { n: res.dropped }) }));
  note.append(badges);
  if (res.note) note.append(el("p.muted.small", { text: res.note }));
}

function renderSuggestions(list, res) {
  clear(list);
  const items = res.suggestions || [];
  if (!items.length) {
    list.append(el("p.muted.small", { text: t("builder.noSuggestions") }));
    return;
  }
  for (const s of items) list.append(suggestionCard(s));
}

function suggestionCard(s) {
  const card = el("div.suggestion.builder__sug");
  const top = el("div.builder__sug-head");
  top.append(el("span.tag.tag--accent", { text: t(`builder.kind.${s.kind}`) }));
  top.append(el("span.faint.small", { text: t("builder.priority", { n: s.priority || 3 }) }));
  if (s.path) top.append(el("code.mono.small", { text: s.path }));
  card.append(top, el("div.suggestion__why", { text: s.reason }));

  if (s.proposed) {
    const swap = el("div.builder__swap");
    if (s.current) swap.append(el("div.builder__old", { text: s.current }));
    swap.append(el("div.builder__new", { text: s.proposed }));
    card.append(swap);
  }
  if (s.evidence?.length) {
    const ev = el("div.builder__ev");
    for (const quote of s.evidence) ev.append(el("span", { text: `“${quote}”` }));
    card.append(ev);
  }

  const actions = el("div.row", { style: { gap: "6px", "flex-wrap": "wrap" } });
  if (s.proposed) {
    actions.append(
      el("button.btn.btn--sm.btn--primary", {
        type: "button",
        text: t("builder.apply"),
        onclick: (e) => applySuggestion(s, e.currentTarget, card),
      }),
    );
  }
  if (s.path) {
    actions.append(
      el("button.btn.btn--sm", {
        type: "button",
        text: t("builder.highlight"),
        onclick: () => {
          const comp = findBound(s.path);
          if (comp) {
            selectComponent(comp);
            document.querySelector(".builder__canvas")?.scrollIntoView?.({
              block: "center",
              behavior: "smooth",
            });
          } else {
            toast(t("builder.notInCanvas", { path: s.path }), "info");
          }
        },
      }),
    );
  }
  actions.append(
    el("button.btn.btn--sm.btn--ghost", {
      type: "button",
      text: t("builder.dismiss"),
      onclick: () => card.remove(),
    }),
  );
  card.append(actions);
  return card;
}

async function applySuggestion(s, button, card) {
  const done = busy(button, "");
  try {
    await saveNow(); // keep whatever the human typed before the override lands
    const res = await api.builderApply({
      profile_id: profileId,
      application_id: appId || "",
      path: s.path,
      proposed: s.proposed,
      reason: s.reason || "",
      provider: boot?.ai?.label || "",
    });
    boot.override_count = res.override_count;
    // Re-read the merged doc so the canvas matches what the exports will say.
    boot = await api.builderBootstrap(profileId, appId);
    if (editor) {
      editor.setComponents(boot.skeleton);
      editor.setStyle(boot.css || "");
    }
    paintMeta();
    paintStructure();
    card?.remove();
    toast(t("builder.applied", { path: s.path }), "ok");
  } catch (err) {
    toast(err.message || t("builder.applyFailed"), "bad");
  } finally {
    done();
  }
}

/* -------------------------------------------------------------- structure -- */
function initStructurePanel(panel) {
  const list = el("div.builder__sections");
  const selection = el("div.builder__selection");
  panel.append(
    el("div.stack", {}, [
      el("h3", { text: t("builder.sections") }),
      list,
      el("p.muted.small", { text: t("builder.structureHint") }),
      el("h3", { text: t("builder.selection") }),
      selection,
      el("p.muted.small", { text: t("builder.exportHint") }),
    ]),
  );
}

function paintStructure() {
  const list = document.querySelector(".builder__sections");
  if (!list) return;
  clear(list);
  const sections = sectionComponents();
  sections.forEach((entry, i) => {
    const row = el("div.builder__sec-row");
    row.append(
      el("button.builder__sec-name", {
        type: "button",
        text: t(SECTION_LABELS[entry.name] || `builder.section.${entry.name}`),
        onclick: () => {
          selectComponent(entry.comp);
          document.querySelector(".builder__canvas")?.scrollIntoView?.({
            block: "center",
            behavior: "smooth",
          });
        },
      }),
      el("button.icon-btn", {
        type: "button",
        "aria-label": t("builder.moveUp"),
        title: t("builder.moveUp"),
        html: "↑",
        onclick: () => moveSection(entry.comp, -1),
      }),
      el("button.icon-btn", {
        type: "button",
        "aria-label": t("builder.moveDown"),
        title: t("builder.moveDown"),
        html: "↓",
        onclick: () => moveSection(entry.comp, 1),
      }),
    );
    row.append(el("span.faint.small", { text: `${i + 1}` }));
    list.append(row);
  });
  if (!sections.length) list.append(el("p.muted.small", { text: t("builder.noSections") }));
}

function moveSection(comp, delta) {
  const parent = comp && typeof comp.parent === "function" ? comp.parent() : null;
  if (!parent) return;
  const list = childrenOf(parent);
  const idx = list.indexOf(comp);
  const at = idx + delta;
  if (idx < 0 || at < 0 || at >= list.length) return;
  parent.append(comp, { at });
  scheduleSave();
  paintStructure();
}

function paintSelection() {
  const box = document.querySelector(".builder__selection");
  if (!box) return;
  clear(box);
  const comp = editor && typeof editor.getSelected === "function" ? editor.getSelected() : null;
  if (!comp) {
    box.append(el("p.muted.small", { text: t("builder.noSelection") }));
    return;
  }
  const attrs = (comp.getAttributes && comp.getAttributes()) || {};
  const path = attrs["data-nl-path"];
  box.append(
    el("p.mono.small", { text: path || t("builder.unbound") }),
    el("p.faint.small", { text: t("builder.selectionHint") }),
  );
}

/* ----------------------------------------------------------------- export -- */
function openExport() {
  const fmt = el("select.select", { "aria-label": t("builder.format") });
  for (const f of [
    ["html", "builder.fmtHtml"],
    ["pdf", "builder.fmtPdf"],
    ["docx", "builder.fmtDocx"],
    ["text", "builder.fmtText"],
  ]) {
    fmt.append(el("option", { value: f[0], text: t(f[1]) }));
  }
  const out = el("div.builder__export-out");
  const body = el("div.stack", {}, [
    el("div.field", {}, [el("label", { text: t("builder.format") }), fmt]),
    el("p.muted.small", { text: t("builder.exportNote") }),
    out,
  ]);

  const dlg = modal({
    title: t("builder.export"),
    subtitle: boot?.application
      ? `${boot.application.title || ""} · ${boot.application.company || ""}`
      : t("builder.appNone"),
    body,
    width: 520,
    actions: [
      el("button.btn.btn--ghost", { type: "button", text: t("builder.cancel"), onclick: () => dlg.close() }),
      el("button.btn.btn--primary", { type: "button", text: t("builder.download"), onclick: (e) => runExport(e.currentTarget, fmt.value, out, dlg) }),
    ],
  });
}

async function runExport(button, format, out, dlg) {
  const done = busy(button, "");
  clear(out);
  try {
    await saveNow();
    const res = await api.builderExport({
      profile_id: profileId,
      application_id: appId || "",
      format,
      html: currentMarkup(),
      css: currentCss(),
    });
    download(res.content_base64, res.mime, res.filename);
    out.append(
      el("p.small", {
        text: t("builder.exported", { name: res.filename, bytes: res.bytes }),
      }),
    );
    if (res.ats_score != null) {
      out.append(
        el("p.small.muted", {
          text: `${t("builder.ats")} ${Math.round(Number(res.ats_score) * 100)}%`,
        }),
      );
    }
    toast(t("builder.exported", { name: res.filename, bytes: res.bytes }), "ok");
    setTimeout(() => dlg.close(), 700);
  } catch (err) {
    out.append(el("p.small.warn", { text: err.message || t("builder.exportFailed") }));
  } finally {
    done();
  }
}

function download(base64, mime, filename) {
  const bin = atob(base64 || "");
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: mime || "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "resume";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export default { render };
