/* app.js — shell bootstrap + hash router.
 *
 * Routes are lazy: each entry in ROUTES maps to a dynamic import(), so the
 * browser only downloads the code for the page the user is actually on.
 */

import store, { get, set, subscribe, setActiveProfile, pushActivity, applyProgress } from "./core/store.js";
import sse from "./core/sse.js";
import api from "./core/api.js";
import t, { applyI18n, setLang, lang } from "./core/i18n.js";
import { el, clear, toast, esc, ICONS, timeAgo, statusTag, countUp } from "./core/ui.js";

/* ------------------------------------------------------------- theme ------ */
const THEME_KEY = "noloop.theme";
const root = document.documentElement;

function applyTheme(mode) {
  root.dataset.theme = mode;
  localStorage.setItem(THEME_KEY, mode);
  const btn = document.getElementById("btn-theme");
  if (btn) {
    btn.setAttribute("aria-label", mode === "dark" ? "Switch to light theme" : "Switch to dark theme");
    btn.title = btn.getAttribute("aria-label");
  }
}
applyTheme(localStorage.getItem(THEME_KEY) || "light");

/* -------------------------------------------------------------- router ---- */
const ROUTES = {
  dashboard: () => import("./routes/dashboard.js"),
  resume: () => import("./routes/resume.js"),
  profile: () => import("./routes/profile.js"),
  jobs: () => import("./routes/jobs.js"),
  applications: () => import("./routes/applications.js"),
  reports: () => import("./routes/reports.js"),
  settings: () => import("./routes/settings.js"),
};

const view = document.getElementById("view");
const SKELETON = view.innerHTML;
let currentRoute = null;
let currentModule = null;
let navToken = 0;

/**
 * The state snapshot shortens ids to 8 chars for display; the API needs the
 * full uuid. Always key the profile list by `full_id` so a click never turns
 * into a 404 "profile not found".
 */
function expandProfileIds(list) {
  return (list || []).map((p) => ({ ...p, id: p.full_id || p.id }));
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [name, query] = raw.split("?");
  const route = (name || "dashboard").replace(/\/$/, "");
  return { route: ROUTES[route] ? route : "dashboard", params: new URLSearchParams(query || "") };
}

function markActive(route) {
  for (const a of document.querySelectorAll("#navlist a")) {
    const on = a.dataset.route === route;
    a.classList.toggle("is-active", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

async function navigate() {
  const { route, params } = parseHash();
  const token = ++navToken;
  if (currentRoute === route && currentModule?.render) {
    currentModule.render(params); // same page, different query
    return;
  }

  // let the outgoing page tear down its subscriptions
  for (const child of [...view.children]) {
    child.dispatchEvent(new CustomEvent("route:leave"));
  }

  markActive(route);
  set({ route }, "route");
  view.setAttribute("aria-busy", "true");
  view.classList.add("is-swapping");
  view.innerHTML = SKELETON; // instant feedback while the chunk downloads

  let mod;
  try {
    mod = await ROUTES[route]();
  } catch (err) {
    console.error("[router] chunk failed", route, err);
    view.innerHTML = "";
    view.append(
      el("div.notice.notice--bad", {
        html: `${ICONS.alert}<span><strong>Couldn't load this page.</strong> ${esc(
          err?.message || "unknown error",
        )}</span>`,
      }),
    );
    return;
  }
  if (token !== navToken) return; // user already moved on

  currentRoute = route;
  currentModule = mod;
  try {
    const node = await mod.render(params, { store, api, sse, t });
    if (token !== navToken) return;
    clear(view).append(node.nodeType ? node : el("div", { html: String(node) }));
    view.classList.remove("is-swapping");
    view.removeAttribute("aria-busy");
    view.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  } catch (err) {
    console.error("[router] render failed", route, err);
    clear(view).append(
      el("div.notice.notice--bad", {
        html: `${ICONS.alert}<span><strong>Render error.</strong> ${esc(err?.message || err)}</span>`,
      }),
    );
  }
}

window.addEventListener("hashchange", navigate);

/* ---------------------------------------------------- global search ------- */
function initSearch() {
  const input = document.getElementById("global-search");
  const panel = document.getElementById("search-results");
  if (!input || !panel) return;
  let timer = null;

  const close = () => {
    panel.hidden = true;
    clear(panel);
  };

  const run = async () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) return close();
    const state = get();
    const rows = [];
    for (const j of state.snapshot?.jobs || []) {
      if (`${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)) {
        rows.push({ kind: "job", label: j.title, sub: j.company, href: `#/jobs?q=${encodeURIComponent(q)}` });
      }
    }
    for (const a of state.snapshot?.kanban || []) {
      if (`${a.title} ${a.company}`.toLowerCase().includes(q)) {
        rows.push({
          kind: "app",
          label: a.title,
          sub: a.company,
          href: `#/applications?q=${encodeURIComponent(q)}`,
        });
      }
    }
    for (const p of state.profiles || []) {
      if (`${p.name}`.toLowerCase().includes(q)) {
        rows.push({ kind: "profile", label: p.name, sub: p.contact_email || "", href: `#/profile?id=${p.id}` });
      }
    }
    clear(panel);
    if (!rows.length) {
      panel.append(el("div.empty", { text: `No matches for “${input.value.trim()}”` }));
    } else {
      for (const r of rows.slice(0, 12)) {
        panel.append(
          el("button", {
            onclick: () => {
              location.hash = r.href.slice(1);
              close();
              input.value = "";
            },
            html: `<span class="r-kind">${esc(r.kind)}</span><b>${esc(r.label)}</b><br><small class="muted">${esc(
              r.sub,
            )}</small>`,
          }),
        );
      }
    }
    panel.hidden = false;
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 160);
  });
  input.addEventListener("focus", () => input.value.trim().length >= 2 && run());
  document.addEventListener("click", (e) => {
    if (!panel.contains(e.target) && e.target !== input) close();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      close();
      input.blur();
    }
  });
}

