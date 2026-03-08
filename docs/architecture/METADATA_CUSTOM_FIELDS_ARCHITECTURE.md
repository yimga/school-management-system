# Metadata / custom fields / dynamic forms architecture

Typed custom field system, dynamic forms by blueprint/policy/module, visibility and validation rules, and governance (Execution Master §3.8, §7.4).

## Requirements

- **Typed custom field system:** Field types (text, number, date, select, multi-select, etc.) with schema; stored in a governed model or JSON with schema validation.
- **Dynamic forms/sections:** Forms and sections driven by blueprint, policy, or module config—not hardcoded per tenant/country.
- **Visibility and validation rules:** Who sees which fields (role, entitlement); validation rules (required, pattern, min/max) from policy.
- **Export/search/report compatibility:** Custom fields included in export and search where policy allows; reported in operational reports.
- **Migration compatibility:** Custom field definitions and data migrate with tenant; no loss on blueprint/policy change where versioned.
- **Admin/config UI for metadata governance:** Control plane or admin UI to define and version custom field sets per entity (e.g. Student, Staff, Applicant).

## Implementation direction

- Custom field definitions: store in policy or a dedicated metadata registry; resolve via runtime (e.g. runtime.policy or runtime.modules) so one code path.
- Forms: render fields from definition list; validate against rules from same source. Use existing siteconfig tenant_config get_student_custom_fields / get_staff_custom_fields patterns but feed from runtime/policy.
- No module forks: one custom-field engine; behavior varies by blueprint/policy/tenant override only.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 2, Law 4)
- apps/siteconfig/tenant_config.py (existing custom field hooks)
- [RUNTIME_MODULES_REFACTOR.md](RUNTIME_MODULES_REFACTOR.md)
