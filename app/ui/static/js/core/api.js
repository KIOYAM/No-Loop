/* api.js — one place for every HTTP call. Local-only (same origin). */

const BASE = "";

class ApiError extends Error {
  constructor(message, { status = 0, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function request(path, { method = "GET", body = null, signal = null } = {}) {
  const init = { method, headers: {}, signal, cache: "no-store" };
  if (body !== null) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(BASE + path, init);
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    throw new ApiError("Cannot reach the local No_Loop server", { status: 0 });
  }
  const type = res.headers.get("content-type") || "";
  const payload = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg =
      (payload && typeof payload === "object" && (payload.error || payload.message)) ||
      `Request failed (${res.status})`;
    throw new ApiError(msg, { status: res.status, payload });
  }
  if (payload && typeof payload === "object" && payload.ok === false) {
    throw new ApiError(payload.error || "Request rejected", { status: res.status, payload });
  }
  return payload;
}

export const api = {
  get: (path, opts) => request(path, opts),
  post: (path, body, opts) => request(path, { ...opts, method: "POST", body }),

  /* ---- meta / state ---- */
  meta: () => request("/api/meta"),
  state: () => request("/api/state"),

  /* ---- profiles ---- */
  profiles: () => request("/api/profiles"),
  profile: (id) => request(`/api/profiles/${encodeURIComponent(id)}`),
  saveProfile: (body, id = null) =>
    request(id ? `/api/profiles/${encodeURIComponent(id)}` : "/api/profiles", {
      method: "POST",
      body,
    }),

  /* ---- facts ---- */
  facts: ({ profileId = "", state = "" } = {}) => {
    const q = new URLSearchParams();
    if (profileId) q.set("profile_id", profileId);
    if (state) q.set("state", state);
    const s = q.toString();
    return request(`/api/facts${s ? `?${s}` : ""}`);
  },
  decideFact: (factId, decision) =>
    request("/api/facts/decision", { method: "POST", body: { fact_id: factId, decision } }),
  bulkFacts: (decisions) =>
    request("/api/facts/bulk", { method: "POST", body: { decisions } }),

  /* ---- resume ---- */
  importResume: (body) => request("/api/resume/import", { method: "POST", body }),

  /* ---- resume builder (visual canvas) ---- */
  builderBootstrap: (profileId, applicationId = "", refresh = false) => {
    const q = new URLSearchParams({ profile_id: profileId });
    if (applicationId) q.set("application_id", applicationId);
    if (refresh) q.set("refresh", "1");
    return request(`/api/builder/bootstrap?${q}`);
  },
  builderList: (profileId) =>
    request(`/api/builder/list?profile_id=${encodeURIComponent(profileId)}`),
  builderSave: (body) => request("/api/builder/variant", { method: "POST", body }),
  builderTemplate: (body) => request("/api/builder/template", { method: "POST", body }),
  builderSuggest: (body) => request("/api/builder/suggest", { method: "POST", body }),
  builderApply: (body) => request("/api/builder/apply", { method: "POST", body }),
  builderExport: (body) => request("/api/builder/export", { method: "POST", body }),

  /* ---- jobs / matches / applications ---- */
  jobs: ({ limit = 60 } = {}) => request(`/api/jobs?limit=${limit}`),
  matches: (profileId = "") =>
    request(`/api/matches${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ""}`),
  applications: (profileId = "") =>
    request(`/api/applications${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ""}`),
  runs: (profileId = "") =>
    request(`/api/runs${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ""}`),
  quickAdd: (body) => request("/api/applications", { method: "POST", body }),
  assistedPackages: (applicationId = "") =>
    request(
      `/api/assisted-packages${applicationId ? `?application_id=${encodeURIComponent(applicationId)}` : ""}`,
    ),

  /* ---- pipeline actions ---- */
  discover: (limit = 30) => request("/api/discover", { method: "POST", body: { limit } }),
  match: (profileId, threshold = null) =>
    request("/api/match", {
      method: "POST",
      body: { profile_id: profileId, ...(threshold === null ? {} : { threshold }) },
    }),
  agentRun: (profileId, limit = 10) =>
    request("/api/agent/run", { method: "POST", body: { profile_id: profileId, limit } }),
  moveCard: (applicationId, toStatus) =>
    request("/api/board/move", {
      method: "POST",
      body: { application_id: applicationId, to_status: toStatus, at: new Date().toISOString() },
    }),

  /* ---- AI settings ---- */
  aiStatus: () => request("/api/ai/status"),
  aiSave: (body) => request("/api/settings/ai", { method: "POST", body }),
  aiTest: () => request("/api/ai/test", { method: "POST", body: {} }),
  localProbe: () => request("/api/ai/local-probe", { method: "POST", body: {} }),
  saveGeminiKey: (api_key) =>
    request("/api/settings/gemini-key", { method: "POST", body: { api_key } }),
  clearGeminiKey: () =>
    request("/api/settings/gemini-key", { method: "POST", body: { clear: true } }),
  diagnose: () => request("/api/system/diagnose"),

  /* ---- reports ---- */
  reportSummary: (profileId = "") =>
    request(`/api/reports/summary${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ""}`),
  reportPreview: ({ report = "applications", profileId = "", format = "csv" } = {}) => {
    const q = new URLSearchParams({ report, format });
    if (profileId) q.set("profile_id", profileId);
    return request(`/api/reports/preview?${q}`);
  },
  reportDownloadUrl: ({ report, format, profileId = "" } = {}) => {
    const q = new URLSearchParams({ report, format });
    if (profileId) q.set("profile_id", profileId);
    return `/api/reports/download?${q}`;
  },
};

export { ApiError };
export default api;
