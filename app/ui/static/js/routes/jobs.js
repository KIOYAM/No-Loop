/* jobs.js — discovered postings, discovery trigger, scoring results. */

import api from "../core/api.js";
import store, { get, set, subscribe } from "../core/store.js";
import t from "../core/i18n.js";
import {
  el,
  clear,
  toast,
  esc,
  ICONS,
  busy,
  emptyState,
  salary,
  timeAgo,
} from "../core/ui.js";

function jobRow(job, score) {
  const row = el("div.card", { style: { marginBottom: "10px" } });
  const body = el("div.card__body.card__body--tight");
  const top = el("div.row");
  const txt = el("div", { style: { flex: "1 1 auto", minWidth: "0" } });
  txt.append(
    el("div", { text: job.title, style: { fontWeight: "650", fontSize: "14px" } }),
    el("div.muted.small", { text: `${job.company} · ${job.location || "unspecified"}` }),
  );
  top.append(txt);

  if (score != null) {
    const pct = Math.round(score * 100);
    const kind = pct >= 75 ? "ok" : pct >= 50 ? "info" : pct >= 30 ? "warn" : "";
    top.append(el(`span.tag${kind ? `.tag--${kind}` : ""}`, { text: `${pct}% fit` }));
  }
  if (job.work_mode && job.work_mode !== "any") {
    top.append(el("span.tag", { text: job.work_mode }));
  }
  if (job.url) {
    top.append(
      el("a.btn.btn--sm.btn--ghost", {
        href: job.url,
        target: "_blank",
        rel: "noopener noreferrer",
        text: "Open ↗",
      }),
    );
  }
  body.append(top);

  if (job.excerpt) {
    body.append(el("p.small.muted", { text: job.excerpt, style: { marginTop: "8px" } }));
  }

  const meta = el("div.row", { style: { marginTop: "9px" } });
  const pay = salary(job);
  if (pay) meta.append(el("span.tag.tag--accent", { text: pay }));
  if (job.posted_at) meta.append(el("span.faint.small", { text: `${t("jobs.posted")} ${timeAgo(job.posted_at)}` }));
  if (job.adapter) meta.append(el("span.tag", { text: job.adapter }));
  body.append(meta);

  row.append(body);
  return row;
}

