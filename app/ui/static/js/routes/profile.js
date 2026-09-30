/* profile.js — create/edit a profile (all fields) + confirm the fact ledger. */

import api from "../core/api.js";
import store, { get, set, subscribe, setActiveProfile } from "../core/store.js";
import t from "../core/i18n.js";
import {
  el,
  clear,
  toast,
  esc,
  ICONS,
  busy,
  emptyState,
  timeAgo,
  confirmDialog,
  modal,
} from "../core/ui.js";

const WORK_MODES = ["any", "remote", "hybrid", "onsite"];
const FACT_STATE_LABEL = {
  confirmed: ["ok", "Confirmed"],
  inferred: ["warn", "Inferred"],
  rejected: ["bad", "Rejected"],
};

/* ------------------------------------------------------------- helpers --- */
function field({ id, label, value = "", type = "text", hint = "", placeholder = "", attrs = {} }) {
  const wrap = el("div.field");
  const input = el(`input.input#${id}`, { type, value: value ?? "", placeholder, ...attrs });
  wrap.append(el("label", { for: id, text: label }), input);
  if (hint) wrap.append(el("span.hint", { text: hint }));
  return wrap;
}

function selectField({ id, label, value = "", options = [], hint = "" }) {
  const wrap = el("div.field");
  const sel = el(`select.select#${id}`);
  for (const opt of options) {
    const [v, text] = Array.isArray(opt) ? opt : [opt, opt];
    sel.append(el("option", { value: v, text, selected: String(v) === String(value) }));
  }
  wrap.append(el("label", { for: id, text: label }), sel);
  if (hint) wrap.append(el("span.hint", { text: hint }));
  return wrap;
}

function tagEditor({ id, label, values = [], hint = "" }) {
  const wrap = el("div.field");
  const chips = el("div.chips");
  const items = [...values];
  const input = el("input.input", {
    id,
    placeholder: "Type then press Enter",
    autocomplete: "off",
  });

  const paint = () => {
    clear(chips);
    for (let i = 0; i < items.length; i += 1) {
      const v = items[i];
      chips.append(
        el("span.chip", {}, [
          el("span", { text: v }),
          el("button", {
            type: "button",
            "aria-label": `Remove ${v}`,
            text: "×",
            onclick: () => {
              items.splice(i, 1);
              paint();
            },
          }),
        ]),
      );
    }
  };

  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    for (const raw of input.value.split(",")) {
      const v = raw.trim();
      if (v && !items.includes(v)) items.push(v);
    }
    input.value = "";
    paint();
  });

  paint();
  wrap.append(el("label", { for: id, text: label }), chips, input);
  if (hint) wrap.append(el("span.hint", { text: hint }));
  wrap.getValue = () => items.filter((s) => s.trim());
  return wrap;
}

function section(title, icon, ...children) {
  const s = el("div.form-section");
  s.append(el("h3", { html: `${icon}<span>${esc(title)}</span>` }));
  const grid = el("div.form-grid");
  for (const c of children) grid.append(c);
  s.append(grid);
  return s;
}

