/* dashboard.js — KPIs, pipeline health, quick actions, platform policy. */

import api from "../core/api.js";
import store, { get, set, subscribe, pushActivity } from "../core/store.js";
import t from "../core/i18n.js";
import {
  el,
  clear,
  toast,
  esc,
  ICONS,
  timeAgo,
  statusTag,
  countUp,
  emptyState,
  busy,
} from "../core/ui.js";

const PIPELINE = [
  ["discovered", "Discovered", "info"],
  ["ready", "Ready", "accent"],
  ["drafted", "Drafted", "accent"],
  ["review", "Needs review", "warn"],
  ["submitted", "Submitted", "ok"],
  ["closed", "Closed", ""],
];

function kpi(label, value, hint, kind = "") {
  const node = el(`div.kpi${kind ? `.kpi--${kind}` : ""}`);
  node.append(el("div.kpi__label", { text: label }));
  const v = el("div.kpi__value", { text: "0", "data-kpi-value": "1" });
  node.append(v);
  if (hint) node.append(el("div.kpi__hint", { text: hint }));
  return { node, value: v };
}

function pipelineBar() {
  const wrap = el("div.grid.grid--3.stagger");
  for (const [key, label, kind] of PIPELINE) {
    const box = el("div.card.card__body.card__body--tight");
    const count = el("div", { style: { fontSize: "24px", fontWeight: "700", lineHeight: "1.2" } });
    count.dataset.pipe = key;
    count.textContent = "0";
    box.append(el("div.kpi__label", { text: label }), count);
    if (kind) box.classList.add(`kpi--${kind}`);
    wrap.append(box);
  }
  return wrap;
}

function renderPipelineInto(root, counts) {
  for (const node of root.querySelectorAll("[data-pipe]")) {
    const to = counts?.[node.dataset.pipe] ?? 0;
    countUp(node, to);
  }
}

async function quickAction(btn, fn, doneMsg) {
  const done = busy(btn);
  try {
    const res = await fn();
    if (doneMsg) toast(doneMsg, "ok");
    return res;
  } catch (err) {
    toast(err.message || t("err.unknown"), "bad");
    return null;
  } finally {
    done();
  }
}

