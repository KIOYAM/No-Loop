/* grapesjs_loader.js — load the vendored GrapesJS editor, once, offline.
 *
 * GrapesJS (0.23.6) and grapesjs-preset-newsletter (1.0.2) are BSD-3-Clause
 * packages pulled from npm tarballs and committed under /vendor/grapesjs by
 * scripts/vendor_grapesjs.ps1 — no CDN, no npm install, no build step. They are
 * injected only while the builder route is open and their stylesheet is dropped
 * again on the way out, so every other page stays exactly as light as before.
 */

const CSS_HREF = "/vendor/grapesjs/grapes.min.css";
const CSS_ID = "nl-grapesjs-css";
const CORE_JS = "/vendor/grapesjs/grapes.min.js";
const PRESET_JS = "/vendor/grapesjs/preset-newsletter.min.js";

let loading = null;

function ensureCss() {
  if (document.getElementById(CSS_ID)) return;
  const link = document.createElement("link");
  link.id = CSS_ID;
  link.rel = "stylesheet";
  link.href = CSS_HREF;
  document.head.append(link);
}

function loadScript(src, isReady) {
  if (isReady()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = false; // keep core before the preset even without await
    script.onload = () => resolve();
    script.onerror = () => {
      script.remove();
      reject(new Error(`Could not load ${src}`));
    };
    document.head.append(script);
  });
}

/** The preset's default export: `fn(editor, opts)` (UMD namespace object). */
export function presetPlugin() {
  const mod = window["grapesjs-preset-newsletter"];
  if (typeof mod === "function") return mod;
  if (mod && typeof mod.default === "function") return mod.default;
  if (mod && typeof mod.plugin === "function") return mod.plugin;
  return null;
}

/** Resolves with the GrapesJS namespace; injecting the scripts only once. */
export function loadGrapesJS() {
  ensureCss();
  if (!loading) {
    loading = (async () => {
      await loadScript(CORE_JS, () => !!window.grapesjs);
      await loadScript(PRESET_JS, () => !!presetPlugin());
      if (!window.grapesjs) throw new Error("GrapesJS did not register a global");
      return window.grapesjs;
    })();
    loading.catch(() => {
      loading = null; // a failed load may be retried on the next visit
    });
  }
  return loading;
}

/** Drop the editor stylesheet again; the scripts stay cached for next time. */
export function unloadGrapesJS() {
  const link = document.getElementById(CSS_ID);
  if (link) link.remove();
}
