/* settings.js — AI provider (BYOK), application limits, data & language.
 * The Gemini key is WRITE-ONLY from the browser: it is sent once to the local
 * server, stored in the OS keyring (or disclosed file fallback), and never
 * echoed back. The server only ever reports "configured: true/false".
 */

import api from "../core/api.js";
import { get, set } from "../core/store.js";
import t from "../core/i18n.js";
import { el, clear, toast, esc } from "../core/ui.js";

const PROVIDER_HELP = {
  auto: "Picks the best available tier: Gemini → local model → rule-based. Falls back automatically on failure.",
  gemini: "Uses your saved Gemini API key for drafting and answering. Requests go to Google's API — the exact text sent is shown in the activity log.",
  local: "Uses a model on this machine (llama.cpp / Ollama / LM Studio). Nothing leaves your device.",
  rule: "No AI calls at all: deterministic templates built from your confirmed facts. Safest, zero cost.",
};

function section(title, subtitle) {
  const card = el("section.card.settings-card");
  card.append(
    el("h2", { text: title, style: { margin: "0 0 2px", fontSize: "16px" } }),
    subtitle ? el("p.muted", { text: subtitle, style: { margin: "0 0 14px", fontSize: "12.5px" } }) : "",
  );
  return card;
}

function field(labelText, input, hint) {
  const wrap = el("label.field", { style: { display: "block", marginBottom: "12px" } });
  wrap.append(el("span.kpi__label", { text: labelText }));
  input.style.width = "100%";
  wrap.append(input);
  if (hint) wrap.append(el("p.muted", { text: hint, style: { margin: "4px 0 0", fontSize: "11.5px" } }));
  return wrap;
}

function textInput({ type = "text", placeholder = "", value = "", min = null, id = null }) {
  const input = el("input.input", { type, placeholder, id, autocomplete: "off" });
  if (value) input.value = value;
  if (min !== null) input.min = String(min);
  return input;
}

/* ------------------------------------------------------------- Gemini key -- */
function geminiCard(ai) {
  const gem = ai?.gemini || { configured: false, models: [] };
  const card = section(
    "Gemini API key (BYOK)",
    "Your key is stored locally (OS keyring when available) and sent only to Google when the AI runs. Write-only: it is never shown again.",
  );
  const status = el("span.tag", {
    class: `tag ${gem.configured ? "tag--ok" : "tag--warn"}`,
    text: gem.configured ? "configured ✓" : "not configured",
  });
  card.append(el("div", { style: { marginBottom: "10px" } }, [status]));

  const keyInput = textInput({ type: "password", placeholder: "AIza… (paste your key)", id: "gemini-key" });
  const modelSel = el("select.input", { id: "gemini-model" });
  for (const m of gem.models?.length ? gem.models : ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]) {
    modelSel.append(el("option", { value: m, text: m }));
  }
  if (gem.model) modelSel.value = gem.model;

  const saveBtn = el("button.btn.btn--primary", { text: "Save key" });
  saveBtn.addEventListener("click", async () => {
    const key = keyInput.value.trim();
    if (!key) {
      toast("Paste a key first (or clear the field to remove it)", "info");
      return;
    }
    saveBtn.disabled = true;
    try {
      await api.saveGeminiKey(key);
      await api.aiSave({ gemini_model: modelSel.value });
      keyInput.value = "";
      toast("Key saved — it will not be shown again", "ok");
      await refreshAi();
    } catch (err) {
      toast(err.message || "Could not save the key", "bad");
    } finally {
      saveBtn.disabled = false;
    }
  });

  const clearBtn = el("button.btn", { text: "Clear stored key" });
  clearBtn.addEventListener("click", async () => {
    clearBtn.disabled = true;
    try {
      await api.saveGeminiKey(" ");
      toast("Stored key removed", "ok");
      await refreshAi();
    } catch (err) {
      toast(err.message || "Could not clear the key", "bad");
    } finally {
      clearBtn.disabled = false;
    }
  });

  const testBtn = el("button.btn", { text: "Test connection" });
  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    testBtn.textContent = "Testing…";
    try {
      // the server answers { ok, test: { ok, provider, latency_ms, message } }
      const res = await api.aiTest();
      const test = res?.test || {};
      if (test.ok) {
        toast(`${test.provider}: ${test.message || "OK"}${test.latency_ms ? ` (${test.latency_ms} ms)` : ""}`, "ok");
      } else {
        toast(test.error || res?.error || "Test failed — check key/model", "bad");
      }
    } catch (err) {
      toast(err.message || "Test failed", "bad");
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = "Test connection";
    }
  });

  const row = el("div.grid.grid--2", { style: { gap: "12px" } });
  row.append(
    field("API key", keyInput, "Get one free at aistudio.google.com → Get API key"),
    field("Model", modelSel, "Flash models are fast and very cheap for drafting"),
  );
  card.append(row, el("div.grid.grid--3", { style: { gap: "8px" } }, [saveBtn, testBtn, clearBtn]));
  return card;
}