export async function render(params) {
  const page = el("div.page");
  const state = get();
  const profileId = state.activeProfileId;
  const q = (params.get("q") || "").toLowerCase();

  /* ------------------------------------------------------------ heading -- */
  const head = el("div.page-head");
  const ht = el("div.page-head__text");
  ht.append(el("h1", { text: t("jobs.title") }), el("p", { text: t("jobs.sub") }));
  const actions = el("div.page-head__actions");

  const limitSel = el("select.select", { style: { width: "auto" } });
  for (const n of [20, 30, 60, 120]) {
    limitSel.append(el("option", { value: String(n), text: `${n}`, selected: n === 30 }));
  }

  const discoverBtn = el("button.btn.btn--primary", {
    html: `<span class="spinner"></span>${ICONS.refresh}<span>${esc(t("jobs.discover"))}</span>`,
    onclick: (e) => runDiscover(e.currentTarget),
  });
  const matchBtn = el("button.btn", {
    html: `<span class="spinner"></span>${ICONS.spark}<span>${esc(t("jobs.match"))}</span>`,
    onclick: (e) => runMatch(e.currentTarget),
  });

  actions.append(limitSel, discoverBtn, matchBtn);
  head.append(ht, actions);
  page.append(head);

  /* ---------------------------------------------------------- live status - */
  const liveCard = el("div.card", { id: "jobs-live", style: { display: "none", marginBottom: "16px" } });
  const liveLabel = el("strong", { id: "jobs-live-label", text: "working…" });
  const liveDetail = el("span.faint.small", { id: "jobs-live-detail", text: "" });
  const liveBar = el("i", { id: "jobs-live-bar" });
  liveCard.append(
    el("div.card__body", {}, [
      el("div.row", {}, [el("span.spinner"), liveLabel, liveDetail]),
      el("div.progress", { style: { marginTop: "10px" } }, [liveBar]),
    ]),
  );
  page.append(liveCard);

  /* --------------------------------------------------------------- list --- */
  const listCard = el("div.card");
  const listHead = el("div.card__head");
  const jobsCount = el("span.sub", { id: "jobs-count", text: "" });
  listHead.append(
    el("h2", { text: t("jobs.title") }),
    jobsCount,
  );
  listCard.append(listHead);
  const listBody = el("div.card__body");
  listCard.append(listBody);
  page.append(listCard);

  let matches = {};
  let jobs = [];

  const paint = () => {
    clear(listBody);
    const filtered = q ? jobs.filter((j) => `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)) : jobs;
    if (!filtered.length) {
      listBody.append(
        emptyState({
          icon: ICONS.refresh,
          title: t("jobs.empty"),
          body: t("jobs.emptyBody"),
          action: el("button.btn.btn--primary", {
            html: `<span class="spinner"></span>${ICONS.refresh}<span>${esc(t("jobs.discover"))}</span>`,
            onclick: (e) => runDiscover(e.currentTarget),
          }),
        }),
      );
      return;
    }
    for (const job of filtered) listBody.append(jobRow(job, matches[job.id]?.score));
    jobsCount.textContent =
      `${filtered.length}${q ? ` matching “${params.get("q")}”` : ""} · ${jobs.length} total`;
  };

  const loadData = async () => {
    try {
      const [jr, mr] = await Promise.all([
        api.jobs({ limit: 120 }),
        profileId ? api.matches(profileId) : Promise.resolve({ matches: [] }),
      ]);
      jobs = jr.jobs || [];
      matches = {};
      for (const m of mr.matches || []) matches[m.job_id] = m;
      paint();
    } catch (err) {
      clear(listBody).append(el("p.muted", { text: err.message }));
    }
  };

  /* ------------------------------------------------------- live progress -- */
  const { default: sse } = await import("../core/sse.js");
  const offProgress = sse.on("progress", (evt) => {
    if (evt?.kind !== "discover") return;
    liveCard.style.display = "block";
    liveLabel.textContent = evt.label || "Discovery";
    liveDetail.textContent = evt.detail || "";
    liveBar.style.width = `${evt.progress ?? 10}%`;
  });
  const offDone = sse.on("task_done", (evt) => {
    if (evt?.kind !== "discover") return;
    const r = evt.result || {};
    if (r.ok === false) {
      toast(r.error || "Discovery failed", "bad");
      liveLabel.textContent = "failed";
    } else {
      toast(`${r.stored} new jobs · ${r.duplicates} duplicates skipped`, "ok");
      liveLabel.textContent = "complete";
      liveBar.style.width = "100%";
      loadData();
    }
    setTimeout(() => {
      liveCard.style.display = "none";
    }, 4500);
  });
  const offMatchDone = sse.on("task_done", (evt) => {
    if (evt?.kind !== "match") return;
    toast(`${evt.result?.count ?? 0} jobs scored`, "ok");
    loadData();
  });

  page.addEventListener(
    "route:leave",
    () => {
      offProgress();
      offDone();
      offMatchDone();
    },
    { once: true },
  );

  /* ------------------------------------------------------------ actions --- */
  async function runDiscover(btn) {
    const done = busy(btn, t("jobs.discovering"));
    try {
      await api.discover(Number(limitSel.value));
      liveCard.style.display = "block";
      liveLabel.textContent = "queued";
      liveDetail.textContent = "contacting the feed…";
      liveBar.style.width = "5%";
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      done();
    }
  }

  async function runMatch(btn) {
    if (!profileId) return toast(t("profile.empty"), "warn");
    const done = busy(btn, t("jobs.matching"));
    try {
      await api.match(profileId);
      toast("Scoring started", "ok");
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      done();
    }
  }

  await loadData();
  return page;
}

export default { render };
