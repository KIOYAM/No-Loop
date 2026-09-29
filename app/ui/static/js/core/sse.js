/* sse.js — the ONLY live channel. The browser never polls for state. */

const RETRY_MS = 2500;

class Bus {
  constructor() {
    this.listeners = new Map(); // event -> Set<fn>
    this.status = "idle"; // idle | live | retry
    this.source = null;
    this.attempt = 0;
    this._reconnector = null;
  }

  on(event, fn) {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event).add(fn);
    return () => this.off(event, fn);
  }

  off(event, fn) {
    const set = this.listeners.get(event);
    if (set) set.delete(fn);
  }

  emit(event, payload) {
    const set = this.listeners.get(event);
    if (set) for (const fn of [...set]) {
      try {
        fn(payload);
      } catch (err) {
        console.error("[sse] listener failed", event, err);
      }
    }
    const anySet = this.listeners.get("*");
    if (anySet) for (const fn of [...anySet]) fn(event, payload);
  }

  _setStatus(next) {
    if (this.status === next) return;
    this.status = next;
    this.emit("status", next);
  }

  connect() {
    if (this.source) return;
    this._setStatus(this.attempt === 0 ? "idle" : "retry");
    const es = new EventSource("/api/events");
    this.source = es;

    es.onopen = () => {
      this.attempt = 0;
      this._setStatus("live");
    };

    es.onerror = () => {
      // EventSource retries by itself, but if the server restarted it stays
      // dead — close and rebuild with a short backoff.
      es.close();
      this.source = null;
      this.attempt += 1;
      this._setStatus("retry");
      clearTimeout(this._reconnector);
      this._reconnector = setTimeout(() => this.connect(), RETRY_MS * Math.min(this.attempt, 4));
    };

    for (const name of [
      "state_changed",
      "settings_changed",
      "progress",
      "task_done",
      "auth_required",
    ]) {
      es.addEventListener(name, (e) => {
        let data = e.data;
        try {
          data = JSON.parse(e.data);
        } catch {
          /* keep raw string */
        }
        this.emit(name, data);
      });
    }
  }

  close() {
    clearTimeout(this._reconnector);
    if (this.source) this.source.close();
    this.source = null;
    this._setStatus("idle");
  }
}

export const sse = new Bus();
export default sse;