/* --------------------------------------------------------------- facts ---- */
function factsPanel(facts, { onChanged }) {
  const card = el("div.card");
  card.append(
    el("div.card__head", {}, [
      el("div", {}, [
        el("h2", { text: t("profile.facts") }),
        el("div.sub", { text: t("profile.factsHint") }),
      ]),
      el("button.btn.btn--sm", {
        text: t("profile.confirmAll"),
        onclick: async (e) => {
          const pending = facts.filter((f) => f.state === "inferred");
          if (!pending.length) return toast("Nothing pending", "ok");
          const ok = await confirmDialog(
            "Confirm all shown?",
            `${pending.length} inferred facts will be marked confirmed. Only do this if they are correct.`,
            { confirmLabel: `Confirm ${pending.length}` },
          );
          if (!ok) return;
          const done = busy(e.currentTarget);
          try {
            await api.bulkFacts(pending.map((f) => ({ fact_id: f.id, decision: "confirm" })));
            toast(`${pending.length} facts confirmed`, "ok");
            onChanged();
          } catch (err) {
            toast(err.message, "bad");
          } finally {
            done();
          }
        },
      }),
    ]),
  );

  const body = el("div.card__body");
  if (!facts.length) {
    body.append(
      emptyState({
        icon: ICONS.spark,
        title: "No facts yet",
        body: "Import a resume and extracted facts land here as *inferred* until you confirm them.",
        action: el("a.btn.btn--primary", { href: "#/resume", text: t("resume.title") }),
      }),
    );
    card.append(body);
    return card;
  }

  const filter = el("div.row", { style: { marginBottom: "12px" } });
  const list = el("div");
  let mode = "all";

  const paint = () => {
    clear(list);
    const shown = facts.filter((f) => mode === "all" || f.state === mode);
    if (!shown.length) {
      list.append(el("p.muted.small", { text: "No facts in this state." }));
      return;
    }
    for (const f of shown) {
      const [kind, label] = FACT_STATE_LABEL[f.state] || ["", f.state];
      const row = el("div.suggestion");
      const txt = el("div", { style: { flex: "1 1 auto", minWidth: "0" } });
      const raw = f.skill?.name ?? f.value;
      const value =
        raw == null
          ? ""
          : typeof raw === "object"
            ? String(raw.raw ?? JSON.stringify(raw))
            : String(raw);
      txt.append(
        el("div", {}, [
          el("span.suggestion__val", { text: value }),
          el("span.faint.small", { text: `  · ${f.field_class}` }),
        ]),
        el("div.suggestion__why", {
          text: `${f.provenance?.extraction_rule || "unknown rule"} · ${Math.round(
            (f.confidence ?? 0) * 100,
          )}%`,
        }),
      );
      const actions = el("div.row", { style: { gap: "6px" } });
      if (f.state !== "confirmed") {
        actions.append(
          el("button.btn.btn--sm", {
            text: t("shell.confirm"),
            onclick: async (e) => {
              const done = busy(e.currentTarget, "");
              try {
                await api.decideFact(f.id, "confirm");
                toast("Fact confirmed", "ok");
                onChanged();
              } catch (err) {
                toast(err.message, "bad");
              } finally {
                done();
              }
            },
          }),
        );
      }
      if (f.state !== "rejected") {
        actions.append(
          el("button.btn.btn--sm.btn--ghost", {
            text: t("shell.reject"),
            onclick: async (e) => {
              const done = busy(e.currentTarget, "");
              try {
                await api.decideFact(f.id, "reject");
                toast("Fact rejected", "warn");
                onChanged();
              } catch (err) {
                toast(err.message, "bad");
              } finally {
                done();
              }
            },
          }),
        );
      }
      row.append(el(`span.tag.tag--${kind}`, { text: label }), txt, actions);
      list.append(row);
    }
  };

  const counts = { all: facts.length, inferred: 0, confirmed: 0, rejected: 0 };
  for (const f of facts) counts[f.state] = (counts[f.state] || 0) + 1;
  const segmented = el("div.segmented");
  for (const key of ["all", "inferred", "confirmed", "rejected"]) {
    if (!counts[key] && key !== "all") continue;
    const b = el("button", {
      text: `${key} (${counts[key]})`,
      class: key === "all" ? "is-active" : "",
      onclick: (e) => {
        mode = key;
        for (const s of segmented.children) s.classList.remove("is-active");
        e.currentTarget.classList.add("is-active");
        paint();
      },
    });
    segmented.append(b);
  }
  filter.append(segmented);
  body.append(filter, list);
  card.append(body);
  paint();
  return card;
}

