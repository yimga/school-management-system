# Refinement and Implementation Order (Partial/Scoped Items)

After completing all 24 phases, this doc prioritizes **partial** and **scoped** checklist items for implementation or refinement. Use this order when moving forward; each item has a suggested next step and priority.

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md (Sections 1–31); phase docs (phase8, phase12, phase14_through_phase20, phase21_through_phase24); section_25_current_state.md.

---

## Priority 1 — High impact, already partially in place

| Item | Section | Current state | Next step | Owner |
|------|---------|---------------|-----------|--------|
| **Structured logging (request_id, tenant_id)** | 25.4 | **Done** | Already implemented: `RequestIdLoggingMiddleware` + `RequestContextFilter` (apps.observability); log format includes request_id, tenant_id, user_id. Update section_25_current_state to Done. | — |
| **Migration rollback** | 11.1, 29.6 | **Done** | Rollback implemented: MigrationRun.rollback_snapshot, trigger_rollback, rollback_handlers (students, grades); admin action. | — |
| **Audit log export** | 25.5 | **Done** | Admin actions export_audit_log_csv, export_audit_log_json (compliance/admin_audit.py). | — |
| **Blueprint pack versioning** | 11.2, phase6 | **Done** | update_bundle_for_schools + admin action; mgmt command: python manage.py update_blueprint_bundles (--pack=slug, --dry-run). | — |
| **Event backbone (DomainEvent, WebhookDelivery)** | 26.2 | **Done** | DomainEvent, WebhookDelivery in apps/events; emit_event, enqueue_webhook_event; retries/signatures. | — |

---

## Priority 2 — Configurability and UX

| Item | Section | Current state | Next step | Owner |
|------|---------|---------------|-----------|--------|
| **Finance: invoice timing, fee templates, late fee rules** | 10.3 | **Done** (policy slice) | policy["finance"] with invoice_timing, fee_templates, late_fee_rules; resolver defaults + bundle merge; phase12 updated. | — |
| **Attendance: statuses, lateness, escalation** | 10.4 | **Done** (policy slice) | policy["attendance"] with statuses, lateness_rules, escalation; resolver + bundle merge; phase12 updated. | — |
| **Communication: channels, fallback order** | 10.5, 28.8 | **Done** (policy slice) | policy["communication"] with channel_order, fallback_order; resolver + bundle merge; phase12 updated. | — |
| **UX rules: list search/filters/export, form autosave** | 26.5 | Done (this cycle) + deferred | Document library CSV; applicants list (search/filter/export); application form Save draft (backend Add applicant). Remaining (deferred): classes/sections list; student onboarding step-level draft. See ux_rules_audit_26_5.md and SCOPED_WORK_VERIFICATION.md. | Frontend / Modules |
| **Parent mobile-first** | 14.4 | Viewport done | Viewport meta in templates/portal_base.html. Audit touch targets and responsive layout when prioritised (parent_mobile_first_audit_14_4.md). | Portal |
| **Design tokens doc** | 26.4, 29.8 | **Done** | docs/architecture/design_tokens.md — CSS vars, density, nav, WCAG 2.2 AA. | — |

---

## Priority 3 — Integrations and standards

| Item | Section | Current state | Next step | Owner |
|------|---------|---------------|-----------|--------|
| **Ed-Fi adapter** | 18.1, 31.2 | Scoped | Add interop/edfi adapter; map canonical models to Ed-Fi; optional API. | Interop |
| **CEDS for reporting (US)** | 18.2 | Scoped | Define CEDS mapping and translation layer for US reporting. | Reports / Interop |
| **WebAuthn / Passkeys** | 25.5, 29.1 | MFA (TOTP) done | Add WebAuthn/passkey option alongside TOTP for privileged roles. | Accounts |
| **OpenFeature for feature flags** | 31.7 | **Done** (doc) | docs/architecture/feature_flags.md — current is_feature_enabled/can(); optional OpenFeature provider documented. | — |

---

## Priority 4 — Larger roadmap items (scoped)

| Item | Section | Current state | Next step | Owner |
|------|---------|---------------|-----------|--------|
| **Student 360 / timeline / transcript** | 15.1, 26.1 | **Done** | Full 360 tabbed UI (student_360_page). Immutable transcript and cross-year archive: transcript_archive, transcript_archive_year, transcript_freeze; Student 360 page links to Transcript & archive. See SCOPED_WORK_VERIFICATION.md. | Product / Backend |
| **Metadata-driven data layer (DynamicField)** | 15.2 | **Done** | apps/metadata: DynamicFieldDefinition, DynamicFieldValue, services, admin. No schema migrations for custom attributes. API/UI extensions per product. | Metadata / Backend |
| **Global ledger (double-entry, payment plans)** | 15.3 | Finance models exist | Extend finance for double-entry ledger; payment plans and installments. | Finance |
| **Offline first + sync engine** | 16.5 | Policy offline_mode | Define offline-capable flows (attendance, grade entry); sync engine and conflict resolution. | Backend / Frontend |
| **Preview/release (staging schema, canary)** | 29.4 | Scoped | Tenant staging/sandbox schema; config diff viewer; canary by tenant/country/plan. | Platform / SRE |
| **Government/district intelligence layer** | 14.5 | Scoped | EMIS/reporting extensions; secure aggregation; document as product roadmap. | Product |
| **Commercial platform (trials, quote-to-contract)** | 29.10 | Scoped | Self-serve trials, quote-to-contract, partner tooling; tie to billing. | Billing / Product |

---

## How to use this doc

1. **Sprint planning:** Pick 1–2 items from Priority 1 or 2 per sprint.
2. **Checklist updates:** When an item is implemented, update the main checklist (and section_25_current_state or phase docs) from partial/scoped to done or document the remaining scope.
3. **Dependencies:** Priority 1 “Event backbone” may unblock webhook delivery and event-driven features; migration rollback and audit export are standalone.
4. **Feature flags:** Use `can(school, capability)` and `is_feature_enabled(school, code)` everywhere; optional OpenFeature integration (Priority 3) for runtime toggles without deploy.

---

## References

- **Observability (25.4):** RequestIdLoggingMiddleware, RequestContextFilter — `apps/observability/middleware.py`, `apps/observability/logging_context.py`; LOGGING in config/settings.py.
- **Feature flags (31.7):** `apps/schools/models.py` — `can(school, capability)`, `is_feature_enabled(school, code)`; OpenFeature can wrap same backend later.
- **Policy injection:** docs/architecture/policy_injection.md.
- **Runbooks:** docs/architecture/control_plane_runbooks.md.