/* ------------------------------------------------------- provider / tiers -- */
function providerCard(ai) {
  const card = section(
    "AI provider",
    "Which tier drafts emails and answers application questions. 'Auto' falls back down the chain so a missing key never blocks you.",
  );
  const choices = ai?.provider_choices || ["auto", "gemini", "local", "rule"];
  const current = ai?.provider || "auto";
  const sel = el("select.input", { id: "ai-provider" });
  for (const c of choices) {
    const label = { auto: "Auto (recommended)", gemini: "Gemini (your key)", local: "Local model", rule: "Rule-based (no AI)" }[c] || c;
    sel.append(el("option", { value: c, text: label }));
  }
  sel.value = current;
  const help = el("p.muted", { text: PROVIDER_HELP[current] || "", style: { margin: "6px 0 0", fontSize: "11.5px" } });
  sel.addEventListener("change", () => {
    help.textContent = PROVIDER_HELP[sel.value] || "";
  });

  const save = el("button.btn.btn--primary", { text: "Save provider" });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await api.aiSave({ provider: sel.value });
      toast("Provider saved", "ok");
      await refreshAi();
    } catch (err) {
      toast(err.message || "Could not save", "bad");
    } finally {
      save.disabled = false;
    }
  });
  card.append(field("Provider", sel, null), help, el("div", { style: { marginTop: "10px" } }, [save]));

  const local = ai?.local;
  if (local) {
    const ok = local.configured || local.path_exists;
    card.append(
      el("p.muted", {
        html: `Local model: <b>${esc(local.model || "not set")}</b> · endpoint <code>${esc(local.endpoint || "-")}</code> · ${ok ? "detected ✓" : "not detected"}`,
        style: { margin: "10px 0 0", fontSize: "11.5px" },
      }),
    );
  }
  return card;
}

/* -------------------------------------------------------- local LLM (BYOK) -- */
/* Configured by *path or URL + model name* so any LLM already on disk works:
 * `normalize_endpoint` appends /v1 to a bare host, and a .gguf / model folder
 * path is accepted too. No_Loop never installs or launches a runtime itself. */
function localCard(ai) {
  const cfg = ai?.config || {};
  const card = section(
    "Local model (OpenAI-compatible)",
    "Talks to llama.cpp / Ollama / LM Studio / vLLM over http://…/v1/chat/completions. Nothing leaves this machine.",
  );

  const local = ai?.providers?.local || {};
  const status = el("span.tag", {
    class: `tag ${local.configured || local.path_exists ? "tag--ok" : "tag--warn"}`,
    text: local.configured || local.path_exists ? "configured ✓" : "not configured",
  });
  card.append(el("div", { style: { marginBottom: "10px" } }, [status]));

  const endpoint = textInput({
    placeholder: "http://127.0.0.1:8080/v1  ·  or D:\\models\\model.gguf",
    value: cfg.local_endpoint || "",
    id: "local-endpoint",
  });
  const model = textInput({
    placeholder: "e.g. qwen2.5-3b-instruct",
    value: cfg.local_model || "",
    id: "local-model",
  });

  /* preset chips — display-only hints, never installed or launched */
  const presets = el("div.row", { style: { gap: "8px", flexWrap: "wrap", margin: "0 0 12px" } });
  for (const p of ai?.presets || []) {
    const chip = el("button.btn", { type: "button", text: p.label });
    chip.title = p.endpoint;
    chip.addEventListener("click", () => {
      endpoint.value = p.endpoint;
      endpoint.focus();
    });
    presets.append(chip);
  }
  if ((ai?.presets || []).length) {
    card.append(el("span.kpi__label", { text: "Quick fill" }), presets);
  }

  const save = el("button.btn.btn--primary", { text: "Save model" });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await api.aiSave({ local_endpoint: endpoint.value.trim(), local_model: model.value.trim() });
      toast("Local model saved", "ok");
      await refreshAi();
    } catch (err) {
      toast(err.message || "Could not save the local model", "bad");
    } finally {
      save.disabled = false;
    }
  });

  const out = el("p.muted", { style: { margin: "8px 0 0", fontSize: "11.5px" } });
  const probe = el("button.btn", { text: "Test connection" });
  probe.addEventListener("click", async () => {
    probe.disabled = true;
    probe.textContent = "Testing…";
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
        toast("Local endpoint reachable", "ok");
      } else {
        out.textContent = `${p.endpoint || endpoint.value} — ${p.error || "not reachable"}`;
        toast("Local endpoint not reachable", "bad");
      }
    } catch (err) {
      out.textContent = err.message || "probe failed";
      toast(err.message || "Probe failed", "bad");
    } finally {
      probe.disabled = false;
      probe.textContent = "Test connection";
    }
  });

  card.append(
    field("Endpoint or model path", endpoint, "Base URL (a bare host gets /v1 appended) or a .gguf / model folder"),
    field("Model name", model, "Must match a model the server exposes — required before the provider activates"),
    el("div.grid.grid--2", { style: { gap: "8px" } }, [save, probe]),
    out,
  );

  if (local.path) {
    card.append(
      el("p.muted", {
        html: `Configured path: <code>${esc(local.path)}</code> · ${local.path_exists ? "exists ✓" : "not found"}`,
        style: { margin: "8px 0 0", fontSize: "11.5px" },
      }),
    );
  }
  return card;
}

