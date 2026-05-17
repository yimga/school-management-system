# Tenant Scoping Allowlist Burndown Plan

**Date opened:** 2026-05-17
**Owner:** Platform engineering
**Tracking:** [`var/security-audit-baseline-tenant-isolation.json`](../var/security-audit-baseline-tenant-isolation.json)
**Verifier:** [`scripts/verify_tenant_scoping_burndown.py`](../scripts/verify_tenant_scoping_burndown.py)
**SOT batch:** 1258 (2026-05-17), 12-pillar audit P3 follow-up.

## Context

`scripts/scan_tenant_queryset_safety.py` enforces the tenant-isolation invariant: every queryset on a school-scoped model must carry a `school=` / `school_id=` / `school__isnull=` filter, OR an explicit `# tenant-isolation-allow: <reason>` marker on the call site. The current baseline is **0** allowlisted call sites (batch **1267**, 2026-05-17).

The seven-pillar audit (P3) called this baseline "a burndown target, not a silence." That framing is correct, but no schedule existed. This document is the schedule.

## Goal

Reduce the baseline from **726** at audit open to **0** by the end of Q2 2027. Batch **1267** met the **0** ceiling in-repo (scanner count); ongoing work replaces markers with real `school=` filters per code review.

> Companion gate: [`scripts/scan_tenant_isolation_marker_quality.py`](../scripts/scan_tenant_isolation_marker_quality.py) audits the **reason string** on every `# tenant-isolation-allow:` marker. The forward-progress gate (this doc) lowers the *count*; the marker-quality gate prevents new lazy reasons. Together they close the "lazy marker" anti-pattern the verifier alone cannot detect.

## Per-quarter targets

Targets are expressed as the **maximum allowed count** by the date column. The verifier reads the active target and fails when the current scanner result exceeds it.

| Quarter ending | Target ceiling | Reduction vs. prior | Focus apps |
|---|---|---|---|
| 2026-08-31 (Q3 2026) | **626** | −100 | `apps/evals/` (118), `apps/portal/` (80) — highest concentration |
| 2026-11-30 (Q4 2026) | **476** | −150 | `apps/accounts/` (69), `apps/schools/` (66), `apps/api/` (63) — auth + tenant boundary code |
| 2027-02-28 (Q1 2027) | **276** | −200 | `apps/finance/` (55), `apps/analytics/` (50), `apps/reports/` (39), `apps/siteconfig/` (35) — money + analytics + config |
| 2027-05-31 (Q2 2027) | **0** | −276 | All remaining apps (`academics`, `platform_runtime`, `migration_cloud`, `people`, `communication`, `marketplace`, and the long tail) |

## How a sprint reduces the count

A typical retirement of N findings follows this loop:

1. Pick an app with high concentration (use `python scripts/scan_tenant_queryset_safety.py --json | python -c "..."` to group by app).
2. For each finding in that file: either
   - **(a) Add a real `school=` filter.** Most common — the query was scoping-by-convention via the surrounding view's tenant context but never expressed in the ORM call. Adding `school=request.school` (or the equivalent in services) eliminates the finding and improves tenant isolation.
   - **(b) Convert the implicit allowlist into an explicit per-call-site `# tenant-isolation-allow: <reason>` marker.** Use when the query is legitimately cross-tenant (platform admin reports, scheduling solver, background sweepers). The reason string must describe **why**, not just acknowledge the marker.
3. Re-run `scan_tenant_queryset_safety.py`; baseline drops.
4. Update `var/security-audit-baseline-tenant-isolation.json` to the new count.
5. Update the CLAUDE.md scanner-table integer to match.
6. Mention in the SOT §11.4 batch row for the wave that landed the reduction.

## How `verify_tenant_scoping_burndown.py` gates CI

The verifier reads the **current JSON baseline `finding_count`** and compares it to the **active quarterly target** (the first row in the table above whose date is ≥ today). When the date column is in the past it picks the next row; the target sticks until the next quarterly boundary.

```bash
python scripts/verify_tenant_scoping_burndown.py             # text summary, exit 0 if on-track
python scripts/verify_tenant_scoping_burndown.py --strict    # exit 1 if behind target
python scripts/verify_tenant_scoping_burndown.py --json
```

CI runs `--strict` once per week (or per merge to main, operator choice). The verifier is intentionally NOT in the per-PR `architectural-boundaries.yml` matrix — that workflow already runs `scan_tenant_queryset_safety --compare` which catches new regressions. The quarterly verifier is the **forward-progress** gate, distinct from the per-PR regression gate.

## Honest carve-outs

- The forward-progress verifier can't tell whether a marker is "honest" (real cross-tenant query) or "lazy" (developer added the marker instead of fixing the query). The companion marker-quality scanner ([`scan_tenant_isolation_marker_quality.py`](../scripts/scan_tenant_isolation_marker_quality.py)) now catches the most common lazy patterns (empty reasons, "TODO" / "fix later" / "see above" / under-8-char strings, single-word generic placeholders). Anything subtler than that — e.g. a plausible-sounding reason that isn't actually true — still needs code review of the marker on the PR that introduced it.
- The schedule assumes ~1 engineer-week per 25-finding reduction at current code shape. If that velocity proves wrong, **renegotiate the target ceilings here, do NOT silently miss them.** The verifier failing is the contract.
- The "platform_runtime" + "migration_cloud" tails contain the highest concentration of legitimately-cross-tenant code (operator-only registries, ETL bundles); the final quarter's −276 target may need a smaller-than-zero final ceiling if those rows resist reduction. That decision goes in the SOT batch when Q2 2027 lands, not now.

## Related artifacts

- Scanner: [`scripts/scan_tenant_queryset_safety.py`](../scripts/scan_tenant_queryset_safety.py)
- Baseline JSON: [`var/security-audit-baseline-tenant-isolation.json`](../var/security-audit-baseline-tenant-isolation.json)
- CI gate: `.github/workflows/tenant-isolation-scan.yml` (regression gate) + this verifier (forward-progress gate)
- CLAUDE.md scanner table row (drift gate)
