/* i18n.js — EN is complete; TA/HI exist as stubs so switching later is data-only.
 * Usage:  t("nav.dashboard")  →  "Dashboard"
 *         t("resume.stages.upload", { file: "cv.pdf" })
 * Unknown keys fall back to the key itself (visible, never a blank UI).
 */

const en = {
  "shell.privacy": "Local-only · 127.0.0.1 · your data never leaves this machine",
  "shell.loading": "Loading…",
  "shell.retry": "Retry",
  "shell.close": "Close",
  "shell.save": "Save",
  "shell.cancel": "Cancel",
  "shell.delete": "Delete",
  "shell.create": "Create",
  "shell.confirm": "Confirm",
  "shell.reject": "Reject",
  "shell.edit": "Edit",
  "shell.copy": "Copy",
  "shell.copied": "Copied",
  "shell.download": "Download",
  "shell.none": "None",
  "shell.all": "All",
  "shell.search": "Search",
  "shell.of": "of",
  "shell.optional": "optional",
  "shell.required": "required",

  "nav.dashboard": "Dashboard",
  "nav.resume": "Resume",
  "nav.profile": "Profile",
  "nav.jobs": "Jobs",
  "nav.pipeline": "Pipeline",
  "nav.reports": "Reports",
  "nav.settings": "Settings",

  "theme.light": "Light",
  "theme.dark": "Dark",
  "theme.toggle": "Switch theme",

  "live.connecting": "connecting…",
  "live.on": "live",
  "live.retry": "reconnecting…",
  "live.off": "offline",

  "activity.title": "Activity",
  "activity.clear": "Clear",
  "activity.empty": "Nothing yet — start a resume import, discovery or agent run.",

  "dashboard.title": "Dashboard",
  "dashboard.sub": "Your job-search command centre, updated live over SSE.",
  "dashboard.kpi.applications": "Applications",
  "dashboard.kpi.companies": "Companies",
  "dashboard.kpi.submitted": "Submitted",
  "dashboard.kpi.review": "Needs review",
  "dashboard.kpi.facts": "Confirmed facts",
  "dashboard.kpi.runs": "Agent runs",
  "dashboard.pipeline": "Pipeline health",
  "dashboard.quick": "Quick actions",
  "dashboard.empty": "No applications yet",
  "dashboard.emptyBody": "Import a resume, discover jobs, then run the assisted agent.",
  "dashboard.recent": "Recent applications",
  "dashboard.policies": "Platform policy",

  "resume.title": "Resume import",
  "resume.sub": "Deterministic parse first (instant), one bounded AI pass second.",
  "resume.drop": "Drop a resume here, or click to browse",
  "resume.dropHint": "PDF · DOCX · TXT — up to 10 MB, read entirely on this machine",
  "resume.orPaste": "…or paste the text",
  "resume.pastePlaceholder": "Paste your resume text here",
  "resume.useAi": "Run the optional AI pass",
  "resume.useAiHint": "One bounded request (15 s timeout). Failure is reported, never fatal.",
  "resume.start": "Import resume",
  "resume.running": "Importing…",
  "resume.stages": "Live stages",
  "resume.done": "Import complete",
  "resume.failed": "Import failed",
  "resume.facts": "facts created",
  "resume.aiFacts": "from AI",
  "resume.duration": "took",
  "resume.pickProfile": "Choose a profile first",
  "resume.recent": "Previous imports",
  "resume.noVersions": "No imports yet for this profile.",

  "profile.title": "Profile",
  "profile.sub": "Everything the agent needs. Fields fill from your resume; you always have the last word.",
  "profile.create": "New profile",
  "profile.createTitle": "Create a profile",
  "profile.createSub": "Profiles scope every job, fact and application.",
  "profile.name": "Profile name",
  "profile.nameHint": "e.g. “Python Developer” or “ML Engineer”",
  "profile.contact": "Contact",
  "profile.targeting": "Targeting",
  "profile.limits": "Application limits",
  "profile.limitsHint": "No defaults by design — the queue stays disabled until every limit is set.",
  "profile.perDay": "Per day",
  "profile.perWeek": "Per week",
  "profile.threshold": "Match threshold",
  "profile.cooldown": "Company cooldown (days)",
  "profile.hours": "Active hours",
  "profile.roles": "Target roles",
  "profile.locations": "Target locations",
  "profile.workMode": "Work mode",
  "profile.excluded": "Excluded companies",
  "profile.extra": "From your resume",
  "profile.facts": "Facts",
  "profile.factsHint": "Nothing is treated as true until you confirm it.",
  "profile.confirmAll": "Confirm all shown",
  "profile.versions": "Resume versions",
  "profile.saved": "Profile saved",
  "profile.autofill": "Auto-filled from resume",
  "profile.empty": "No profile yet",

  "jobs.title": "Jobs",
  "jobs.sub": "Discovered postings, de-duplicated across sources.",
  "jobs.discover": "Discover jobs",
  "jobs.discovering": "Discovering…",
  "jobs.limit": "How many",
  "jobs.empty": "No jobs discovered yet",
  "jobs.emptyBody": "Pull a fresh batch from the public feed. Everything is stored locally.",
  "jobs.match": "Score against profile",
  "jobs.matching": "Scoring…",
  "jobs.score": "Fit",
  "jobs.salary": "Salary",
  "jobs.posted": "Posted",
  "jobs.source": "Source",

  "pipeline.title": "Pipeline",
  "pipeline.sub": "Live view of every application and the assisted agent run.",
  "pipeline.board": "Board",
  "pipeline.agent": "Agent run",
  "pipeline.run": "Run agent",
  "pipeline.running": "Running…",
  "pipeline.runLimit": "Jobs to consider",
  "pipeline.steps": "Agent steps",
  "pipeline.history": "Run history",
  "pipeline.add": "Quick add",
  "pipeline.addTitle": "Record an application",
  "pipeline.addSub": "Manual entries start at Review — nothing is ever auto-submitted.",
  "pipeline.empty": "The board is empty",
  "pipeline.emptyBody": "Discover jobs, score them, then run the assisted agent.",
  "pipeline.blocked": "Queue blocked",
  "pipeline.blockedBody": "Set application limits on your profile before the agent can run.",
  "pipeline.evidence": "Evidence",
  "pipeline.artifacts": "Artifacts",

  "reports.title": "Reports",
  "reports.sub": "Downloadable, shareable output — assembled locally, nothing uploaded.",
  "reports.kind": "Report",
  "reports.format": "Format",
  "reports.preview": "Preview",
  "reports.download": "Download",
  "reports.submitted": "Submitted",
  "reports.runsTitle": "Agent runs",
  "reports.summary": "Summary",
  "reports.rows": "rows",
  "reports.applications": "Applications",
  "reports.companies": "Companies",
  "reports.runs": "Agent runs",
  "reports.facts": "Fact ledger",
  "reports.empty": "Nothing to report yet",

  "nav.builder": "Builder",

  "builder.title": "Resume builder",
  "builder.sub": "Drag, retype and restyle the resume itself. Every change is yours — the AI only proposes.",
  "builder.noProfile": "Pick a profile first",
  "builder.noProfileBody": "The canvas is built from one profile's confirmed facts. Choose a profile in the sidebar, then reload.",
  "builder.appLabel": "Tailor for application",
  "builder.appNone": "This profile (no application)",
  "builder.appUntitled": "Untitled role",
  "builder.save": "Save",
  "builder.export": "Export",
  "builder.engineFailed": "The editor engine could not start.",
  "builder.tabAi": "Propose",
  "builder.tabStructure": "Structure",
  "builder.ats": "ATS",
  "builder.atsHint": "Keyword overlap with the selected job description",
  "builder.overrides": "{n} of your edits saved",
  "builder.overridesNone": "Matches your facts",
  "builder.ai": "AI",
  "builder.pending": "{n} unconfirmed facts",
  "builder.pendingHint": "Confirm them in Profile so the builder can quote them",
  "builder.saving": "Saving…",
  "builder.saved": "Saved",
  "builder.savedAt": "Saved {time}",
  "builder.unsaved": "Unsaved changes",
  "builder.saveError": "Save failed — check the server log",
  "builder.blocksCategory": "Resume",
  "builder.focus": "Focus",
  "builder.focusPlaceholder": "Focus, e.g. leadership, migrations…",
  "builder.suggest": "Suggest",
  "builder.suggestFailed": "Could not get suggestions",
  "builder.proposeOnly": "Proposals only: nothing changes until you click Apply.",
  "builder.localHint": "No AI key configured — suggestions come from the local rule-based analysis.",
  "builder.modeAi": "AI proposal",
  "builder.modeLocal": "Local analysis",
  "builder.dropped": "{n} rejected by the grounding gate",
  "builder.noSuggestions": "Nothing worth changing right now.",
  "builder.kind.rewrite": "Rewrite",
  "builder.kind.reorder": "Reorder",
  "builder.kind.drop": "Remove",
  "builder.kind.add_section": "Add section",
  "builder.kind.style": "Style",
  "builder.kind.ats": "ATS",
  "builder.kind.confirm": "Confirm",
  "builder.priority": "P{n}",
  "builder.apply": "Apply",
  "builder.highlight": "Show in canvas",
  "builder.dismiss": "Dismiss",
  "builder.notInCanvas": "{path} is not on the canvas",
  "builder.applied": "Applied to {path} — saved as your decision",
  "builder.applyFailed": "Could not apply that suggestion",
  "builder.sections": "Sections",
  "builder.structureHint": "Drag a section on the canvas, or reorder it here. The order is what every export uses. The canvas is rebuilt from your profile on every visit: text with no fact behind it does not come back — confirm the fact in Profile to make new content permanent.",
  "builder.selection": "Selection",
  "builder.selectionHint": "Bound fields write back to the resume; unbound text stays in the HTML export only.",
  "builder.noSelection": "Click something on the canvas.",
  "builder.unbound": "Unbound (structural text)",
  "builder.exportHint": "PDF, DOCX and plain text are built from your confirmed facts plus your saved edits; HTML is built from this canvas.",
  "builder.noSections": "No sections on the canvas yet.",
  "builder.moveUp": "Move up",
  "builder.moveDown": "Move down",
  "builder.format": "Format",
  "builder.fmtHtml": "HTML — exactly what you see",
  "builder.fmtPdf": "PDF — facts + your edits",
  "builder.fmtDocx": "DOCX — facts + your edits",
  "builder.fmtText": "Plain text (ATS)",
  "builder.cancel": "Cancel",
  "builder.download": "Download",
  "builder.exportNote": "Nothing is uploaded: the file is assembled on this machine and downloaded straight from it.",
  "builder.exported": "{name} ({bytes} bytes)",
  "builder.exportFailed": "Export failed",
  "builder.section.header": "Header",
  "builder.section.summary": "Summary",
  "builder.section.skills": "Skills",
  "builder.section.experience": "Experience",
  "builder.section.projects": "Projects",
  "builder.section.education": "Education",
  "builder.section.certifications": "Certifications",

  "settings.title": "Settings",
  "settings.sub": "AI providers, this machine, and privacy — all local.",
  "settings.ai": "AI provider",
  "settings.provider": "Active provider",
  "settings.providerAuto": "Auto (best available)",
  "settings.gemini": "Google Gemini",
  "settings.local": "Local model",
  "settings.rule": "Rule-based (no AI)",
  "settings.key": "API key",
  "settings.keyHint": "Stored in your OS credential store or a local secrets file. Write-only from the browser.",
  "settings.saveKey": "Save key",
  "settings.clearKey": "Remove key",
  "settings.model": "Model",
  "settings.endpoint": "Endpoint or path",
  "settings.endpointHint": "An OpenAI-compatible base URL, or a .gguf / model directory on disk.",
  "settings.localModel": "Model name",
  "settings.localModelHint": "e.g. qwen3:4b — must match what your local server serves.",
  "settings.test": "Test connection",
  "settings.testing": "Testing…",
  "settings.probe": "Probe local server",
  "settings.optionalKey": "Local API key (optional)",
  "settings.hardware": "This machine",
  "settings.suggestion": "Suggested local model",
  "settings.suggestionNote": "Suggestion only — No_Loop never installs anything.",
  "settings.privacy": "Privacy",
  "settings.language": "Language",
  "settings.appearance": "Appearance",
  "settings.saved": "Settings saved",
  "settings.notConfigured": "Not configured — the rule-based fallback is active and fully functional.",

  "err.network": "Cannot reach the local No_Loop server",
  "err.unknown": "Something went wrong",
};