/* ----------------------------------------------------------------- limits -- */
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

  const status = el("p.muted", {
    text: profile
      ? `Editing limits for profile: ${profile.name}`
      : "Create or select a profile first — limits are per profile.",
    style: { margin: "0 0 10px", fontSize: "12px" },
  });

  const save = el("button.btn.btn--primary", { text: "Save limits" });
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
      await refreshProfiles();
    } catch (err) {
      toast(err.message || "Could not save limits", "bad");
    } finally {
      save.disabled = false;
    }
  });

  card.append(
    status,
    el("div.grid.grid--3", { style: { gap: "12px" } }, [
      field("Max applications / day", daily, "1–200"),
      field("Max applications / week", weekly, "must be ≥ the daily cap"),
      field("Match threshold", threshold, "0–1 · below this, no apply"),
    ]),
    el("div.grid.grid--3", { style: { gap: "12px", marginTop: "12px" } }, [
      field("Company cooldown (days)", cooldown, "0 = none"),
      field("Active hours from", from, "0–23"),
      field("Active hours to", to, "1–24"),
    ]),
    el("div", { style: { marginTop: "12px" } }, [save]),
  );
  return card;
}

/* ------------------------------------------------------------ diagnostics -- */
function diagnosticsCard() {
  const card = section("System diagnostics", "One-shot hardware + local-model check. Read-only, runs locally.");
  const out = el("pre.code", { style: { maxHeight: "220px", overflow: "auto", fontSize: "11.5px" } });
  out.textContent = "Press “Run check”…";
  const btn = el("button.btn", { text: "Run check" });
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    out.textContent = "Probing…";
    try {
      const res = await api.diagnose();
      out.textContent = JSON.stringify(res, null, 2);
    } catch (err) {
      out.textContent = `error: ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  });
  card.append(btn, out);
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
  const head = el("div.page-head");
  head.append(
    el("div.page-head__text", {}, [
      el("h1", { text: "Settings" }),
      el("p.muted", { text: "AI providers, safety limits and local data — everything stays on this machine." }),
    ]),
  );
  page.append(head);

  const grid = el("div.grid.grid--2", { style: { gap: "16px", alignItems: "start" } });
  grid.append(geminiCard(ai), localCard(ai));

  const grid2 = el("div.grid.grid--2", { style: { gap: "16px", alignItems: "start", marginTop: "16px" } });
  grid2.append(providerCard(ai), limitsCard(profile));

  const grid3 = el("div.grid.grid--2", { style: { gap: "16px", alignItems: "start", marginTop: "16px" } });
  grid3.append(diagnosticsCard());
  page.append(grid, grid2, grid3);

  page.append(
    el("p.muted", {
      html: `Privacy: the key lives in your OS credential store (fallback: a local file). It is sent only to Google's Generative Language API when the AI runs, and never written to logs, exports or the activity feed.`,
      style: { margin: "18px 0 0", fontSize: "12px" },
    }),
  );

  return page;
}

export default { render };
