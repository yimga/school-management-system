# Tenant lifecycle code-truth inventory

Generated: `2026-06-09T16:58:36.256449+00:00`

## Canonical engines

- **provisioning_execution**: `apps/schools/tasks.py::_do_provision`
- **provisioning_progress**: `apps/schools/provisioning_progress.py`
- **operational_lifecycle**: `apps/lifecycle/unified_lifecycle.py`
- **offboarding_execution**: `apps/schools/tenant_offboarding.py`
- **post_provision_config**: `apps/setup_studio/wizard_engine.py`
- **growth_retention_readonly**: `apps/platform_runtime/tenant_lifecycle_engine.py`
- **lifecycle_notifications**: `apps/platform_runtime/tenant_lifecycle_notifications.py`

## Test module counts

- lifecycle: **9**
- setup_studio: **14**
- schools_provision: **6**
- schools_offboard: **6**
- schools_signup: **12**
- platform_runtime_lifecycle: **6**

## Verifier scripts

- `scripts/audit_tenant_lifecycle_aggressive.py`
- `scripts/audit_tenant_lifecycle_full.py`
- `scripts/audit_tenant_lifecycle_workflows.py`
- `scripts/generate_tenant_lifecycle_architecture_deduplication_audit.py`
- `scripts/generate_tenant_lifecycle_code_truth_inventory.py`
- `scripts/generate_tenant_lifecycle_completion_audits.py`
- `scripts/generate_tenant_lifecycle_forensic_gap_audit.py`
- `scripts/verify_tenant_control_plane_rbac.py`
- `scripts/verify_tenant_email_delivery_cascade.py`
- `scripts/verify_tenant_experience_competitor_gap_closure.py`
- `scripts/verify_tenant_identity_hub.py`
- `scripts/verify_tenant_launch_sla.py`
- `scripts/verify_tenant_lifecycle_10x.py`
- `scripts/verify_tenant_lifecycle_completion.py`
- `scripts/verify_tenant_lifecycle_unified.py`
- `scripts/verify_tenant_offboarding_surface.py`
- `scripts/verify_tenant_onboarding_csv_import.py`
- `scripts/verify_tenant_owned_model_adoption_scaffold.py`
- `scripts/verify_tenant_platform_vectors.py`
- `scripts/verify_tenant_portal_list_pagination.py`
- `scripts/verify_tenant_provision_progress_surface.py`
- `scripts/verify_tenant_rag_bundles.py`
- `scripts/verify_tenant_resolution_cache_keys.py`
- `scripts/verify_tenant_schema_app_registration.py`
- `scripts/verify_tenant_scoping_burndown.py`
- `scripts/verify_tenant_sovereignty_pillar.py`
- `scripts/verify_tenant_studio_day1_contract.py`

## Setup Studio wizards

- JSON wizard count: **36**
