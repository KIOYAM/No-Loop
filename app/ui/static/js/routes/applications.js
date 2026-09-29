/* applications.js — kanban board + live assisted-agent run. */

import api from "../core/api.js";
import store, { get, set, subscribe, pushActivity } from "../core/store.js";
import t from "../core/i18n.js";
import {
  el,
  clear,
  toast,
  esc,
  ICONS,
  busy,
  modal,
  emptyState,
  statusTag,
  methodTag,
  timeAgo,
} from "../core/ui.js";

const COLUMNS = [
  ["discovered", "Discovered"],
  ["shortlisted", "Shortlisted"],
  ["ready", "Ready"],
  ["drafted", "Drafted"],
  ["review_required", "Review"],
  ["submitted", "Submitted"],
  ["interview", "Interview"],
  ["offer", "Offer"],
  ["closed", "Closed"],
];

function card(a) {
  const node = el("div.kcard", {
    draggable: "true",
    dataset: { id: a.full_id || a.id, status: a.status },
  });
  node.append(
    el("div.kcard__title", { text: a.title }),
    el("div.kcard__company", { text: a.company }),
  );
  const meta = el("div.kcard__meta");
  meta.append(methodTag(a.entry_method));
  if (a.artifacts) meta.append(el("span.tag", { text: `${a.artifacts} artifacts` }));
  const pkgBtn = el("button.icon-btn", {
    "aria-label": "View assisted package",
    html: ICONS.file,
    title: "View assisted package",
  });
  pkgBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    openPackageViewer(a);
  });
  meta.append(pkgBtn);
  if (a.url) {
    meta.append(
      el("a.faint.small", { href: a.url, target: "_blank", rel: "noopener noreferrer", text: "↗" }),
    );
  }
  node.append(meta);
  if (a.failed_reason) {
    node.append(el("div.kcard__why", { text: a.failed_reason, class: "kcard__why warn" }));
  }
  return node;
}

function paintBoard(board, apps, columns) {
  clear(board);
  const byStatus = {};
  for (const a of apps) (byStatus[a.status] ||= []).push(a);

  for (const [key, label] of columns) {
    const col = el("div.column", { dataset: { status: key } });
    const rows = byStatus[key] || [];
    const head = el("div.column__head");
    head.append(el("h3", { text: label }), el("span.column__count", { text: String(rows.length) }));
    const cards = el("div.column__cards");
    for (const a of rows) cards.append(card(a));
    if (!rows.length) cards.append(el("div.faint.small", { text: "—", style: { textAlign: "center", padding: "14px 0" } }));
    col.append(head, cards);

    col.addEventListener("dragover", (e) => {
      e.preventDefault();
      col.classList.add("is-over");
    });
    col.addEventListener("dragleave", () => col.classList.remove("is-over"));
    col.addEventListener("drop", async (e) => {
      e.preventDefault();
      col.classList.remove("is-over");
      const id = e.dataTransfer.getData("text/plain");
      if (!id || key === byStatusOf(id, apps)) return;
      try {
        await api.moveCard(id, key);
        toast(`Moved to ${label}`, "ok");
      } catch (err) {
        toast(err.message || "Move rejected by policy", "bad");
      }
    });
    board.append(col);
  }
}

function byStatusOf(id, apps) {
  const a = apps.find((x) => (x.full_id || x.id) === id);
  return a?.status;
}

function wireDrag(board) {
  board.addEventListener("dragstart", (e) => {
    const c = e.target.closest(".kcard");
    if (!c) return;
    c.classList.add("is-dragging");
    e.dataTransfer.setData("text/plain", c.dataset.id);
    e.dataTransfer.effectAllowed = "move";
  });
  board.addEventListener("dragend", (e) => {
    e.target.closest(".kcard")?.classList.remove("is-dragging");
  });
}


