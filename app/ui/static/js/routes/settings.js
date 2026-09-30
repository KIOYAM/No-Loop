/* settings.js — AI provider (BYOK), application limits, diagnostics.
 *
 * The Gemini key is WRITE-ONLY from the browser: it is sent once to the local
 * server, stored in the OS keyring (or the disclosed secrets.json fallback)
 * and never echoed back — the server only ever reports "configured: true".
 *
 * Read the response shape carefully: /api/ai/status nests everything under
 * `config` and `providers`. `ai.provider`, `ai.gemini` and `ai.models` do not
 * exist — reading them left the badge stuck on "not configured" no matter
 * what you saved, and the model/provider selects silently ignored their
 * stored values.
 *
 * Layout: a card here is ~400px wide, where nested .grid--2/.grid--3 (needing
 * 656px and 720px) collapse to a single column and stack every button into a
 * full-width slab. Pairs and actions use flex (.settings-pair /
 * .settings-actions) instead, which wrap on content at any card width.
 */

import api from "../core/api.js";
import { get, set } from "../core/store.js";
import { el, toast, esc } from "../core/ui.js";

// Fallback only if /api/ai/status is unreachable — every id here answers
// today. The server normalises a retired id on load, so `saved` below is
// always one of the current models.
const FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash"];

const PROVIDER_HELP = {
  auto: "Picks the best available tier: Gemini → local model → rule-based. Falls back automatically on failure.",
  gemini: "Uses your saved Gemini API key for drafting and answering. Requests go to Google's API — the exact text sent is shown in the activity log.",
  local: "Uses a model on this machine (llama.cpp / Ollama / LM Studio). Nothing leaves your device.",
  rule: "No AI calls at all: deterministic templates built from your confirmed facts. Safest, zero cost.",
};

const PROVIDER_LABEL = {
  auto: "Auto (recommended)",
  gemini: "Gemini (your key)",
  local: "Local model",
  rule: "Rule-based (no AI)",
};

const ACTIVE_LABEL = {
  gemini: "Gemini (your key)",
  local: "the local model",
  rule: "rule-based templates",
  none: "nothing yet — no AI tier is configured",
};

/* ------------------------------------------------------------- builders -- */
function section(title, subtitle, badge) {
  const card = el("section.card.settings-card");
  const titles = el("div");
  titles.append(el("h2", { text: title }));
  if (subtitle) titles.append(el("p.muted", { text: subtitle }));
  const head = el("div.settings-card__head", {}, [titles]);
  if (badge) head.append(badge);
  card.append(head);
  return card;
}

function statusTag(on) {
  return el("span.tag", {
    class: `tag ${on ? "tag--ok" : "tag--warn"}`,
    text: on ? "configured ✓" : "not configured",
  });
}

function field(labelText, input, hint) {
  const wrap = el("label.field");
  wrap.append(el("span.kpi__label", { text: labelText }));
  input.style.width = "100%";
  wrap.append(input);
  if (hint) wrap.append(el("p.hint", { text: hint }));
  return wrap;
}

const pair = (...fields) => el("div.settings-pair", {}, fields);
const actions = (...buttons) => el("div.settings-actions", {}, buttons);

function textInput({ type = "text", placeholder = "", value = "", min = null, id = null }) {
  const input = el("input.input", { type, placeholder, id, autocomplete: "off" });
  // `if (value)` would drop a legitimate 0 — active hours from midnight is 0.
  if (value !== "" && value !== null && value !== undefined) input.value = String(value);
  if (min !== null) input.min = String(min);
  return input;
}