export async function render() {
  const page = el("div.page");
  const state = get();
  const snap = state.snapshot || { counts: {}, pipeline_counts: {}, kanban: [] };
  const profileId = state.activeProfileId;

  /* ---------------------------------------------------------- page head -- */
  const head = el("div.page-head");
  const headText = el("div.page-head__text");
  headText.append(
    el("h1", { text: t("dashboard.title") }),
    el("p", { text: t("dashboard.sub") }),
  );
  const actions = el("div.page-head__actions");
  const btnDiscover = el("button.btn.btn--primary", {
    html: `<span class="spinner"></span>${ICONS.refresh}<span>${esc(t("jobs.discover"))}</span>`,
    onclick: (e) =>
      quickAction(e.currentTarget, () => api.discover(30), "Discovery started — watch the activity log"),
  });
  const btnRun = el("button.btn", {
    html: `<span class="spinner"></span>${ICONS.play}<span>${esc(t("pipeline.run"))}</span>`,
    onclick: async (e) => {
      if (!profileId) return toast(t("profile.empty"), "warn");
      await quickAction(
        e.currentTarget,
        () => api.agentRun(profileId, 10),
        "Agent run started — assisted flow, nothing auto-submits",
      );
    },
  });
  actions.append(btnDiscover, btnRun, el("a.btn.btn--ghost", { href: "#/resume", text: t("resume.title") }));
  head.append(headText, actions);
  page.append(head);

  /* --------------------------------------------------------------- KPIs -- */
  const kpis = el("div.grid.grid--4.stagger");
  const c = snap.counts || {};
  const tiles = [
    kpi(t("dashboard.kpi.applications"), c.applications ?? 0, `${c.jobs ?? 0} jobs discovered`, "accent"),
    kpi(t("dashboard.kpi.review"), snap.pipeline_counts?.review ?? 0, "awaiting your decision", "warn"),
    kpi(t("dashboard.kpi.submitted"), snap.pipeline_counts?.submitted ?? 0, "with evidence", "ok"),
    kpi(
      t("dashboard.kpi.facts"),
      c.facts_confirmed ?? 0,
      `${c.facts ?? 0} total · ${c.facts - (c.facts_confirmed ?? 0)} unconfirmed`,
    ),
  ];
  for (const tile of tiles) kpis.append(tile.node);
  page.append(kpis);

  /* ------------------------------------------------------- pipeline bar -- */
  const pipeCard = el("div.card");
  pipeCard.append(
    el("div.card__head", {}, [
      el("div", {}, [el("h2", { text: t("dashboard.pipeline") })]),
      el("a.small", { href: "#/applications", text: t("nav.pipeline") + " →" }),
    ]),
  );
  const pipeBody = el("div.card__body");
  const pipe = pipelineBar();
  pipeBody.append(pipe);
  pipeCard.append(pipeBody);
  page.append(pipeCard);

  /* --------------------------------------------------- recent activity --- */
  const recent = el("div.grid.grid--2");
  const recentCard = el("div.card");
  recentCard.append(
    el("div.card__head", {}, [
      el("h2", { text: t("dashboard.recent") }),
      el("span.sub", { text: `${snap.kanban?.length ?? 0} total` }),
    ]),
  );
  const recentBody = el("div.card__body.card__body--tight");
  if (!snap.kanban?.length) {
    recentBody.append(
      emptyState({
        icon: ICONS.file,
        title: t("dashboard.empty"),
        body: t("dashboard.emptyBody"),
        action: el("a.btn.btn--primary", { href: "#/resume", text: t("resume.title") }),
      }),
    );
  } else {
    const list = el("div.stack");
    list.style.gap = "2px";
    for (const a of [...snap.kanban]
      .sort((x, y) => String(y.updated_at).localeCompare(String(x.updated_at)))
      .slice(0, 7)) {
      const row = el("div.row", {
        style: { padding: "8px 4px", borderBottom: "1px solid var(--line)" },
      });
      const txt = el("div", { style: { minWidth: "0", flex: "1 1 auto" } });
      txt.append(
        el("div", { text: a.title, style: { fontWeight: "650", fontSize: "13px" } }),
        el("div", { text: a.company, class: "muted small" }),
      );
      row.append(txt, statusTag(a.status), el("span.faint.small", { text: timeAgo(a.updated_at) }));
      list.append(row);
    }
    recentBody.append(list);
  }
  recentCard.append(recentBody);

  /* ---------------------------------------------------------- policies ---- */
  const polCard = el("div.card");
  polCard.append(
    el("div.card__head", {}, [
      el("h2", { text: t("dashboard.policies") }),
      el("span.sub", { text: "assisted by default" }),
    ]),
  );
  const polBody = el("div.card__body");
  const meta = state.meta;
  if (!meta?.policies?.length) {
    polBody.append(el("p.muted.small", { text: "Policy register loads with /api/meta." }));
  } else {
    for (const p of meta.policies.slice(0, 5)) {
      const row = el("div.row", { style: { padding: "7px 0", borderBottom: "1px solid var(--line)" } });
      const txt = el("div", { style: { flex: "1 1 auto", minWidth: "0" } });
      txt.append(el("strong", { text: p.name, style: { fontSize: "13px" } }));
      txt.append(el("div.faint.small", { text: p.note }));
      row.append(
        txt,
        el(`span.tag.${p.can_automate ? "tag--info" : "tag--warn"}`, {
          text: String(p.status).replace(/_/g, " "),
        }),
      );
      polBody.append(row);
    }
    polBody.append(
      el("div.notice", {
        style: { marginTop: "12px" },
        html: `${ICONS.info}<span>No_Loop never bypasses a platform policy. Automation runs where
        permitted; everywhere else you get an assisted, fill-only flow and you click Submit.</span>`,
      }),
    );
  }
  polCard.append(polBody);
  recent.append(recentCard, polCard);
  page.append(recent);

  /* --------------------------------------------------------- live wiring -- */
  const unsub = subscribe((s, reason) => {
    if (reason === "state" || reason === "boot") {
      renderPipelineInto(pipe, s.snapshot?.pipeline_counts);
      const tileVals = [
        [tiles[0].value, s.snapshot?.counts?.applications ?? 0],
        [tiles[1].value, s.snapshot?.pipeline_counts?.review ?? 0],
        [tiles[2].value, s.snapshot?.pipeline_counts?.submitted ?? 0],
        [tiles[3].value, s.snapshot?.counts?.facts_confirmed ?? 0],
      ];
      for (const [node, val] of tileVals) countUp(node, val);
      const sub = recentCard.querySelector(".card__head .sub");
      if (sub) sub.textContent = `${s.snapshot?.kanban?.length ?? 0} total`;
    }
  });

  // paint once with whatever we have, then refresh from the server
  renderPipelineInto(pipe, snap.pipeline_counts);
  for (const [node, val] of [
    [tiles[0].value, c.applications ?? 0],
    [tiles[1].value, snap.pipeline_counts?.review ?? 0],
    [tiles[2].value, snap.pipeline_counts?.submitted ?? 0],
    [tiles[3].value, c.facts_confirmed ?? 0],
  ]) {
    countUp(node, val);
  }

  api
    .state()
    .then((r) => set({ snapshot: r.snapshot }, "state"))
    .catch(() => {});

  page.addEventListener("route:leave", unsub, { once: true });
  return page;
}

export default { render };