/* ------------------------------------------------------- activity feed ---- */
function initActivity() {
  const drawer = document.getElementById("activity-drawer");
  const scrim = document.getElementById("scrim");
  const feed = document.getElementById("activity-feed");
  const badge = document.getElementById("activity-badge");
  let unseen = 0;

  const open = () => {
    drawer.hidden = false;
    scrim.hidden = false;
    requestAnimationFrame(() => {
      drawer.classList.add("is-open");
      scrim.classList.add("is-open");
    });
    unseen = 0;
    badge.hidden = true;
  };
  const close = () => {
    drawer.classList.remove("is-open");
    scrim.classList.remove("is-open");
    setTimeout(() => {
      drawer.hidden = true;
      scrim.hidden = true;
    }, 380);
  };

  document.getElementById("btn-activity").addEventListener("click", open);
  document.getElementById("btn-activity-close").addEventListener("click", close);
  scrim.addEventListener("click", close);
  document.getElementById("btn-activity-clear").addEventListener("click", () => {
    set({ activity: [] });
    clear(feed);
    document.getElementById("activity-count").textContent = "";
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !drawer.hidden) close();
  });

  subscribe((state, reason) => {
    if (reason !== "activity") return;
    document.getElementById("activity-count").textContent = `${state.activity.length} events`;
    if (drawer.hidden && state.activity.length) {
      unseen += 1;
      badge.hidden = false;
      badge.textContent = String(Math.min(unseen, 99));
    }
    renderFeed(feed, state.activity);
  });

  return { open, close };
}

function renderFeed(feed, items) {
  clear(feed);
  if (!items.length) {
    feed.append(el("div.empty-state", {}, [el("p", { text: t("activity.empty") })]));
    return;
  }
  for (const it of items.slice(0, 80)) {
    const kind = it.kind || "info";
    const ico =
      kind === "bad"
        ? ICONS.alert
        : kind === "ok"
          ? ICONS.check
          : kind === "run"
            ? ICONS.play
            : ICONS.dot;
    const item = el("li.feed__item");
    item.append(el("span.feed__ico", { class: `feed__ico ${kind}`, html: ico }));
    const body = el("div");
    body.append(el("div.feed__text", { html: it.text || esc(it.detail || "") }));
    body.append(el("div.feed__time", { text: timeAgo(it.at) }));
    item.append(body);
    feed.append(item);
  }
}

/* --------------------------------------------------------- profile switch - */
function initProfileSwitch() {
  const select = document.getElementById("profile-switch");
  const nameEl = document.getElementById("active-name");
  const avatar = document.getElementById("active-avatar");

  const paint = () => {
    const state = get();
    const list = state.profiles || [];
    let active = state.activeProfileId;
    clear(select);
    if (!list.length) {
      select.append(el("option", { value: "", text: "No profile yet" }));
      nameEl.textContent = "No profile";
      avatar.textContent = "?";
      return;
    }
    // a stale short id (older build wrote pid[:8]) resolves to the full one
    if (active && !list.some((p) => p.id === active)) {
      const match = list.find((p) => p.id.startsWith(active) || active.startsWith(p.id));
      if (match) setActiveProfile(match.id);
      active = match ? match.id : "";
    }
    for (const p of list) {
      select.append(el("option", { value: p.id, text: p.name, selected: p.id === active }));
    }
    const current = list.find((p) => p.id === active) || list[0];
    if (current.id !== active) setActiveProfile(current.id);
    nameEl.textContent = current.name;
    avatar.textContent = (current.name || "?").trim().charAt(0).toUpperCase();
  };

  select.addEventListener("change", () => setActiveProfile(select.value));
  subscribe(paint);
  paint();
}

/* --------------------------------------------------------------- boot ----- */
function wireTopbar() {
  document.getElementById("btn-theme").addEventListener("click", () => {
    applyTheme(root.dataset.theme === "dark" ? "light" : "dark");
    toast(root.dataset.theme === "dark" ? t("theme.dark") : t("theme.light"), "ok", { timeout: 1400 });
  });

  const nav = document.getElementById("sidenav");
  const app = document.getElementById("app");
  document.getElementById("btn-nav").addEventListener("click", (e) => {
    const btn = e.currentTarget;
    const wide = window.matchMedia("(min-width: 961px)").matches;
    if (wide) {
      app.classList.toggle("nav-collapsed");
      btn.setAttribute("aria-expanded", String(!app.classList.contains("nav-collapsed")));
    } else {
      nav.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", String(nav.classList.contains("is-open")));
    }
  });

  // close the mobile drawer after picking a route
  nav.addEventListener("click", (e) => {
    if (e.target.closest("a") && !window.matchMedia("(min-width: 961px)").matches) {
      nav.classList.remove("is-open");
    }
  });

  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#/"]');
    if (a && a.getAttribute("href") === location.hash) navigate();
  });
}