/* ---------------------------------------------------- assisted package ---- */
async function openPackageViewer(app) {
  let pkg = null;
  try {
    const res = await api.assistedPackages(app.full_id || app.id);
    pkg = (res.packages || [])[0] || null;
  } catch (err) {
    toast(err.message || "Could not load the package", "bad");
    return;
  }
  const body = el("div");
  if (!pkg) {
    body.append(
      el("div.notice", {
        html: `${ICONS.info}<span>No assisted package for this application yet. Run the agent from the Agent tab.</span>`,
      }),
    );
  } else {
    const statusLabel = {
      assisted_only: "Assisted — you submit",
      user_account_required: "Assisted — you submit (fill-only allowed)",
      allowed: "Automation permitted",
    }[pkg.policy_status] || pkg.policy_status;
    body.append(
      el("p.muted", {
        html: `<b>${esc(pkg.job_title || app.title)}</b> @ ${esc(pkg.company || app.company)} · ${esc(pkg.platform || "")} · <b>${esc(statusLabel)}</b>`,
      }),
    );
    /* steps checklist */
    if (Array.isArray(pkg.steps) && pkg.steps.length) {
      const steps = el("ol", { style: { margin: "8px 0 12px 18px", fontSize: "12.5px" } });
      for (const s of pkg.steps) steps.append(el("li", { text: s }));
      body.append(el("h3", { text: "Steps", style: { margin: "10px 0 4px", fontSize: "13px" } }), steps);
    }
    /* ready answers with copy buttons */
    const ready = pkg.answers_ready || [];
    const need = pkg.answers_needing_user || [];
    if (ready.length || need.length) {
      body.append(el("h3", { text: "Answers", style: { margin: "10px 0 4px", fontSize: "13px" } }));
    }
    for (const a of ready) {
      const row = el("div.field", { style: { marginBottom: "8px" } });
      const copy = el("button.icon-btn", { html: ICONS.file, title: "Copy answer" });
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(a.answer || "");
          toast(t("shell.copied"), "ok");
        } catch {
          toast("Clipboard blocked by the browser", "warn");
        }
      });
      row.append(
        el("div", { style: { display: "flex", justifyContent: "space-between", gap: "8px" } }, [
          el("span.kpi__label", { text: a.question }),
          copy,
        ]),
        el("div", { text: a.answer || "—", style: { fontSize: "12.5px" } }),
        el("div.faint.small", { text: `source: ${a.source || "fact ledger"}${a.reason ? ` — ${a.reason}` : ""}` }),
      );
      body.append(row);
    }
    for (const a of need) {
      const row = el("div.field", { style: { marginBottom: "8px" } });
      row.append(
        el("div", { style: { display: "flex", gap: "6px", alignItems: "center" } }, [
          el("span.tag.tag--warn", { text: "needs you" }),
          el("span.kpi__label", { text: a.question }),
        ]),
        el("div.faint.small", { text: a.reason || "No_Loop will not guess — answer this one yourself." }),
      );
      body.append(row);
    }
    /* email draft */
    if (pkg.email_draft) {
      const pre = el("pre.code", { style: { maxHeight: "180px", overflow: "auto", fontSize: "11.5px", whiteSpace: "pre-wrap" } });
      pre.textContent = pkg.email_draft;
      const copyDraft = el("button.btn", { text: "Copy email draft" });
      copyDraft.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(pkg.email_draft || "");
          toast(t("shell.copied"), "ok");
        } catch {
          toast("Clipboard blocked by the browser", "warn");
        }
      });
      body.append(el("h3", { text: "Email draft", style: { margin: "12px 0 4px", fontSize: "13px" } }), pre, el("div", { style: { marginTop: "8px" } }, [copyDraft]));
    }
    body.append(
      el("div.notice", {
        html: `${ICONS.check}<span>Review everything, open the site yourself, and <b>you</b> click Submit. Then drag this card to <b>Submitted</b> — the ledger records your action as the evidence.</span>`,
      }),
    );
  }
  modal({
    title: "Assisted package",
    subtitle: "Everything prepared for you — review, copy, submit yourself.",
    body,
    width: 620,
    actions: [el("button.btn.btn--primary", { text: t("shell.close") || "Close", onclick: () => dlg.close() })],
  });
  const dlg = document.querySelector("dialog.modal:last-of-type");
}