/* ------------------------------------------------------------- Gemini key -- */
function geminiCard(ai, syncActive) {
  const g = ai?.providers?.gemini || {};
  const state = { configured: !!g.configured, backend: g.key_backend || "none" };
  const badge = statusTag(state.configured);
  const card = section(
    "Gemini API key (BYOK)",
    "Stored on this machine and sent only to Google when the AI runs. Write-only: it is never shown back to the browser.",
    badge,
  );

  const keyInput = textInput({
    type: "password",
    placeholder: "AIza… (paste your key)",
    id: "gemini-key",
  });
  keyInput.setAttribute("spellcheck", "false");
  keyInput.setAttribute("aria-label", "Gemini API key");

  const models = [...(ai?.gemini_models?.length ? ai.gemini_models : FALLBACK_MODELS)];
  const saved = g.model || ai?.config?.gemini_model || "";
  // a stored model that has left the list must still be selectable, or saving
  // anything else would silently rewrite it to the first option
  if (saved && !models.includes(saved)) models.unshift(saved);
  const modelSel = el("select.input", { id: "gemini-model", "aria-label": "Gemini model" });
  for (const m of models) modelSel.append(el("option", { value: m, text: m }));
  if (saved) modelSel.value = saved;

  // Persist the model the moment it is picked. The committed version only
  // saved it inside "Save key" — which early-returns on an empty field, so
  // once a key was stored there was no way to change the model at all.
  modelSel.addEventListener("change", async () => {
    const chosen = modelSel.value;
    try {
      await api.aiSave({ gemini_model: chosen });
      toast(`Model set to ${chosen}`, "ok");
      await refreshAi();
    } catch (err) {
      toast(err.message || "Could not save the model", "bad");
      const have = get()?.ai?.config?.gemini_model;
      if (have) modelSel.value = have; // revert to what the server actually holds
    }
  });

  const note = el("p.muted.settings-note");
  const out = el("p.muted.settings-note", { style: { display: "none" } });

  const backendText = (on, backend) =>
    !on || backend === "none"
      ? "No key stored yet — paste one above to turn Gemini on."
      : backend === "keyring"
        ? "Key held in your OS credential store (keyring)."
        : "keyring unavailable — key held in .local-data/secrets.json (gitignored, never exported).";

  const where = (backend) =>
    backend === "keyring" ? "your OS credential store" : ".local-data/secrets.json";

  const showOut = (text, kind) => {
    out.textContent = text;
    out.style.display = text ? "" : "none";
    out.style.color = kind === "bad" ? "var(--bad)" : kind === "ok" ? "var(--ok)" : "";
  };

  const saveBtn = el("button.btn.btn--primary", { type: "button", text: "Save key" });
  const testBtn = el("button.btn", { type: "button", text: "Test connection" });
  const clearBtn = el("button.btn.btn--danger", { type: "button", text: "Clear stored key" });

  // `headline` is what makes a change *look* like a change: re-saving a key
  // leaves the badge and the storage note reading exactly as before, so
  // without it nothing on the card appears to move.
  const sync = (on, backend, headline) => {
    state.configured = on;
    state.backend = backend;
    badge.className = `tag ${on ? "tag--ok" : "tag--warn"}`;
    badge.textContent = on ? "configured ✓" : "not configured";
    note.textContent = headline || backendText(on, backend);
    note.style.color = headline ? "var(--ok)" : "";
    clearBtn.disabled = !on;
  };

  const keySaved = (backend) => `✓ Key saved — stored in ${where(backend)}, never shown again`;

  saveBtn.addEventListener("click", async () => {
    const key = keyInput.value.trim();
    if (!key) {
      toast("Paste a key first", "info");
      keyInput.focus();
      return;
    }
    saveBtn.disabled = true;
    try {
      const res = await api.saveGeminiKey(key);
      keyInput.value = "";
      const backend = res?.backend || "file";
      sync(true, backend, keySaved(backend));
      showOut("");
      toast("Key saved — it will never be shown again", "ok");
      await refreshAi();
      syncActive?.();
    } catch (err) {
      showOut(err.message || "Could not save the key", "bad");
      toast(err.message || "Could not save the key", "bad");
    } finally {
      saveBtn.disabled = false;
    }
  });

  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    testBtn.textContent = "Testing…";
    showOut("Contacting the provider…");
    try {
      // a key pasted but not yet saved would otherwise be tested as absent
      if (keyInput.value.trim()) {
        const res = await api.saveGeminiKey(keyInput.value.trim());
        keyInput.value = "";
        const backend = res?.backend || "file";
        sync(true, backend, keySaved(backend));
        toast("Key saved — testing it now", "ok");
        await refreshAi();
        syncActive?.();
      }
      const res = await api.aiTest();
      const r = res?.test || {};
      const detail =
        `${r.provider || "unknown provider"} — ${r.message || ""}` +
        `${r.latency_ms ? ` (${r.latency_ms} ms)` : ""}`;
      showOut(detail.trim(), r.ok ? "ok" : "bad");
      if (r.ok) toast(r.message || "Connection OK", "ok");
      else toast(r.message || r.error || "Test failed — check the key and model", "bad");
    } catch (err) {
      showOut(err.message || "Test failed", "bad");
      toast(err.message || "Test failed", "bad");
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = "Test connection";
    }
  });

  clearBtn.addEventListener("click", async () => {
    clearBtn.disabled = true;
    try {
      await api.clearGeminiKey();
      sync(false, "none", "Stored key removed — paste a new key above to turn Gemini on");
      showOut("");
      toast("Stored key removed", "ok");
      await refreshAi();
      syncActive?.();
    } catch (err) {
      showOut(err.message || "Could not clear the key", "bad");
      toast(err.message || "Could not clear the key", "bad");
    } finally {
      clearBtn.disabled = !state.configured;
    }
  });

  card.append(
    pair(
      field("API key", keyInput, "Free at aistudio.google.com → Get API key"),
      field("Model", modelSel, "Flash models are fast and very cheap for drafting"),
    ),
    actions(saveBtn, testBtn, clearBtn),
    note,
    out,
  );
  sync(state.configured, state.backend);
  return card;
}

