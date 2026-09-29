/* resume.js — animated, annotated resume import driven by SSE `progress` events.
 *
 * Flow: pick profile → drop/paste file → POST /api/resume/import returns a
 * job_id instantly → every stage annotation arrives over SSE and lights up the
 * stage list in real time → `task_done` carries the final tally.
 */

import api from "../core/api.js";
import { get, subscribe, clearProgress, pushActivity } from "../core/store.js";
import t from "../core/i18n.js";
import { el, clear, toast, esc, ICONS, busy, emptyState, timeAgo, bytes } from "../core/ui.js";

const MAX_BYTES = 10 * 1024 * 1024;

const STAGE_FALLBACK = [
  ["upload", "Receiving file"],
  ["validate", "Validating"],
  ["dedupe", "Duplicate check"],
  ["detect", "Format detection"],
  ["extract", "Text extraction"],
  ["parse", "Fact extraction"],
  ["persist", "Saving"],
  ["autofill", "Profile autofill"],
  ["ai", "AI enhancement"],
  ["profile", "Updating profile"],
  ["done", "Complete"],
];

function stageList(meta) {
  const rows = meta?.stages?.length ? meta.stages : STAGE_FALLBACK.map(([id, label]) => ({ id, label, detail: "", weight: 0 }));
  const wrap = el("div.stages");
  const index = new Map();
  for (const s of rows) {
    const node = el("div.stage", { dataset: { stage: s.id } });
    node.append(el("span.stage__dot", { html: "<span>•</span>" }));
    const text = el("div.stage__text");
    text.append(
      el("div.stage__label", { text: s.label }),
      el("div.stage__detail", { text: s.detail || "" }),
    );
    node.append(text, el("span.stage__meta", { text: "" }));
    wrap.append(node);
    index.set(s.id, node);
  }
  return { wrap, index };
}

function paintStages(job, index) {
  if (!job) return;
  for (const [id, node] of index) {
    const entry = job.byId[id];
    node.classList.remove("is-active", "is-done", "is-skipped", "is-failed");
    const meta = node.querySelector(".stage__meta");
    const detail = node.querySelector(".stage__detail");
    if (!entry) {
      meta.textContent = "";
      continue;
    }
    const cls =
      entry.status === "done"
        ? "is-done"
        : entry.status === "skipped"
          ? "is-skipped"
          : entry.status === "failed"
            ? "is-failed"
            : "is-active";
    node.classList.add(cls);
    if (entry.detail) detail.textContent = entry.detail;
    node.querySelector(".stage__dot").innerHTML =
      cls === "is-done"
        ? ICONS.check
        : cls === "is-failed"
          ? ICONS.x
          : cls === "is-skipped"
            ? "–"
            : '<span class="spinner" style="width:11px;height:11px;border-width:1.5px"></span>';
    meta.textContent =
      entry.elapsed_ms != null && entry.elapsed_ms > 0 ? `${(entry.elapsed_ms / 1000).toFixed(2)}s` : "";
  }
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    if (file.size > MAX_BYTES) return reject(new Error("File is larger than 10 MB"));
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the file"));
    reader.onload = () => {
      const raw = String(reader.result || "");
      const isText = /\.(txt|md|csv|json)$/i.test(file.name) || file.type.startsWith("text/");
      if (isText) resolve({ kind: "text", value: raw });
      else {
        const b64 = raw.slice(raw.indexOf(",") + 1);
        resolve({ kind: "base64", value: b64 });
      }
    };
    reader.readAsDataURL(file);
  });
}

