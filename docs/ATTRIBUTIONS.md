# ATTRIBUTIONS.md — External Code Adoption Registry (append-only)

This file records every adaptation of external code into No_Loop (R-TRUTH-6; CODING_STANDARDS.md §11). **Append-only**: entries are never deleted or edited; corrections are added as new entries referencing the old one.

No_Loop code is otherwise original. Ideas and architectural patterns studied from reference repositories do not require entries here — only *code* (snippets, functions, algorithms transcribed or minimally adapted) does.

## Entry template

```
### ATTR-<n>: <short title>
- Date: YYYY-MM-DD
- Source: <repo URL or page URL> @ <commit/branch>
- License: <MIT | Apache-2.0 | BSD-... | other-approved> (verified in .references/PROVENANCE.md or primary source)
- No_Loop files: <paths>
- Attribution in code: yes/no (file:line)
- What was adapted vs. rewritten: <description>
- Security review: LOOP-9 items 2/4/5/11 checked on <date> by <agent/person>
- Tests covering the adapted code: <test names>
```

---

## Registry

*(empty — no external code has been adopted yet; all No_Loop code is original)*

---

## Pre-approved sources (per .references/PROVENANCE.md, 2026-09-28)

| Source | Verdict | Snippet policy |
|---|---|---|
| Gsync/jobsync @ ef3d7ee | MIT | Allowed with entry + in-code attribution |
| SamlyticsDS/jobmatch-ai @ ccd2099 | MIT | Allowed with entry + in-code attribution |
| AbhishekMandapmalvi/AutoApply @ 053071b | MIT | Allowed with entry + in-code attribution |
| attdobi/aipply @ 9f90c1d | none found | Ideas-only — no code adoption |
| wadekarg/JobMatchAI @ 1c8d8c4 | none found | Ideas-only — no code adoption |
| ScottCoffin/Job_Scraper @ 72e5c64 | AGPL-3.0 | **Never adopt code — ideas-only, permanently** |
| Vigneshyadala/ai-job-application-bot @ 085f8db | none found | Ideas-only — no code adoption |
| dsharm9148/job-apply-bot @ 0808cb6 | none found | Ideas-only — no code adoption |