/* ------------------------------------------------------------- agent run - */
function agentPanel(meta, profileId, onChanged) {
  const agentState = el("span.tag.tag--info", { id: "agent-state", text: "idle" });
  const cardEl = el("div.card");
  cardEl.append(
    el("div.card__head", {}, [
      el("div", {}, [
        el("h2", { text: t("pipeline.agent") }),
        el("div.sub", { text: "assisted flow · ends at Review, never auto-submitted" }),
      ]),
      agentState,
    ]),
  );

  const body = el("div.card__body");
  const controls = el("div.row", { style: { marginBottom: "14px" } });
  const limitInput = el("input.input", {
    type: "number",
    min: "1",
    max: "50",
    value: "10",
    style: { width: "84px" },
    "aria-label": t("pipeline.runLimit"),
  });
  const runBtn = el("button.btn.btn--primary", {
    html: `<span class="spinner"></span>${ICONS.play}<span>${esc(t("pipeline.run"))}</span>`,
  });
  controls.append(el("span.muted.small", { text: t("pipeline.runLimit") }), limitInput, runBtn);

  const blocked = el("div.notice.notice--warn", {
    style: { display: profileId ? "none" : "flex", marginBottom: "12px" },
    html: `${ICONS.alert}<span><strong>${esc(t("pipeline.blocked"))}</strong>
      ${esc(t("pipeline.blockedBody"))}</span>`,
  });

  const bar = el("div.progress", { style: { marginBottom: "14px", display: "none" } }, [el("i", { id: "agent-bar" })]);

  const steps = el("div.stages", { id: "agent-steps" });
  const stepIndex = new Map();
  for (const step of meta?.run_steps || []) {
    const id = step.id ?? step[0];
    const label = step.label ?? step[1] ?? id;
    const node = el("div.stage", { dataset: { stage: id } });
    node.append(el("span.stage__dot", { html: "<span>•</span>" }));
    const text = el("div.stage__text");
    text.append(el("div.stage__label", { text: label }), el("div.stage__detail", { text: "" }));
    node.append(text, el("span.stage__meta", { text: "" }));
    steps.append(node);
    stepIndex.set(id, node);
  }

  const resultBox = el("div", { id: "agent-result", style: { display: "none", marginTop: "12px" } });

  body.append(blocked, controls, bar, steps, resultBox);
  cardEl.append(body);

  const paintStep = (evt) => {
    const node = stepIndex.get(evt.step);
    if (!node) return;
    for (const n of stepIndex.values()) if (n.classList.contains("is-active")) n.classList.remove("is-active");
    node.classList.remove("is-done", "is-failed", "is-skipped");
    const cls =
      evt.status === "done"
        ? "is-done"
        : evt.status === "failed"
          ? "is-failed"
          : evt.status === "skipped"
            ? "is-skipped"
            : "is-active";
    if (cls === "is-active") for (const n of stepIndex.values()) n.classList.remove("is-active");
    node.classList.add(cls);
    node.querySelector(".stage__detail").textContent =
      `${evt.company ? `${evt.company} · ` : ""}${evt.detail || ""}`;
    node.querySelector(".stage__dot").innerHTML =
      evt.status === "done"
        ? ICONS.check
        : evt.status === "failed"
          ? ICONS.x
          : evt.status === "skipped"
            ? "–"
            : '<span class="spinner" style="width:11px;height:11px;border-width:1.5px"></span>';
    if (evt.total) {
      node.querySelector(".stage__meta").textContent = `${evt.index}/${evt.total}`;
      bar.style.display = "block";
      bar.querySelector("i").style.width = `${Math.round((evt.index / evt.total) * 100)}%`;
      agentState.textContent = `running ${evt.index}/${evt.total}`;
    }
  };

  runBtn.addEventListener("click", async () => {
    if (!profileId) return toast(t("profile.empty"), "warn");
    const done = busy(runBtn, t("pipeline.running"));
    try {
      await api.agentRun(profileId, Number(limitInput.value) || 10);
      for (const n of stepIndex.values()) {
        n.classList.remove("is-done", "is-failed", "is-skipped", "is-active");
        n.querySelector(".stage__dot").innerHTML = "<span>•</span>";
        n.querySelector(".stage__detail").textContent = "";
        n.querySelector(".stage__meta").textContent = "";
      }
      resultBox.style.display = "none";
      bar.style.display = "block";
      bar.querySelector("i").style.width = "2%";
      agentState.textContent = "running";
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      done();
    }
  });

  return { node: cardEl, paintStep, onDone: (evt) => {
    const r = evt.result || {};
    const s = r.summary || {};
    clear(resultBox).style.display = "block";
    if (r.ok === false) {
      resultBox.className = "notice notice--bad";
      resultBox.innerHTML = `${ICONS.alert}<span><strong>Run failed</strong> ${esc(r.error || "")}</span>`;
      agentState.textContent = "failed";
      return;
    }
    resultBox.className = "notice notice--ok";
    resultBox.innerHTML = `${ICONS.check}<span><strong>Run complete</strong>
      ${s.admitted ?? 0} admitted · ${s.recorded ?? 0} recorded · ${s.blocked ?? 0} blocked ·
      ${s.skipped ?? 0} duplicates · ${s.failed ?? 0} failed
      <br><span class="faint">every record ends at Review — you make the final call</span></span>`;
    agentState.textContent = "complete";
    bar.querySelector("i").style.width = "100%";
    onChanged();
  }};
}