export async function render() {
  const page = el("div.page");
  const state = get();
  const profiles = state.profiles || [];
  const profileId = state.activeProfileId;

  /* ------------------------------------------------------------ heading -- */
  const head = el("div.page-head");
  const ht = el("div.page-head__text");
  ht.append(el("h1", { text: t("resume.title") }), el("p", { text: t("resume.sub") }));
  head.append(ht);
  page.append(head);

  if (!profiles.length) {
    page.append(
      el("div.notice.notice--warn", {
        html: `${ICONS.alert}<span><strong>${esc(t("profile.empty"))}</strong>
          ${esc(t("resume.pickProfile"))}</span>`,
      }),
      el("div", { style: { marginTop: "16px" } }, [
        el("a.btn.btn--primary", { href: "#/profile", text: t("profile.create") }),
      ]),
    );
    return page;
  }

  /* -------------------------------------------------------------- layout - */
  const grid = el("div.grid", { style: { gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" } });
  if (window.matchMedia("(max-width: 1000px)").matches) grid.style.gridTemplateColumns = "1fr";

  /* ------------------------------------------------------------ importer - */
  const importCard = el("div.card");
  importCard.append(
    el("div.card__head", {}, [
      el("div", {}, [el("h2", { text: t("resume.title") })]),
      el("span.sub", { text: "PDF · DOCX · TXT" }),
    ]),
  );
  const body = el("div.card__body");

  const fileInput = el("input", { type: "file", accept: ".pdf,.docx,.txt,.md,.rtf,text/*" });
  const drop = el("label.dropzone", {}, [
    el("div", { html: ICONS.file }),
    el("strong", { text: t("resume.drop") }),
    el("span", { text: t("resume.dropHint") }),
    fileInput,
  ]);
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("is-over");
    }),
  );
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.remove("is-over");
    }),
  );

  let picked = null;
  const chosenLabel = el("div.small.muted", { style: { minHeight: "18px", marginTop: "6px" } });

  const usePick = async (file) => {
    if (!file) return;
    if (file.size > MAX_BYTES) return toast("File is larger than 10 MB", "bad");
    picked = { file };
    chosenLabel.innerHTML = `<b>${esc(file.name)}</b> · ${bytes(file.size)}`;
    chosenLabel.classList.remove("muted");
  };
  fileInput.addEventListener("change", () => usePick(fileInput.files?.[0]));
  drop.addEventListener("drop", (e) => usePick(e.dataTransfer?.files?.[0]));

  const paste = el("textarea.textarea", {
    placeholder: t("resume.pastePlaceholder"),
    rows: "5",
    style: { marginTop: "12px" },
  });

  const aiCheck = el("label.switch", {}, [
    el("input", { type: "checkbox", checked: true }),
    el("i"),
    el("span", { text: t("resume.useAi") }),
  ]);
  const aiHint = el("div.hint", {
    text: t("resume.useAiHint"),
    style: { marginLeft: "47px", marginTop: "4px" },
  });

  const submit = el("button.btn.btn--primary.btn--lg", {
    html: `<span class="spinner"></span>${ICONS.play}<span>${esc(t("resume.start"))}</span>`,
    style: { marginTop: "16px" },
  });

  body.append(drop, chosenLabel, paste, el("div", { style: { marginTop: "12px" } }, [aiCheck]), aiHint, submit);
  importCard.append(body);

  /* --------------------------------------------------------- stage panel - */
  const stageCard = el("div.card");
  const statusEl = el("div.sub", { id: "resume-status", text: "waiting for an import" });
  const pctEl = el("span.tag.tag--info", { id: "resume-pct", text: "0%" });
  stageCard.append(
    el("div.card__head", {}, [
      el("div", {}, [el("h2", { text: t("resume.stages") }), statusEl]),
      pctEl,
    ]),
  );
  const stageBody = el("div.card__body");
  const { wrap: stages, index: stageIndex } = stageList(state.meta);
  const bar = el("div.progress", { style: { marginBottom: "14px" } }, [el("i")]);
  const summary = el("div", { id: "resume-summary", style: { display: "none" } });
  stageBody.append(bar, stages, summary);
  stageCard.append(stageBody);

  grid.append(importCard, stageCard);
  page.append(grid);

  /* ------------------------------------------------------ version history - */
  const historyCard = el("div.card");
  historyCard.append(
    el("div.card__head", {}, [
      el("h2", { text: t("resume.recent") }),
      el("a.small", { href: "#/profile", text: t("nav.profile") + " →" }),
    ]),
  );
  const historyBody = el("div.card__body");
  historyCard.append(historyBody);
  page.append(el("div", { style: { marginTop: "16px" } }, [historyCard]));

  const paintHistory = async () => {
    clear(historyBody);
    if (!state.activeProfileId) {
      historyBody.append(el("p.muted.small", { text: t("resume.pickProfile") }));
      return;
    }
    try {
      const r = await api.profile(state.activeProfileId);
      const versions = r.resume_versions || [];
      if (!versions.length) {
        historyBody.append(
          emptyState({ icon: ICONS.file, title: t("resume.noVersions"), body: "" }),
        );
        return;
      }
      const table = el("table.data");
      table.innerHTML = `<thead><tr><th>#</th><th>File</th><th>Facts</th><th>Imported</th></tr></thead>`;
      const tb = el("tbody");
      for (const v of versions.slice(0, 8)) {
        const tr = el("tr");
        tr.append(
          el("td", { text: String(v.version ?? "—") }),
          el("td", { html: `<span class="mono">${esc(v.filename || v.source || "—")}</span>` }),
          el("td.num", { text: String(v.fact_count ?? v.facts ?? "—") }),
          el("td", { html: `<span class="faint">${esc(timeAgo(v.created_at))}</span>` }),
        );
        tb.append(tr);
      }
      table.append(tb);
      historyBody.append(el("div.table-wrap", {}, [table]));
    } catch (err) {
      historyBody.append(el("p.muted.small", { text: err.message }));
    }
  };

  /* ---------------------------------------------------------- live wiring - */
  let activeJob = null;

  const unsub = subscribe((s, reason) => {
    if (reason === "progress" && activeJob) {
      const job = s.progress.get(activeJob);
      if (job) {
        paintStages(job, stageIndex);
        const pct = job.percent ?? 0;
        bar.querySelector("i").style.width = `${pct}%`;
        pctEl.textContent = `${Math.round(pct)}%`;
        statusEl.textContent =
          job.status === "failed" ? "failed" : job.detail || job.label || "working…";
      }
    }
    if (reason === "state" || reason === "boot") paintHistory();
  });

  /* ------------------------------------------------------------- submit --- */
  submit.addEventListener("click", async () => {
    const text = paste.value.trim();
    if (!picked && !text) return toast("Choose a file or paste your resume text", "warn");
    if (!state.activeProfileId) return toast(t("resume.pickProfile"), "warn");

    const payload = { profile_id: state.activeProfileId, use_ai: aiCheck.querySelector("input").checked };
    try {
      if (picked) {
        const { kind, value } = await readFile(picked.file);
        payload.filename = picked.file.name;
        if (kind === "text") payload.text = value;
        else payload.content_base64 = value;
      } else {
        payload.text = text;
        payload.filename = "pasted-resume.txt";
      }
    } catch (err) {
      return toast(err.message, "bad");
    }

    const done = busy(submit, t("resume.running"));
    submit.disabled = true;
    try {
      const res = await api.importResume(payload);
      activeJob = res.job_id;
      summary.style.display = "none";
      bar.classList.remove("is-indeterminate");
      bar.querySelector("i").style.width = "3%";
      statusEl.textContent = `queued · ${res.filename}`;
      pctEl.textContent = "0%";
      for (const node of stageIndex.values()) {
        node.classList.remove("is-done", "is-active", "is-failed", "is-skipped");
        node.querySelector(".stage__dot").innerHTML = "<span>•</span>";
        node.querySelector(".stage__meta").textContent = "";
      }
      toast("Import started — stages stream in live", "ok");
      pushActivity({
        kind: "run",
        text: `<b>Resume import</b> started — ${esc(res.filename)}`,
        at: new Date().toISOString(),
      });
    } catch (err) {
      toast(err.message || t("err.unknown"), "bad");
    } finally {
      done();
      submit.disabled = false;
    }
  });

  /* --------------------------------------------------- final task result -- */
  const { default: sse } = await import("../core/sse.js");
  const offDone = sse.on("task_done", (evt) => {
    if (evt?.kind !== "resume" || evt.job_id !== activeJob) return;
    const r = evt.result || {};
    clear(summary).style.display = "block";
    summary.className = r.ok ? "notice notice--ok" : "notice notice--bad";
    const wallMs = Number(r.duration_ms ?? r.wall_ms ?? 0);
    summary.innerHTML = r.ok
      ? `${ICONS.check}<span><strong>${esc(t("resume.done"))}</strong>
         ${r.facts_created ?? 0} ${esc(t("resume.facts"))}
         (${r.ai_facts_created ?? 0} ${esc(t("resume.aiFacts"))}) ·
         ${esc(t("resume.duration"))} ${(wallMs / 1000).toFixed(2)}s
         ${r.warnings?.length ? `<br><span class="warn">${esc(r.warnings.join(" · "))}</span>` : ""}
         ${r.ai_provider ? `<br><span class="faint">provider: ${esc(r.ai_provider)}</span>` : ""}</span>`
      : `${ICONS.alert}<span><strong>${esc(t("resume.failed"))}</strong>
         ${esc(r.error_reason || "unknown error")}
         ${r.user_action ? `<br>${esc(r.user_action)}` : ""}</span>`;

    if (r.ok && r.suggestions?.length) {
      const box = el("div", { style: { marginTop: "12px" } });
      box.append(el("h4", { text: t("profile.autofill"), style: { marginBottom: "8px" } }));
      for (const s of r.suggestions.slice(0, 8)) {
        box.append(
          el("div.suggestion", {}, [
            el("span", { text: s.field }),
            el("span.suggestion__val", { text: String(s.value ?? "") }),
            el("span.suggestion__conf", { text: `${Math.round((s.confidence ?? 0.5) * 100)}%` }),
          ]),
        );
      }
      summary.append(box);
    }
    statusEl.textContent = r.ok ? "complete" : "failed";
    pctEl.textContent = r.ok ? "100%" : "failed";
    if (r.ok) bar.querySelector("i").style.width = "100%";
    paintHistory();
    activeJob = null;
  });

  page.addEventListener(
    "route:leave",
    () => {
      offDone();
      unsub();
      if (activeJob) clearProgress(activeJob);
    },
    { once: true },
  );

  paintHistory();
  return page;
}

export default { render };
