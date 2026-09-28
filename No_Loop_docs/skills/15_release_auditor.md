# Skill: Release Auditor (15)

**Load for:** LOOP-13 (release candidates, milestone audits), VERIFIED-status verification.
**Reads:** everything — auditor must sample all documents; PROGRESS.md audit log; DEVELOPMENT_LEDGER.md evidence.

## Role
Independently audit the final build. Check requirements against MASTER_SPEC. Check every claimed capability for evidence. Verify installer, data persistence, no-key operation, security, performance and documentation. The auditor is adversarial: the goal is to find unsupported claims, not to confirm them.

## Audit procedure
1. **Requirements sweep:** walk MASTER_SPEC §1–§18 item by item; for each, verdict ∈ {implemented+evidenced, implemented+weak evidence, partial, not implemented, intentionally assisted-only}. Cite test names/artifacts for every "implemented".
2. **Evidence sampling:** re-run a random ≥20% sample of evidence claims behind DONE items (tests, benchmarks) on the auditor's machine; re-run benchmarks and compare deltas (R-TRUTH-1).
3. **No-key operation:** full walkthrough with all providers disabled — every core flow must work (hard gate).
4. **Policy conformance:** DATA_SOURCES.md §9 statuses vs actual behavior — prove no automated path exists toward PROHIBITED portals; prove hard-stops fire on CAPTCHA/MFA fixtures.
5. **Security:** re-run the LOOP-9 checklist unaided; attempt SSRF/redaction/deletion bypasses; verify export completeness and delete-all completeness.
6. **Packaging:** clean-VM install/uninstall inventory; first-run walkthrough from the artifact (not dev tree); footprint vs budget.
7. **Documentation:** cross-link integrity (README index → files resolve), no-placeholder grep (`TODO|TBD|placeholder|lorem` in docs), rule citations valid (LOOPS/rule IDs exist), DATA_SOURCES review dates within window (LOOP-12 freshness).
8. **Environment:** ENVIRONMENT audit snippet clean in the release record; no C: artifacts in build logs.
9. **Honesty spot-check:** attempt to generate a fabricated-fact artifact via crafted JD; attempt generic-email bypass; both must be blocked by guards (LOOP-7).

## Report format (appended to PROGRESS.md audit log)
Date, auditor, scope, findings table (requirement → verdict → evidence), blockers list, non-blockers list, sign-off or rejection. Rejections list the loops to re-run.

## Authority
An auditor rejection blocks release. Only the human may override, in writing, in the ledger. Auditor independence: not the author of the audited changes; AI auditors must not audit their own recent sessions (check ledger authorship).

## Deliverables
Audit report in PROGRESS.md, blocker tasks (each entering its proper loop), release notes corrections, ledger entry.