function wireLiveStatus() {
  const pill = document.getElementById("live-pill");
  const label = document.getElementById("live-label");
  const map = { live: ["is-live", t("live.on")], retry: ["is-retry", t("live.retry")], idle: ["", t("live.connecting")] };
  const paint = (status) => {
    const [cls, text] = map[status] || map.idle;
    pill.className = `live ${cls}`;
    label.textContent = text;
    set({ online: status === "live" }, "net");
  };
  sse.on("status", paint);
  sse.connect();
  paint(sse.status);
}

/** Turn every live event into a human activity line + store update. */
function wireLiveEvents() {
  sse.on("state_changed", (payload) => {
    const snap = payload?.snapshot;
    if (snap) {
      set({ snapshot: snap }, "state");
      if (snap.profiles) set({ profiles: expandProfileIds(snap.profiles) }, "state");
    }
  });

  sse.on("settings_changed", () => {
    api.aiStatus().then((r) => set({ ai: r.ai || r }, "ai")).catch(() => {});
  });

  sse.on("progress", (evt) => {
    applyProgress(evt);
    const text = progressLine(evt);
    if (text) pushActivity({ kind: evt.status === "failed" ? "bad" : "run", text, at: new Date().toISOString() });
  });

  sse.on("task_done", (evt) => {
    const ok = evt?.result?.ok !== false;
    const text = taskLine(evt);
    pushActivity({ kind: ok ? "ok" : "bad", text, at: new Date().toISOString() });
    // one-shot jobs are done: drop their stage map shortly after the toast
    if (evt?.job_id && evt.kind !== "agent") {
      setTimeout(() => store.clearProgress(evt.job_id), 60000);
    }
  });
}

function progressLine(evt) {
  const label = evt.label || evt.stage || evt.kind;
  const detail = evt.detail ? ` — ${esc(evt.detail)}` : "";
  return `<b>${esc(label)}</b>${detail}`;
}

function taskLine(evt) {
  const r = evt?.result || {};
  const kind = evt.kind || "task";
  if (kind === "discover") {
    return r.ok === false
      ? `<b>Discovery failed</b> — ${esc(r.error || "unknown error")}`
      : `<b>Discovery</b> — ${r.stored ?? 0} new, ${r.duplicates ?? 0} duplicates skipped`;
  }
  if (kind === "resume") {
    return r.ok
      ? `<b>Resume import</b> — ${r.facts_created ?? 0} facts, version ${r.version ?? "?"}`
      : `<b>Resume import failed</b> — ${esc(r.error_reason || "unknown")}`;
  }
  if (kind === "agent") {
    const s = r.summary || {};
    return r.ok === false
      ? `<b>Agent run failed</b> — ${esc(r.error || "unknown")}`
      : `<b>Agent run</b> — ${s.admitted ?? 0} admitted, ${s.recorded ?? 0} recorded, ${s.blocked ?? 0} blocked`;
  }
  if (kind === "match") return `<b>Scoring complete</b> — ${r.count ?? 0} jobs ranked`;
  return `<b>${esc(kind)}</b> finished`;
}

async function bootstrap() {
  wireTopbar();
  initSearch();
  initActivity();
  initProfileSwitch();
  wireLiveStatus();
  wireLiveEvents();
  applyI18n(document);
  document.documentElement.lang = lang();

  // initial data — two cheap GETs, then SSE keeps everything fresh
  try {
    const [meta, state, profiles, ai] = await Promise.allSettled([
      api.meta(),
      api.state(),
      api.profiles(),
      api.aiStatus(),
    ]);
    if (meta.status === "fulfilled") set({ meta: meta.value }, "boot");
    if (state.status === "fulfilled") set({ snapshot: state.value.snapshot }, "boot");
    if (profiles.status === "fulfilled") set({ profiles: profiles.value.profiles || [] }, "boot");
    if (ai.status === "fulfilled") set({ ai: ai.value.ai || ai.value }, "boot");
  } catch (err) {
    console.error("[boot]", err);
  }

  document.getElementById("app").removeAttribute("aria-busy");
  if (!location.hash) location.replace("#/dashboard");
  await navigate();
}

subscribe((state, reason) => {
  if (reason !== "state" && reason !== "boot") return;
  const kpis = document.querySelectorAll("[data-kpi]");
  for (const node of kpis) {
    const path = node.dataset.kpi;
    const val = path.split(".").reduce((o, k) => (o == null ? o : o[k]), state.snapshot);
    if (typeof val === "number") countUp(node, val);
  }
});

bootstrap();

export { navigate, toast, t };