/* Transliterated stubs: keys exist so a future translator only fills values. */
const ta = { ...en, "nav.dashboard": "டாஷ்போர்டு", "nav.settings": "அமைப்புகள்" };
const hi = { ...en, "nav.dashboard": "डैशबोर्ड", "nav.settings": "सेटिंग्स" };

const CATALOGS = { en, ta, hi };
export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ta", label: "தமிழ்" },
  { code: "hi", label: "हिन्दी" },
];

let current = localStorage.getItem("noloop.lang") || "en";
if (!CATALOGS[current]) current = "en";

export function lang() {
  return current;
}

export function setLang(code) {
  if (!CATALOGS[code]) return;
  current = code;
  localStorage.setItem("noloop.lang", code);
  document.documentElement.lang = code;
  document.dispatchEvent(new CustomEvent("langchange", { detail: code }));
}

/** Translate `key`, interpolating `{name}` placeholders from `vars`. */
export function t(key, vars) {
  const table = CATALOGS[current] || en;
  let out = table[key] ?? en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  }
  return out;
}

/** Apply t() to every [data-i18n] node in `root`. */
export function applyI18n(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.getAttribute("data-i18n"));
  }
  for (const node of root.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", t(node.getAttribute("data-i18n-placeholder")));
  }
}

export default t;
