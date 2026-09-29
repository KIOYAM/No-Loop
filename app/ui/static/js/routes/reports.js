/* reports.js — pick a report, preview it, download CSV / JSON / HTML. */

import api from "../core/api.js";
import { get } from "../core/store.js";
import t from "../core/i18n.js";
import { el, clear, toast, esc, ICONS, busy, emptyState } from "../core/ui.js";

const KIND_LABEL = {
  applications: "reports.applications",
  companies: "reports.companies",
  runs: "reports.runs",
  facts: "reports.facts",
  summary: "reports.summary",
};

function statCard(label, value, hint = "") {
  const node = el("div.kpi");
  node.append(el("div.kpi__label", { text: label }));
  const v = el("div.kpi__value", { text: String(value) });
  node.append(v);
  if (hint) node.append(el("div.kpi__hint", { text: hint }));
  return node;
}

export async function render() {
  const page = el("div.page");
  const state = get();
  const profileId = state.activeProfileId;
  const meta = state.meta;
  const kinds = meta?.reports?.kinds?.length ? meta.reports.kinds : ["applications", "companies", "runs", "facts", "summary"];
  const formats = meta?.reports?.formats?.length ? meta.reports.formats : ["csv", "json", "html"];

  /* ------------------------------------------------------------- heading - */
  const head = el("div.page-head");
  const ht = el("div.page-head__text");
  ht.append(el("h1", { text: t("reports.title") }), el("p", { text: t("reports.sub") }));
  const actions = el("div.page-head__actions");

  const kindSel = el("select.select", { style: { width: "auto" }, "aria-label": t("reports.kind") });
  for (const k of kinds) {
    kindSel.append(el("option", { value: k, text: t(KIND_LABEL[k] || k) }));
  }
  const fmtSel = el("select.select", { style: { width: "auto" }, "aria-label": t("reports.format") });
  for (const f of formats) fmtSel.append(el("option", { value: f, text: f.toUpperCase() }));

  const downloadBtn = el("a.btn.btn--primary", {
    html: `${ICONS.down}<span>${esc(t("reports.download"))}</span>`,
    href: api.reportDownloadUrl({ report: "applications", format: "csv", profileId }),
    download: "",
  });
  const refreshBtn = el("button.btn.btn--ghost", {
    html: `${ICONS.refresh}<span>${esc(t("reports.preview"))}</span>`,
  });

  const syncDownload = () => {
    downloadBtn.href = api.reportDownloadUrl({
      report: kindSel.value,
      format: fmtSel.value,
      profileId,
    });
    downloadBtn.setAttribute("download", `noloop-${kindSel.value}.${fmtSel.value}`);
  };
  kindSel.addEventListener("change", () => {
    syncDownload();
    loadPreview();
  });
  fmtSel.addEventListener("change", syncDownload);

  actions.append(kindSel, fmtSel, refreshBtn, downloadBtn);
  head.append(ht, actions);
  page.append(head);

  /* -------------------------------------------------------------- summary - */
  const summaryGrid = el("div.grid.grid--4.stagger");
  summaryGrid.append(el("div.skel.skel--card"));
  summaryGrid.append(el("div.skel.skel--card"));
  summaryGrid.append(el("div.skel.skel--card"));
  summaryGrid.append(el("div.skel.skel--card"));
  page.append(summaryGrid);

  /* -------------------------------------------------------------- preview - */
  const previewCard = el("div.card", { style: { marginTop: "16px" } });
  const previewHead = el("div.card__head");
  const previewMeta = el("span.sub", { id: "preview-meta", text: "" });
  previewHead.append(
    el("h2", { text: t("reports.preview") }),
    previewMeta,
  );
  const previewBody = el("div.card__body", { id: "preview-body" });
  previewCard.append(previewHead, previewBody);
  page.append(previewCard);

  async function loadSummary() {
    try {
      const r = await api.reportSummary(profileId);
      const s = r.summary || {};
      clear(summaryGrid).append(
        statCard(t("reports.applications"), s.total_applications ?? 0, `${s.distinct_companies ?? 0} companies`),
        statCard(t("reports.submitted") || "Submitted", s.submitted ?? 0, `${s.interviews ?? 0} interviews · ${s.offers ?? 0} offers`),
        statCard(t("pipeline.history"), s.agent_runs ?? 0, `${s.agent_steps ?? 0} steps logged`),
        statCard("Facts", `${s.facts_confirmed ?? 0}/${s.facts_total ?? 0}`, "confirmed / total"),
      );
    } catch (err) {
      clear(summaryGrid).append(el("div.notice.notice--bad", { html: `${ICONS.alert}<span>${esc(err.message)}</span>` }));
    }
  }

  async function loadPreview() {
    clear(previewBody).append(el("div.skel.skel--line"), el("div.skel.skel--line"), el("div.skel.skel--line"));
    try {
      const r = await api.reportPreview({ report: kindSel.value, profileId, format: fmtSel.value });
      clear(previewBody);
      previewMeta.textContent = `${r.rows.length} ${t("reports.rows")} · ${r.columns.length} columns`;
      if (!r.rows.length) {
        previewBody.append(emptyState({ icon: ICONS.file, title: t("reports.empty"), body: "" }));
        return;
      }
      const wrap = el("div.table-wrap");
      const table = el("table.data");
      const thead = el("thead");
      const trh = el("tr");
      for (const c of r.columns) trh.append(el("th", { text: String(c).replace(/_/g, " ") }));
      thead.append(trh);
      const tbody = el("tbody");
      for (const row of r.rows) {
        const tr = el("tr");
        for (const c of r.columns) {
          const raw = row[c];
          const text =
            raw == null
              ? ""
              : typeof raw === "object"
                ? JSON.stringify(raw)
                : String(raw);
          tr.append(
            el("td", {
              text: text.length > 140 ? `${text.slice(0, 140)}…` : text,
              class: typeof raw === "number" ? "num" : "",
            }),
          );
        }
        tbody.append(tr);
      }
      table.append(thead, tbody);
      wrap.append(table);
      previewBody.append(wrap);
      if (r.rows.length >= 200) {
        previewBody.append(
          el("p.faint.small", {
            text: "Preview capped at 200 rows — the download contains every row.",
            style: { marginTop: "10px" },
          }),
        );
      }
    } catch (err) {
      clear(previewBody).append(el("div.notice.notice--bad", { html: `${ICONS.alert}<span>${esc(err.message)}</span>` }));
    }
  }

  refreshBtn.addEventListener("click", (e) => {
    const done = busy(refreshBtn);
    Promise.all([loadSummary(), loadPreview()]).finally(done);
    e.preventDefault();
  });

  syncDownload();
  await Promise.all([loadSummary(), loadPreview()]);
  return page;
}

export default { render };
