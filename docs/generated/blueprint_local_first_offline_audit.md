# Blueprint Local-First Offline Audit

Overall status: `FUNCTIONAL`

## Summary

- Tenant-safe blueprints: 7
- Operator-only blueprints: 1
- Tenant-safe Blueprints missing full local-first manifests: 0
- Source probes passing: 6 / 6

## Source Probes

- `preview_emits_offline_readiness`: `PASS`
- `apply_persists_local_first_manifest`: `PASS`
- `rollback_invalidates_offline_manifest`: `PASS`
- `impact_scores_offline_risk`: `PASS`
- `tenant_ui_shows_offline_readiness`: `PASS`
- `server_seven_day_proof_exists`: `PASS`

## Blueprint Matrix

| Blueprint | Tenant safe | Status | Decision | Missing local-first fields |
| --- | --- | --- | --- | --- |
| `private-primary-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |
| `private-secondary-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |
| `cameroon-gce-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |
| `bilingual-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |
| `boarding-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |
| `international-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |
| `multi-campus-network` | `False` | `OPERATOR_ONLY` | `HIDE FROM TENANT` | None |
| `low-connectivity-school` | `True` | `FUNCTIONAL` | `ADAPT EXISTING` | None |

## Closed Gaps

- Added a first-class local-first manifest contract for tenant-safe Blueprints.
- Preview emits offline readiness, device-role impact, outage survival, conflict policy, and proof status.
- Apply persists the local-first manifest in tenant-scoped school settings and install snapshots.
- Rollback restores settings and reports offline manifest invalidation posture.
- Tenant Blueprint UI exposes offline readiness, cached surfaces, queued actions, device roles, and proof status.

## Recommended Follow-On

- Replace PARTIAL browser proof status after a real browser restart/storage-pressure harness passes.
- Wire device manifest version bumps to the client sync runtime when that endpoint is available.
- Add per-blueprint browser screenshots for the tenant Blueprint UI after deployment.