/* --------------------------------------------------------- provider tier -- */
function providerCard(ai, activeNote, syncActive) {
  const cfg = ai?.config || {};
  const card = section(
    "AI provider",
    "Which tier drafts emails and answers application questions. 'Auto' falls back down the chain so a missing key never blocks you.",
  );

  const choices = ai?.provider_choices || ["auto", "gemini", "local", "rule"];
  const current = cfg.provider || "auto";
  const sel = el("select.input", { id: "ai-provider", "aria-label": "AI provider" });
  for (const c of choices) sel.append(el("option", { value: c, text: PROVIDER_LABEL[c] || c }));
  sel.value = current;

  const help = el("p.muted.settings-note", { text: PROVIDER_HELP[current] || "" });
  sel.addEventListener("change", () => {
    help.textContent = PROVIDER_HELP[sel.value] || "";
  });

  // what will actually answer *right now* — "Auto" can be selected while the
  // chain still bottoms out on rule-based, and saying so beats a green tick.
  // `render()` owns this node and the sync, so saving a Gemini key in the
  // other card refreshes it too instead of leaving a stale claim behind.
  syncActive();

  const save = el("button.btn.btn--primary", { type: "button", text: "Save provider" });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await api.aiSave({ provider: sel.value });
      toast("Provider saved", "ok");
      await refreshAi();
      syncActive();
    } catch (err) {
      toast(err.message || "Could not save", "bad");
    } finally {
      save.disabled = false;
    }
  });

  card.append(field("Provider", sel, null), help, activeNote, actions(save));

  const local = ai?.providers?.local;
  if (local) {
    card.append(
      el("p.muted.settings-note", {
        html:
          `Local model: <b>${esc(local.model || "not set")}</b> · ` +
          `endpoint <code>${esc(local.endpoint || "-")}</code> · ` +
          `${local.configured || local.path_exists ? "detected ✓" : "not detected"}`,
      }),
    );
  }
  return card;
}

