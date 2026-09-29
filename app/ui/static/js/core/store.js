/* store.js — tiny observable state container shared by all routes. */

const initial = {
  snapshot: null, // server truth (kanban, counts, profiles, gemini)
  meta: null, // stages, columns, transitions, policies, report kinds
  profiles: [],
  activeProfileId: localStorage.getItem("noloop.profile") || "",
  ai: null, // /api/ai/status payload
  online: false,
  route: "dashboard",
  activity: [], // rolling feed of live events
  progress: new Map(), // job_id -> stage map (resume / agent / discover)
};

const state = { ...initial };
const subs = new Set();

export function get() {
  return state;
}

export function set(patch, reason = "update") {
  let changed = false;
  for (const [k, v] of Object.entries(patch)) {
    if (state[k] !== v) {
      state[k] = v;
      changed = true;
    }
  }
  if (changed) publish(reason);
}

export function subscribe(fn) {
  subs.add(fn);
  return () => subs.delete(fn);
}

export function publish(reason = "update") {
  for (const fn of [...subs]) {
    try {
      fn(state, reason);
    } catch (err) {
      console.error("[store] subscriber failed", err);
    }
  }
}

export function setActiveProfile(id) {
  state.activeProfileId = id || "";
  if (id) localStorage.setItem("noloop.profile", id);
  publish("profile");
}

/** Append one entry to the rolling activity feed (capped). */
export function pushActivity(entry, cap = 200) {
  state.activity.unshift(entry);
  if (state.activity.length > cap) state.activity.length = cap;
  publish("activity");
}

/** Merge a live `progress` event into the per-job stage map. */
export function applyProgress(evt) {
  if (!evt || !evt.job_id) return;
  const key = evt.job_id;
  const job = state.progress.get(key) || { job_id: key, kind: evt.kind, stages: [], byId: {} };
  job.kind = evt.kind || job.kind;
  job.label = evt.label || job.label;
  job.detail = evt.detail;
  job.status = evt.status;
  job.percent = typeof evt.progress === "number" ? evt.progress : job.percent || 0;
  job.updated = Date.now();

  if (evt.stage) {
    const existing = job.byId[evt.stage];
    if (existing) {
      Object.assign(existing, {
        status: evt.status || existing.status,
        detail: evt.detail || existing.detail,
        elapsed_ms: evt.elapsed_ms ?? existing.elapsed_ms,
        progress: evt.progress ?? existing.progress,
      });
    } else {
      const entry = {
        id: evt.stage,
        label: evt.label || evt.stage,
        detail: evt.detail || "",
        status: evt.status || "running",
        elapsed_ms: evt.elapsed_ms ?? null,
        progress: evt.progress ?? null,
      };
      job.byId[evt.stage] = entry;
      job.stages.push(entry);
    }
  }
  state.progress.set(key, job);
  publish("progress");
}

export function clearProgress(jobId) {
  state.progress.delete(jobId);
  publish("progress");
}

export default { get, set, subscribe, publish, setActiveProfile, pushActivity, applyProgress, clearProgress };