/* --------------------------------------------------------------- render --- */
export async function render(params) {
  const page = el("div.page");
  const state = get();
  const profiles = state.profiles || [];
  const requestedId = params.get("id");
  const activeId = requestedId || state.activeProfileId || profiles[0]?.id || "";
  // tolerate a shortened id (the snapshot abbreviates them for display)
  const resolvedId =
    profiles.find((p) => p.id === activeId)?.id ||
    profiles.find((p) => p.id.startsWith(activeId))?.id ||
    activeId;

  /* ------------------------------------------------------------- heading - */
  const head = el("div.page-head");
  const ht = el("div.page-head__text");
  ht.append(el("h1", { text: t("profile.title") }), el("p", { text: t("profile.sub") }));
  const actions = el("div.page-head__actions");
  actions.append(
    el("button.btn.btn--primary", {
      html: `${ICONS.plus}<span>${esc(t("profile.create"))}</span>`,
      onclick: () => openCreateDialog(),
    }),
  );
  head.append(ht, actions);
  page.append(head);

  if (!profiles.length) {
    page.append(emptyState({ icon: ICONS.spark, title: t("profile.empty"), body: t("profile.nameHint") }));
    return page;
  }

  /* ---------------------------------------------------------- form card -- */
  const formCard = el("div.card");
  const formHead = el("div.card__head");
  const formTitle = el("div");
  formTitle.append(el("h2", { text: profiles.find((p) => p.id === resolvedId)?.name || t("profile.title") }));
  const formSub = el("div.sub", { text: "" });
  formTitle.append(formSub);
  formHead.append(formTitle, el("span.tag.tag--accent", { id: "profile-badge", text: "editing" }));
  formCard.append(formHead);

  const formBody = el("div.card__body");
  const form = el("form", { novalidate: true });
  formBody.append(form);
  formCard.append(formBody);

  const foot = el("div.card__foot");
  const status = el("span.muted.small", { text: "" });
  const saveBtn = el("button.btn.btn--primary", { type: "submit", text: t("shell.save") });
  foot.append(status, saveBtn);
  formCard.append(foot);

  page.append(formCard);

  /* ----------------------------------------------------------- facts card - */
  const factsWrap = el("div", { style: { marginTop: "16px" } });
  page.append(factsWrap);

  let detail = null;

  async function load(id) {
    if (!id) return;
    try {
      detail = await api.profile(id);
      paintForm();
      renderFacts();
      paintVersions();
    } catch (err) {
      toast(err.message, "bad");
    }
  }

  function paintForm() {
    const p = detail?.profile || {};
    clear(form);
    form.append(
      section(
        t("profile.contact"),
        ICONS.spark,
        field({ id: "p-name", label: t("profile.name"), value: p.name, attrs: { required: true } }),
        field({ id: "p-contact", label: "Contact name", value: p.contact_name }),
        field({ id: "p-email", label: "Email", type: "email", value: p.contact_email }),
        field({ id: "p-phone", label: "Phone", type: "tel", value: p.contact_phone }),
        field({ id: "p-location", label: "Location", value: p.location }),
        field({ id: "p-link", label: "Portfolio / GitHub", value: p.links?.github || p.links?.portfolio || "" }),
      ),
    );

    const summary = el("div.form-section");
    summary.append(el("h3", { html: `${ICONS.file}<span>${esc(t("profile.extra"))}</span>` }));
    const sumField = el("div.field");
    sumField.append(el("label", { for: "p-summary", text: "Summary" }));
    const ta = el("textarea.textarea#p-summary", { rows: "4" });
    ta.value = p.extra?.summary || "";
    sumField.append(ta);
    sumField.append(
      el("span.hint", { text: "Auto-filled from your resume — edit freely, nothing is written back." }),
    );
    summary.append(sumField);
    form.append(summary);

    /* targeting */
    const tgt = p.targeting || {};
    const roles = tagEditor({
      id: "p-roles",
      label: t("profile.roles"),
      values: tgt.role_titles || [],
      hint: "Press Enter to add. Required before discovery scores well.",
    });
    const locs = tagEditor({
      id: "p-locs",
      label: t("profile.locations"),
      values: tgt.locations || [],
    });
    const excl = tagEditor({
      id: "p-excl",
      label: t("profile.excluded"),
      values: tgt.excluded_companies || [],
      hint: "Companies you never want to see.",
    });
    form.append(
      section(
        t("profile.targeting"),
        ICONS.refresh,
        roles,
        locs,
        selectField({
          id: "p-mode",
          label: t("profile.workMode"),
          value: (tgt.work_modes || ["any"])[0],
          options: WORK_MODES,
        }),
        field({ id: "p-salary", label: "Minimum salary", type: "number", value: tgt.min_salary ?? "", attrs: { min: "0" } }),
        field({ id: "p-currency", label: "Currency", value: tgt.currency || "EUR", attrs: { maxlength: "3" } }),
        field({ id: "p-notice", label: "Notice period (days)", type: "number", value: tgt.notice_period_days ?? "", attrs: { min: "0", max: "365" } }),
        excl,
      ),
    );
    form._roles = roles;
    form._locs = locs;
    form._excl = excl;

    /* limits */
    const lim = p.limits || {};
    const hours = el("div.fieldset-inline");
    const h1 = field({ id: "p-h1", label: "From (hour)", type: "number", value: lim.active_hours?.[0] ?? 9, attrs: { min: "0", max: "23" } });
    const h2 = field({ id: "p-h2", label: "To (hour)", type: "number", value: lim.active_hours?.[1] ?? 20, attrs: { min: "0", max: "23" } });
    hours.append(h1, h2);
    const limitsSection = section(
      t("profile.limits"),
      ICONS.clock,
      field({ id: "p-perday", label: t("profile.perDay"), type: "number", value: lim.per_day ?? "", attrs: { min: "1", max: "200" } }),
      field({ id: "p-perweek", label: t("profile.perWeek"), type: "number", value: lim.per_week ?? "", attrs: { min: "1", max: "1000" } }),
      field({ id: "p-thresh", label: t("profile.threshold"), type: "number", value: lim.match_threshold ?? "", attrs: { min: "0", max: "1", step: "0.01" } }),
      field({ id: "p-cooldown", label: t("profile.cooldown"), type: "number", value: lim.company_cooldown_days ?? "", attrs: { min: "0", max: "365" } }),
    );
    const hoursWrap = el("div.form-grid");
    hoursWrap.append(hours);
    limitsSection.append(hoursWrap);
    limitsSection.prepend(
      el("p.hint", {
        text: t("profile.limitsHint"),
        style: { marginBottom: "12px", marginTop: "-4px" },
      }),
    );
    form.append(limitsSection);

    const configured = Boolean(p.limits && Object.values(p.limits).every((v) => v !== null && v !== undefined));
    clear(status).append(
      el("span", {
        text: configured ? "Limits configured — the queue is unblocked" : "Limits incomplete — the queue stays blocked",
        class: configured ? "good" : "warn",
      }),
    );
    formSub.textContent = `${detail?.applications ?? 0} applications · ${detail?.facts?.length ?? 0} facts · updated ${timeAgo(p.updated_at)}`;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = form.querySelector("#p-name").value.trim();
    if (!name) {
      const inp = form.querySelector("#p-name");
      inp.setAttribute("aria-invalid", "true");
      return toast(t("profile.name") + " is required", "bad");
    }
    form.querySelector("#p-name").removeAttribute("aria-invalid");

    const num = (sel) => {
      const v = form.querySelector(sel)?.value;
      return v === "" || v === undefined ? null : Number(v);
    };

    const roleTitles = form._roles.getValue();
    const body = {
      name,
      contact_name: form.querySelector("#p-contact").value.trim() || null,
      contact_email: form.querySelector("#p-email").value.trim() || null,
      contact_phone: form.querySelector("#p-phone").value.trim() || null,
      location: form.querySelector("#p-location").value.trim() || null,
      links: form.querySelector("#p-link").value.trim()
        ? { github: form.querySelector("#p-link").value.trim() }
        : {},
      summary: form.querySelector("#p-summary").value,
      targeting: roleTitles.length
        ? {
            role_titles: roleTitles,
            locations: form._locs.getValue(),
            work_modes: [form.querySelector("#p-mode").value],
            min_salary: num("#p-salary"),
            currency: form.querySelector("#p-currency").value.trim() || null,
            notice_period_days: num("#p-notice"),
            excluded_companies: form._excl.getValue(),
            excluded_keywords: [],
          }
        : null,
      limits: null,
    };

    const perDay = num("#p-perday");
    const perWeek = num("#p-perweek");
    const threshold = num("#p-thresh");
    const cooldown = num("#p-cooldown");
    const h1 = num("#p-h1");
    const h2 = num("#p-h2");
    if (perDay != null && perWeek != null && threshold != null && cooldown != null && h1 != null && h2 != null) {
      body.limits = {
        per_day: perDay,
        per_week: perWeek,
        match_threshold: threshold,
        company_cooldown_days: cooldown,
        active_hours: [h1, h2],
      };
    }

    const done = busy(saveBtn, t("shell.save"));
    try {
      const res = await api.saveProfile(body, detail.profile.id);
      toast(t("profile.saved"), "ok");
      const refreshed = await api.profiles();
      set({ profiles: refreshed.profiles }, "profiles");
      setActiveProfile(res.profile_id);
      detail = await api.profile(res.profile_id);
      paintForm();
      renderFacts();
    } catch (err) {
      toast(err.message || t("err.unknown"), "bad");
    } finally {
      done();
    }
  });

  /* -------------------------------------------------------------- facts --- */
  function renderFacts() {
    clear(factsWrap);
    factsWrap.append(
      factsPanel(detail?.facts || [], {
        onChanged: async () => {
          detail = await api.profile(detail.profile.id);
          renderFacts();
          paintForm();
        },
      }),
    );
    paintVersions();
  }

  function paintVersions() {
    const versions = detail?.resume_versions || [];
    if (!versions.length) return;
    const card = el("div.card");
    card.append(
      el("div.card__head", {}, [
        el("h2", { text: t("profile.versions") }),
        el("a.small", { href: "#/resume", text: t("resume.title") + " →" }),
      ]),
    );
    const body = el("div.card__body.card__body--tight");
    const table = el("table.data");
    table.innerHTML = "<thead><tr><th>#</th><th>File</th><th>Imported</th></tr></thead>";
    const tb = el("tbody");
    for (const v of versions.slice(0, 6)) {
      const tr = el("tr");
      tr.append(
        el("td", { text: String(v.version ?? "—") }),
        el("td", { html: `<span class="mono">${esc(v.filename || "—")}</span>` }),
        el("td", { html: `<span class="faint">${esc(timeAgo(v.created_at))}</span>` }),
      );
      tb.append(tr);
    }
    table.append(tb);
    body.append(el("div.table-wrap", {}, [table]));
    card.append(body);
    factsWrap.append(el("div", { style: { marginTop: "16px" } }, [card]));
  }

  /* -------------------------------------------------------------- create --- */
  function openCreateDialog() {
    const body = el("div");
    const nameField = field({ id: "new-name", label: t("profile.name"), placeholder: "Python Developer", hint: t("profile.nameHint") });
    const emailField = field({ id: "new-email", label: "Email", type: "email" });
    body.append(nameField, emailField);
    const dlg = modal({
      title: t("profile.createTitle"),
      subtitle: t("profile.createSub"),
      body,
      actions: [
        el("button.btn", { text: t("shell.cancel"), onclick: () => dlg.close() }),
        el("button.btn.btn--primary", { text: t("shell.create"), onclick: () => submitCreate() }),
      ],
    });
    const submitCreate = async () => {
      const name = body.querySelector("#new-name").value.trim();
      if (!name) return toast(t("profile.name") + " is required", "bad");
      try {
        const res = await api.saveProfile({ name, contact_email: body.querySelector("#new-email").value.trim() || null });
        dlg.close();
        toast(t("profile.saved"), "ok");
        const refreshed = await api.profiles();
        set({ profiles: refreshed.profiles }, "profiles");
        setActiveProfile(res.profile_id);
        location.hash = `#/profile?id=${res.profile_id}`;
        await load(res.profile_id);
      } catch (err) {
        toast(err.message, "bad");
      }
    };
    setTimeout(() => body.querySelector("#new-name").focus(), 60);
  }

  if (resolvedId) await load(resolvedId);

  const unsub = subscribe((s, reason) => {
    if (reason === "profiles" && !detail) load(s.activeProfileId);
  });
  page.addEventListener("route:leave", () => unsub(), { once: true });

  return page;
}

export default { render };
