/* ui.js — DOM helpers: element factory, toast, modal, skeleton, count-up. */

export const ICONS = {
  check: '<svg viewBox="0 0 20 20"><path d="m4 10.5 4 4 8-9"/></svg>',
  alert: '<svg viewBox="0 0 20 20"><path d="M10 2.5 18 17H2Z"/><path d="M10 8v4M10 14.5v.01"/></svg>',
  info: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8"/><path d="M10 9v5M10 6.5v.01"/></svg>',
  x: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5 5 15"/></svg>',
  clock: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8"/><path d="M10 5.5V10l3 2"/></svg>',
  play: '<svg viewBox="0 0 20 20"><path d="M6 4l10 6-10 6Z"/></svg>',
  spark: '<svg viewBox="0 0 20 20"><path d="M10 2.5 11.8 8 17.5 10 11.8 12 10 17.5 8.2 12 2.5 10 8.2 8Z"/></svg>',
  file: '<svg viewBox="0 0 20 20"><path d="M11 2H5.5A1.5 1.5 0 0 0 4 3.5v13A1.5 1.5 0 0 0 5.5 18h9a1.5 1.5 0 0 0 1.5-1.5V7Z"/><path d="M11 2v5h5"/></svg>',
  down: '<svg viewBox="0 0 20 20"><path d="M10 3v10M6 9.5l4 4 4-4M4 17h12"/></svg>',
  refresh: '<svg viewBox="0 0 20 20"><path d="M17 10a7 7 0 1 1-2.1-5"/><path d="M17 3v4h-4"/></svg>',
  plus: '<svg viewBox="0 0 20 20"><path d="M10 4v12M4 10h12"/></svg>',
  dot: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="4"/></svg>',
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export { esc, esc as escapeHtml };

/** el("div.card#id", {attrs}, [children|string]) — tag, then any #id and .classes. */
export function el(spec, attrs = {}, children = []) {
  const src = String(spec);
  const id = (src.match(/#([\w-]+)/) || [])[1] || null;
  const classes = [...src.matchAll(/\.([\w-]+)/g)].map((m) => m[1]);
  const tag = (src.split(/[#.]/)[0] || "div").trim() || "div";
  const node = document.createElement(tag);
  if (id) node.id = id;
  if (classes.length) node.className = classes.join(" ");
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, String(v));
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function mount(container, node) {
  clear(container).append(node);
  return node;
}

/* ---------------------------------------------------------------- toast --- */
export function toast(message, kind = "ok", { timeout = 3600 } = {}) {
  const host = document.getElementById("toaster");
  if (!host) return;
  const icon = kind === "ok" ? ICONS.check : kind === "bad" ? ICONS.alert : ICONS.info;
  const node = el("div.toast", { class: `toast toast--${kind}`, role: "status" });
  node.innerHTML = `${icon}<span>${esc(message)}</span>`;
  const close = el("button.icon-btn.toast__close", {
    "aria-label": "Dismiss",
    html: ICONS.x,
    onclick: () => dismiss(),
  });
  node.append(close);
  host.append(node);
  let timer = setTimeout(dismiss, timeout);
  function dismiss() {
    clearTimeout(timer);
    node.style.animation = "toast-out var(--t-med) var(--ease) forwards";
    setTimeout(() => node.remove(), 240);
  }
  return dismiss;
}

/* ---------------------------------------------------------------- modal --- */
export function modal({ title, subtitle = "", body, actions = [], width = null }) {
  const dlg = el("dialog.modal");
  if (width) dlg.style.width = `min(${width}px, 94vw)`;
  const head = el("div.modal__head");
  const titles = el("div");
  titles.append(el("h2", { text: title }));
  if (subtitle) titles.append(el("p", { text: subtitle }));
  head.append(titles, el("button.icon-btn", { "aria-label": "Close", html: ICONS.x }));
  const bodyWrap = el("div.modal__body");
  if (body) bodyWrap.append(body.nodeType ? body : el("div", { html: String(body) }));
  const foot = el("div.modal__foot");
  for (const a of actions) foot.append(a.nodeType ? a : el("button.btn", a));
  dlg.append(head, bodyWrap, foot);
  head.querySelector("button").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg) dlg.close(); // backdrop click
  });
  document.body.append(dlg);
  dlg.addEventListener("close", () => dlg.remove(), { once: true });
  dlg.showModal();
  return dlg;
}

export function confirmDialog(title, message, { confirmLabel = "Confirm", danger = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const dlg = modal({
      title,
      body: el("p", { text: message, class: "muted" }),
      actions: [
        el("button.btn", {
          text: "Cancel",
          onclick: () => {
            done = true;
            dlg.close();
            resolve(false);
          },
        }),
        el(`button.btn.${danger ? "btn--danger" : "btn--primary"}`, {
          text: confirmLabel,
          onclick: () => {
            done = true;
            dlg.close();
            resolve(true);
          },
        }),
      ],
    });
    dlg.addEventListener("close", () => {
      if (!done) resolve(false);
    });
  });
}

/* ------------------------------------------------------------- busy state - */
export function busy(button, label = null) {
  const original = button.innerHTML;
  button.classList.add("is-busy");
  button.setAttribute("aria-busy", "true");
  button.innerHTML = `<span class="spinner"></span>${label ? `<span>${esc(label)}</span>` : ""}`;
  return () => {
    button.classList.remove("is-busy");
    button.removeAttribute("aria-busy");
    button.innerHTML = original;
  };
}

/* ------------------------------------------------------------- count-up --- */
export function countUp(node, to, { duration = 620, decimals = 0 } = {}) {
  const from = Number(node.dataset.value || 0);
  node.dataset.value = String(to);
  if (from === to) {
    node.textContent = to.toFixed(decimals);
    return;
  }
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    node.textContent = to.toFixed(decimals);
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    node.textContent = (from + (to - from) * eased).toFixed(decimals);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* --------------------------------------------------------------- format --- */
export function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const s = Math.round((Date.now() - then) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.round(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function bytes(n) {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export function salary(job) {
  if (!job || (job.salary_min == null && job.salary_max == null)) return null;
  const cur = job.salary_currency || "";
  const fmt = (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v));
  if (job.salary_min != null && job.salary_max != null) {
    return `${cur} ${fmt(job.salary_min)}–${fmt(job.salary_max)}`;
  }
  const v = job.salary_min ?? job.salary_max;
  return `${job.salary_min != null ? "≥" : "≤"} ${cur} ${fmt(v)}`;
}

/* -------------------------------------------------------------- skeleton -- */
export function skeletonBlock(lines = 3) {
  const wrap = el("div");
  for (let i = 0; i < lines; i += 1) wrap.append(el("div.skel.skel--line"));
  return wrap;
}

export function skeletonCards(n = 3) {
  const wrap = el("div.skel-grid");
  for (let i = 0; i < n; i += 1) wrap.append(el("div.skel.skel--card"));
  return wrap;
}

export function emptyState({ icon = ICONS.file, title, body, action = null }) {
  const wrap = el("div.empty-state");
  wrap.append(el("div.ico", { html: icon }));
  wrap.append(el("h3", { text: title }));
  if (body) wrap.append(el("p", { text: body }));
  if (action) wrap.append(action.nodeType ? action : el("button.btn.btn--primary", action));
  return wrap;
}

/** Render a named status badge using the project's status vocabulary. */
export function statusTag(status) {
  const map = {
    discovered: ["info", "Discovered"],
    shortlisted: ["info", "Shortlisted"],
    ready: ["accent", "Ready"],
    drafted: ["accent", "Drafted"],
    review_required: ["warn", "Review"],
    verification_required: ["warn", "Verify"],
    failed: ["bad", "Failed"],
    submitted: ["ok", "Submitted"],
    interview: ["gold", "Interview"],
    offer: ["ok", "Offer"],
    closed: ["", "Closed"],
    rejected: ["bad", "Rejected"],
    withdrawn: ["", "Withdrawn"],
  };
  const [kind, label] = map[status] || ["", status];
  return el(`span.tag${kind ? `.tag--${kind}` : ""}`, { text: label });
}

export function methodTag(method) {
  const kind = method === "auto" ? "auto" : method === "assisted" ? "assisted" : "manual";
  return el(`span.tag.tag--${kind}`, { text: method || "manual" });
}