/* ------------------------------------------------------------- history ---- */
function historyPanel(runs) {
  const cardEl = el("div.card");
  cardEl.append(
    el("div.card__head", {}, [
      el("h2", { text: t("pipeline.history") }),
      el("span.sub", { text: `${runs.length} runs` }),
    ]),
  );
  const body = el("div.card__body");
  if (!runs.length) {
    body.append(emptyState({ icon: ICONS.clock, title: "No runs yet", body: "Run the agent to populate history." }));
    cardEl.append(body);
    return cardEl;
  }
  const table = el("table.data");
  table.innerHTML =
    "<thead><tr><th>Started</th><th>Profile</th><th>Steps</th><th>Admitted</th><th>Recorded</th></tr></thead>";
  const tb = el("tbody");
  // a run stores the full profile id — show the name the user recognises,
  // falling back to a short id only when the profile is gone
  const known = get().profiles || [];
  const profileLabel = (pid) => {
    if (!pid) return "—";
    const found = known.find((p) => p.id === pid || String(p.full_id || "").startsWith(pid));
    return found ? found.name : String(pid).slice(0, 8);
  };
  for (const r of runs.slice(0, 10)) {
    const s = r.summary || {};
    const tr = el("tr");
    tr.append(
      el("td", { html: `<span class="nowrap">${esc(timeAgo(r.started_at))}</span>` }),
      el("td", { text: profileLabel(r.profile_id), title: String(r.profile_id || "") }),
      el("td.num", { text: String((r.steps || []).length) }),
      el("td.num", { text: String(s.admitted ?? 0) }),
      el("td.num", { text: String(s.recorded ?? 0) }),
    );
    tb.append(tr);
  }
  table.append(tb);
  body.append(el("div.table-wrap", {}, [table]));
  cardEl.append(body);
  return cardEl;
}