/* -------------------------------------------------------- local LLM (BYOK) -- */
/* Configured by *path or URL + model name* so any LLM already on disk works:
 * `normalize_endpoint` appends /v1 to a bare host, and a .gguf / model folder
 * path is accepted too. No_Loop never installs or launches a runtime itself. */
function localCard(ai, syncActive) {
  const cfg = ai?.config || {};
  const local = ai?.providers?.local || {};
  const badge = statusTag(!!(local.configured || local.path_exists));
  const card = section(
    "Local model (OpenAI-compatible)",
    "Talks to llama.cpp / Ollama / LM Studio / vLLM over http://…/v1/chat/completions. Nothing leaves this machine.",
    badge,
  );

  const endpoint = textInput({
    placeholder: "http://127.0.0.1:8080/v1  ·  or D:\\models\\model.gguf",
    value: cfg.local_endpoint || "",
    id: "local-endpoint",
  });
  endpoint.setAttribute("aria-label", "Local endpoint or model path");
  const model = textInput({
    placeholder: "e.g. qwen2.5-3b-instruct",
    value: cfg.local_model || "",
    id: "local-model",
  });
  model.setAttribute("aria-label", "Local model name");

  /* preset chips — display-only hints, never installed or launched */
  const presets = ai?.presets || [];
  if (presets.length) {
    const row = el("div.row", { style: { flexWrap: "wrap", margin: "0 0 14px" } });
    for (const p of presets) {
      const chip = el("button.btn.btn--sm", { type: "button", text: p.label });
      chip.title = `Fill ${p.endpoint}`;
      chip.addEventListener("click", () => {
        endpoint.value = p.endpoint;
        endpoint.focus();
        toast(`Endpoint set to ${p.endpoint} — press Save model`, "info");
      });
      row.append(chip);
    }
    card.append(el("span.kpi__label", { text: "Quick fill", style: { display: "block", marginBottom: "6px" } }), row);
  }

  const save = el("button.btn.btn--primary", { type: "button", text: "Save model" });
  const probe = el("button.btn", { type: "button", text: "Test connection" });
  const out = el("p.settings-out", { text: "Not tested yet." });

  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const res = await api.aiSave({
        local_endpoint: endpoint.value.trim(),
        local_model: model.value.trim(),
      });
      toast("Local model saved", "ok");
      badge.className = "tag tag--ok";
      badge.textContent = "configured ✓";
      out.textContent = res?.status ? "Saved. Press Test connection to reach the endpoint." : "Saved.";
      await refreshAi();
      syncActive?.();
    } catch (err) {
      out.textContent = err.message || "Could not save the local model";
      out.style.color = "var(--bad)";
      toast(err.message || "Could not save the local model", "bad");
    } finally {
      save.disabled = false;
    }
  });

  probe.addEventListener("click", async () => {
    probe.disabled = true;
    probe.textContent = "Testing…";
    out.style.color = "";
    out.textContent = "Contacting the endpoint…";
    try {
      // persist what is in the fields first so the probe tests them
      await api.aiSave({ local_endpoint: endpoint.value.trim(), local_model: model.value.trim() });
      const res = await api.localProbe();
      const p = res?.probe || {};
      if (p.reachable) {
        const names = (p.models || []).slice(0, 6).join(", ");
        out.textContent =
          `Reachable ✓ ${p.endpoint} · ${p.latency_ms} ms` +
          (names ? ` · models: ${names}` : "") +
          (p.model_configured === false ? ` · model "${p.model}" not in that list` : "");
        badge.className = "tag tag--ok";
        badge.textContent = "configured ✓";
        toast("Local endpoint reachable", "ok");
      } else {
        out.textContent = `${p.endpoint || endpoint.value} — ${p.error || "not reachable"}`;
        out.style.color = "var(--bad)";
        badge.className = "tag tag--warn";
        badge.textContent = "not reachable";
        toast("Local endpoint not reachable", "bad");
      }
    } catch (err) {
      out.textContent = err.message || "probe failed";
      out.style.color = "var(--bad)";
      toast(err.message || "Probe failed", "bad");
    } finally {
      probe.disabled = false;
      probe.textContent = "Test connection";
    }
  });

  card.append(
    pair(
      field("Endpoint or model path", endpoint, "Base URL (a bare host gets /v1 appended) or a .gguf / model folder"),
      field("Model name", model, "Must match a model the server exposes — required before the provider activates"),
    ),
    actions(save, probe),
    out,
  );

  if (local.path) {
    card.append(
      el("p.muted.settings-note", {
        html: `Configured path: <code>${esc(local.path)}</code> · ${local.path_exists ? "exists ✓" : "not found"}`,
      }),
    );
  }
  return card;
}

