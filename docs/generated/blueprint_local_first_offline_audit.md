# Blueprint Local-First Offline Audit

Overall status: `FUNCTIONAL`

## Summary

- Tenant-safe blueprints: 7
- Operator-only blueprints: 1
- Tenant-safe Blueprints missing full local-first manifests: 0
- Tenant-safe Blueprints missing composition fields: 0
- Source probes passing: 10 / 10

## Source Probes

- `preview_emits_offline_readiness`: `PASS`
- `apply_persists_local_first_manifest`: `PASS`
- `rollback_invalidates_offline_manifest`: `PASS`
- `impact_scores_offline_risk`: `PASS`
- `tenant_ui_shows_offline_readiness`: `PASS`
- `server_seven_day_proof_exists`: `PASS`
- `tenant_blueprint_template_string_warning_safe`: `PASS`
- `tenant_blueprint_template_no_warning_code_lookup`: `PASS`
- `tenant_launch_settings_cta_uses_tenant_configuration`: `PASS`
- `tenant_app_catalog_route_exists`: `PASS`

## Blueprint Matrix

| Blueprint | Tenant safe | Role | Tracks | App recommendations | Status | Missing fields |
| --- | --- | --- | --- | --- | --- | --- |
| `private-primary-school` | `True` | `base` | general, faith_based, remedial_support | parent-communication, attendance-recovery, fee-reminder | `FUNCTIONAL` | None |
| `private-secondary-school` | `True` | `base` | general, technical_vocational, science, arts, commercial | grade-moderation, department-performance, discipline-escalation | `FUNCTIONAL` | None |
| `cameroon-gce-school` | `True` | `regional_overlay` | general, technical_vocational, science, arts, commercial | exam-registration, report-validation, manual-payment-reconciliation | `FUNCTIONAL` | None |
| `bilingual-school` | `True` | `specialty_overlay` | general, dual_language, regional_language_support | language-specific-announcements, report-translation-checks | `FUNCTIONAL` | None |
| `boarding-school` | `True` | `specialty_overlay` | general, boarding_welfare | leave-request, incident-escalation, boarding-operations | `FUNCTIONAL` | None |
| `international-school` | `True` | `base` | international_curriculum, general, language_pathways | document-review, curriculum-transition, admissions-pipeline | `FUNCTIONAL` | None |
| `multi-campus-network` | `False` | `operator_network` | network_operations | None | `OPERATOR_ONLY` | None |
| `low-connectivity-school` | `True` | `offline_overlay` | general, technical_vocational, low_connectivity | conflict-review, manual-payment-reconciliation, offline-readiness | `FUNCTIONAL` | None |

## Closed Gaps

- Added a first-class local-first manifest contract for tenant-safe Blueprints.
- Preview emits offline readiness, device-role impact, outage survival, conflict policy, and proof status.
- Apply persists the local-first manifest in tenant-scoped school settings and install snapshots.
- Rollback restores settings and reports offline manifest invalidation posture.
- Tenant Blueprint UI exposes offline readiness, cached surfaces, queued actions, device roles, and proof status.
- Tenant Blueprint UI safely renders string warnings from external dependency blockers.
- Launch Studio school/region CTA now targets tenant configuration instead of the backend dashboard.
- Blueprint preview exposes composition guidance for base models, overlays, tracks, local constraints, and tenant app catalog recommendations.

## Recommended Follow-On

- Replace PARTIAL browser proof status after a real browser restart/storage-pressure harness passes.
- Wire device manifest version bumps to the client sync runtime when that endpoint is available.
- Add per-blueprint browser screenshots for the tenant Blueprint UI after deployment.
- Add a multi-select Blueprint composition planner so tenants can preview base + regional + offline + specialty overlays as one combined change set before apply.
- Add country-specific Blueprint fixtures for regional calendars, grading variants, vocational programs, and compliance constraints.