/* --------------------------------------------------------------- render --- */
export async function render(params) {
  const page = el("div.page");
  const state = get();
  const profileId = state.activeProfileId;
  const meta = state.meta;
  const columns = meta?.columns?.length ? meta.columns.map((c) => [c.id, c.label]) : COLUMNS;

  /* ------------------------------------------------------------- heading - */
  const head = el("div.page-head");
  const ht = el("div.page-head__text");
  ht.append(el("h1", { text: t("pipeline.title") }), el("p", { text: t("pipeline.sub") }));
  const actions = el("div.page-head__actions");
  actions.append(
    el("button.btn", {
      text: t("pipeline.add"),
      onclick: () => openQuickAdd(),
    }),
  );
  head.append(ht, actions);
  page.append(head);

  /* --------------------------------------------------------------- tabs -- */
  const tabs = el("div.tabs", { role: "tablist" });
  const boardPane = el("div", { role: "tabpanel", style: { paddingTop: "16px" } });
  const agentPane = el("div", { role: "tabpanel", style: { paddingTop: "16px", display: "none" } });
  const histPane = el("div", { role: "tabpanel", style: { paddingTop: "16px", display: "none" } });

  const panes = [boardPane, agentPane, histPane];
  const tabDefs = [
    [t("pipeline.board"), boardPane],
    [t("pipeline.agent"), agentPane],
    [t("pipeline.history"), histPane],
  ];
  tabDefs.forEach(([label, pane], i) => {
    const b = el("button", { text: label, class: i === 0 ? "is-active" : "", role: "tab" });
    b.addEventListener("click", () => {
      for (const btn of tabs.children) btn.classList.remove("is-active");
      b.classList.add("is-active");
      panes.forEach((p) => (p.style.display = p === pane ? "block" : "none"));
    });
    tabs.append(b);
  });
  page.append(tabs, boardPane, agentPane, histPane);

  /* -------------------------------------------------------------- board --- */
  const board = el("div.board");
  wireDrag(board);
  const boardScroll = el("div", { style: { overflowX: "auto", paddingBottom: "8px" } }, [board]);
  boardPane.append(boardScroll);

  let apps = [];
  const repaintBoard = () => paintBoard(board, apps, columns);

  /* -------------------------------------------------------------- agent --- */
  const agent = agentPanel(meta, profileId, () => refresh());
  agentPane.append(agent.node);

  /* ------------------------------------------------------------ history --- */
  const histWrap = el("div");
  histPane.append(histWrap);

  /* ------------------------------------------------------------- loading -- */
  const loader = el("div.skel-grid", { style: { marginTop: "16px" } });
  for (let i = 0; i < 3; i += 1) loader.append(el("div.skel.skel--card"));
  boardPane.append(loader);

  async function refresh() {
    try {
      const [ar, rr] = await Promise.all([
        api.applications(profileId),
        api.runs(profileId),
      ]);
      apps = ar.applications || [];
      loader.remove();
      repaintBoard();
      clear(histWrap).append(historyPanel(rr.runs || []));
      if (!apps.length) {
        clear(board).append(
          emptyState({
            icon: ICONS.play,
            title: t("pipeline.empty"),
            body: t("pipeline.emptyBody"),
            action: el("a.btn.btn--primary", { href: "#/jobs", text: t("nav.jobs") }),
          }),
        );
      }
    } catch (err) {
      clear(loader).append(el("p.muted", { text: err.message }));
    }
  }

  /* ------------------------------------------------------- live wiring ----- */
  const { default: sse } = await import("../core/sse.js");
  const offs = [
    sse.on("progress", (evt) => {
      if (evt?.kind === "agent") agent.paintStep(evt);
    }),
    sse.on("task_done", (evt) => {
      if (evt?.kind !== "agent") return;
      agent.onDone(evt);
      refresh();
    }),
    sse.on("state_changed", () => refresh()),
  ];
  page.addEventListener("route:leave", () => offs.forEach((off) => off()), { once: true });

  /* ---------------------------------------------------------- quick add --- */
  function openQuickAdd() {
    const body = el("div");
    const company = el("input.input#qa-company", { placeholder: "Acme Corp", required: true });
    const title = el("input.input#qa-title", { placeholder: "Backend Engineer", required: true });
    const url = el("input.input#qa-url", { type: "url", placeholder: "https://…" });
    const notes = el("textarea.textarea#qa-notes", { rows: "3", placeholder: "Optional context" });
    body.append(
      el("div.form-grid", {}, [
        el("div.field", {}, [el("label", { for: "qa-company", text: "Company" }), company]),
        el("div.field", {}, [el("label", { for: "qa-title", text: "Title" }), title]),
      ]),
      el("div.field", {}, [el("label", { for: "qa-url", text: "Link" }), url]),
      el("div.field", {}, [el("label", { for: "qa-notes", text: "Notes" }), notes]),
      el("div.notice", {
        html: `${ICONS.info}<span>Manual entries are recorded with your assertion as evidence and
        land at <strong>Submitted</strong> — the ledger never fabricates a submission.</span>`,
      }),
    );
    const dlg = modal({
      title: t("pipeline.addTitle"),
      subtitle: t("pipeline.addSub"),
      body,
      actions: [
        el("button.btn", { text: t("shell.cancel"), onclick: () => dlg.close() }),
        el("button.btn.btn--primary", { text: t("shell.create"), onclick: () => submit() }),
      ],
    });
    const submit = async () => {
      const c = company.value.trim();
      const ti = title.value.trim();
      if (!c || !ti) return toast("Company and title are required", "bad");
      if (!profileId) return toast(t("profile.empty"), "warn");
      try {
        await api.quickAdd({
          profile_id: profileId,
          company: c,
          title: ti,
          url: url.value.trim() || null,
          notes: notes.value.trim() || null,
        });
        dlg.close();
        toast("Application recorded", "ok");
        refresh();
      } catch (err) {
        toast(err.message, "bad");
      }
    };
    setTimeout(() => company.focus(), 60);
  }

  await refresh();
  return page;
}

export default { render };