/* ---------------------------------------------------------------- limits -- */
/* The profile list and the state snapshot only expose `limits: true` (a
 * "configured" flag). The actual numbers live on the profile detail endpoint,
 * so this card loads them from there before rendering. */
async function loadActiveProfile() {
  const st = get();
  const id = st.activeProfileId || (st.profiles || [])[0]?.id;
  if (!id) return null;
  try {
    const res = await api.profile(id);
    return res?.profile || null;
  } catch {
    return null;
  }
}

async function refreshProfiles() {
  try {
    const res = await api.profiles();
    set({ profiles: res?.profiles || [] }, "profiles");
  } catch {
    /* non-fatal — the next state_changed push will catch up */
  }
}

function limitsCard(profile) {
  const card = section(
    "Application limits",
    "Hard caps protect you from over-applying. The queue stays locked until every limit is set (no silent defaults).",
  );
  const limits = profile?.limits || {};
  const hours = Array.isArray(limits.active_hours) ? limits.active_hours : [9, 20];

  const daily = textInput({ type: "number", min: 1, max: 200, value: limits.per_day ?? "", placeholder: "e.g. 10" });
  const weekly = textInput({ type: "number", min: 1, max: 1000, value: limits.per_week ?? "", placeholder: "e.g. 40" });
  const threshold = textInput({
    type: "number",
    min: 0,
    max: 1,
    value: limits.match_threshold ?? "",
    placeholder: "e.g. 0.6",
  });
  threshold.step = "0.05";
  const cooldown = textInput({
    type: "number",
    min: 0,
    max: 365,
    value: limits.company_cooldown_days ?? "",
    placeholder: "e.g. 7",
  });
  const from = textInput({ type: "number", min: 0, max: 23, value: hours[0] ?? 9 });
  const to = textInput({ type: "number", min: 1, max: 24, value: hours[1] ?? 20 });
  for (const n of [daily, weekly, threshold, cooldown, from, to]) n.inputMode = "numeric";

  const status = el("p.muted.settings-note", {
    text: profile
      ? `Editing limits for profile: ${profile.name}`
      : "Create or select a profile first — limits are per profile.",
  });

  const save = el("button.btn.btn--primary", { type: "button", text: "Save limits" });
  save.addEventListener("click", async () => {
    if (!profile) return toast("Create a profile first", "bad");
    const num = (node) => (node.value.trim() === "" ? NaN : Number(node.value));
    const perDay = num(daily);
    const perWeek = num(weekly);
    const thr = num(threshold);
    const cool = num(cooldown);
    const start = num(from);
    const end = num(to);

    if (!Number.isFinite(perDay) || perDay < 1 || perDay > 200) {
      return toast("Max applications / day must be 1–200", "bad");
    }
    if (!Number.isFinite(perWeek) || perWeek < 1) return toast("Max applications / week is required", "bad");
    if (perWeek < perDay) return toast("Weekly cap must be at least the daily cap", "bad");
    if (!Number.isFinite(thr) || thr < 0 || thr > 1) return toast("Match threshold must be 0–1", "bad");
    if (!Number.isFinite(cool) || cool < 0 || cool > 365) return toast("Company cooldown must be 0–365 days", "bad");
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > 24 || end <= start) {
      return toast("Active hours must be a start-before-end window (0–24)", "bad");
    }

    save.disabled = true;
    try {
      // the server REPLACES the whole limits object, so every field is sent
      await api.saveProfile(
        {
          limits: {
            per_day: perDay,
            per_week: perWeek,
            match_threshold: thr,
            company_cooldown_days: cool,
            active_hours: [start, end],
          },
        },
        profile.id,
      );
      toast("Limits saved", "ok");
      status.textContent = "Saved — application limits are active for this profile.";
      status.style.color = "var(--ok)";
      await refreshProfiles();
    } catch (err) {
      status.textContent = err.message || "Could not save limits";
      status.style.color = "var(--bad)";
      toast(err.message || "Could not save limits", "bad");
    } finally {
      save.disabled = false;
    }
  });

  card.append(
    status,
    pair(
      field("Max applications / day", daily, "1–200"),
      field("Max applications / week", weekly, "must be ≥ the daily cap"),
      field("Match threshold", threshold, "0–1 · below this, no apply"),
    ),
    pair(
      field("Company cooldown (days)", cooldown, "0 = none"),
      field("Active hours from", from, "0–23"),
      field("Active hours to", to, "1–24"),
    ),
    actions(save),
  );
  return card;
}

