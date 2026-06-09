# Tenant lifecycle forensic gap audit

Findings: **8**

## PROV-001 — WorkflowRun invisible during sync provision (fake 5% progress) (critical, done)
- Scope: repo-side
- Files: `apps/schools/tasks.py`
- Fix: Remove outer atomic from provision_school_sync and provision_school_task; pulse steps commit incrementally.

## PROV-002 — Pending tenant setup UX showed wrong CTAs and blank progress (high, done)
- Scope: repo-side
- Files: `templates/schools/tenant_setup_in_progress.html, apps/schools/pending_tenant_discovery.py`
- Fix: Minimal shell, gated buttons, background kick, inline rmc_tenant_provision_progress.

## PROV-003 — 14-step provisioning progress model not fully mapped to UI labels (medium, done)
- Scope: repo-side
- Files: `apps/schools/provisioning_progress.py, apps/platform_runtime/workflow_registry.py`
- Fix: resolve_provisioning_progress exposes extended_steps (14) alongside 5-step WorkflowRun train.

## NOTIF-001 — Lifecycle notification idempotency scattered (medium, done)
- Scope: repo-side
- Files: `apps/platform_runtime/tenant_lifecycle_notifications.py, apps/schools/signup_completion_notifications.py, apps/schools/tenant_offboarding_notifications.py`
- Fix: tenant_lifecycle_notifications facade with delivery status + school.settings lifecycle_notifications.

## ARCH-001 — Three lifecycle state vocabularies (intentional separation) (low, documented)
- Scope: repo-side
- Files: `apps/lifecycle/unified_lifecycle.py, apps/platform_runtime/tenant_lifecycle_engine.py, apps/platform_runtime/tenant_lifecycle_state_machine.py`
- Fix: Keep unified_lifecycle as operational SOT; growth layers read-only.

## ENV-001 — Schema-per-tenant purge proof requires Postgres + django-tenants (medium, blocked_external)
- Scope: environment
- Files: `apps/compliance/tenant_offboarding_inventory.py`
- Fix: Represent as contract + CI matrix job; do not fake on SQLite.

## ENV-002 — Celery worker required for async-only deploy paths (low, blocked_external)
- Scope: environment
- Files: `apps/schools/tasks.py`
- Fix: Document; sync fallback already in complete_provisioning_for_school.

## GATE-001 — verify_tenant_lifecycle_completion blocked by shell scroll contract (medium, done)
- Scope: repo-side
- Files: `scripts/audit_shell_scroll_contract.py, templates/admin/base.html`
- Fix: Fix admin back-to-top placement or split lifecycle completion bundle from scroll gate.