/* ------------------------------------------------------------ diagnostics -- */
function diagnosticsCard() {
  const card = section(
    "System diagnostics",
    "One-shot hardware and local-model check. Read-only, runs on this machine — nothing is sent anywhere.",
  );
  const out = el("pre.code.settings-out", { style: { maxHeight: "240px", overflow: "auto" } });
  out.textContent = "Press “Run check”…";
  const btn = el("button.btn", { type: "button", text: "Run check" });
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    out.style.color = "";
    out.textContent = "Probing…";
    try {
      const res = await api.diagnose();
      out.textContent = JSON.stringify(res, null, 2);
    } catch (err) {
      out.textContent = `error: ${err.message}`;
      out.style.color = "var(--bad)";
    } finally {
      btn.disabled = false;
    }
  });
  card.append(actions(btn), out);
  return card;
}

/* ------------------------------------------------------------------ page --- */
async function refreshAi() {
  try {
    const res = await api.aiStatus();
    set({ ai: res?.ai || res }, "settings.ai");
  } catch {
    /* non-fatal */
  }
}

export async function render() {
  await refreshAi();
  const state = get();
  const ai = state.ai || {};
  // limits live on the profile detail, not in the snapshot
  const profile = await loadActiveProfile();

  const page = el("div.page");
  page.append(
    el("div.page-head", {}, [
      el("div.page-head__text", {}, [
        el("h1", { text: "Settings" }),
        el("p.muted", {
          text: "AI providers, safety limits and local data — everything stays on this machine.",
        }),
      ]),
    ]),
  );

  // Owned here so every card that can change what resolves — the Gemini key,
  // the local model, the selected tier — refreshes the same line rather than
  // leaving a stale "Gemini" claim after the key has been cleared.
  const activeNote = el("p.settings-note");
  const syncActive = () => {
    const key = get()?.ai?.active || "";
    activeNote.textContent = key ? `Answering right now: ${ACTIVE_LABEL[key] || key}.` : "";
    activeNote.style.display = key ? "" : "none";
  };

  const row1 = el("div.settings-grid");
  row1.append(geminiCard(ai, syncActive), localCard(ai, syncActive));

  const row2 = el("div.settings-grid");
  row2.append(providerCard(ai, activeNote, syncActive), limitsCard(profile));

  page.append(row1, row2, diagnosticsCard());

  page.append(
    el("p.muted.settings-note", {
      html:
        "Privacy: the key lives in your OS credential store (fallback: a local gitignored file). " +
        "It is sent only to Google's Generative Language API when the AI runs, and never written " +
        "to logs, exports or the activity feed.",
      style: { marginTop: "18px" },
    }),
  );

  return page;
}

export default { render };
