# Section 23 — Policy/Blueprint Injection Verification (Phase 5)

Audit of every injection point. Use this table to verify or extend policy/blueprint injection.

## Summary table

| Id   | Layer | Requirement | Where implemented | Notes |
|------|--------|-------------|--------------------|--------|
| 23.1 | Middleware | Tenant resolution, control vs tenant split, blueprint hydration, request metadata, security/compliance gates, feature-flag evaluation | See below | Verified |
| 23.2 | Context processor | Inject resolved global_env / tenant_ctx into templates | See below | Verified |
| 23.3 | Views/ViewSets | tenant_policy, workflow_resolver, dashboard_resolver, terminology where needed | See below | Verified |
| 23.4 | Forms/Serializers | Policy-driven visibility, required/optional, picker options, validation | See below | Verified |
| 23.5 | Services | Tenant context, blueprint, policy snapshot; no direct settings in business code | See below | Verified |
| 23.6 | Templates | Resolved labels, layout, branding | global_env, tenant_ctx in templates | Verified |
| 23.7 | Signals / DRF permissions | Invariants (audit), capability gates | See below | Verified |

---

## 23.1 — Middleware

| Concern | File / function | Notes |
|--------|------------------|--------|
| Tenant resolution | `apps.schools.middleware` — host → school (subdomain, custom domain); `_resolve_school_from_request`, urlconf switch (public vs tenant) | Sets `request.school`; control vs tenant via host and SUPER_PREFIXES |
| Control vs tenant split | `apps.schools.middleware` — SUPER_PREFIXES, public host vs tenant host; urlconf = public_urls vs tenant_urls | /super/ → control plane; tenant subdomain → tenant_urls |
| Request metadata / tenant context | `apps.tenancy.middleware.TenantContextMiddleware` — `build_tenant_context_from_request(request)` | Sets `request.tenant_ctx` (TenantContext: tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host) |
| Blueprint hydration | Policy not loaded in middleware; context processor loads `global_env` = get_effective_policy(school) | 23.2 handles full policy; tenant_ctx holds raw overrides/metadata |
| Feature-flag evaluation (gates) | `apps.schools.middleware.FeatureGateMiddleware` — FEATURE_GATE_PATH_MAP; calls get_effective_policy(school, capability=code) or is_feature_enabled(school, code) | Returns 403 when path requires capability and tenant does not have it |

---

## 23.2 — Context processor

| Concern | File / function | Notes |
|--------|------------------|--------|
| global_env | `apps.policies.context_processors.tenant_policy_context` | ctx["global_env"] = get_effective_policy(request.school, user=request.user) |
| tenant_ctx | Same | ctx["tenant_ctx"] = request.tenant_ctx (or None) |
| Registered in settings | `config.settings.TEMPLATES.OPTIONS.context_processors` | "apps.policies.context_processors.tenant_policy_context" |

---

## 23.3 — Views/ViewSets

| Concern | File / function | Notes |
|--------|------------------|--------|
| Policy for request (tenant_policy) | Views pass policy from get_tenant_blueprint(request) or get_effective_policy(school) | portal.views (link_child, onboarding), portal.views_onboarding, evals.views (marksheet, grade approval), siteconfig.views (grading_settings) |
| workflow_resolver | `apps.siteconfig.workflow_resolver` — for_action(school, action_slug), get_approval_workflow(school, workflow_key) | academics.views_syllabus (get_approval_workflow "syllabus_approval"); evals (grade_approval via approval module) |
| dashboard_resolver | `apps.siteconfig.dashboard_resolver.for_role(school, role, user=..., include_registry=...)` | portal.views (dashboard_for_role for backend); evals.views (dashboard_for_role for teacher dashboard); siteconfig.views_workflow_api (dashboard_registry_api) |
| terminology | Via global_env.terminology or policy["terminology"] in views/forms | No separate terminology_resolver; terminology in global_env / policy |

---

## 23.4 — Forms/Serializers

| Concern | File / function | Notes |
|--------|------------------|--------|
| apply_form_policy / get_form_schema | `apps.policies.form_policy` — get_form_schema(policy, form_name), apply_form_policy(form, form_name, policy, school=...) | Form schemas from policy["forms"] (platform defaults + bundle + school.settings["forms"]) |
| Wired forms | `apps.portal.forms` — LinkChildForm (apply_form_policy "link_child"), StudentOnboardingForm (apply_form_policy "student_onboarding") | Views pass policy=get_tenant_blueprint(request) |
| Choices / catalog | form_policy get_field_configs, _resolve_choices_for_key (catalog-backed choices) | phase3_metadata_driven_forms_24_8_23_4.md |

---

## 23.5 — Services

| Concern | File / function | Notes |
|--------|------------------|--------|
| Policy only, no direct settings | reports.services (resolve_report_labels, _region_display_context); evals.approval (get_grade_approval_policy); people.StudentProfile (_get_admissions_policy); siteconfig.identifier_policy_service; finance.gateways.registry (payment_gateways from policy) | All use get_effective_policy(school) or get_grade_approval_policy(school); no direct School.settings/features in business logic |
| Tenant context passed | create_grade_approval_request(teacher, subject_assignment, ...) derives school from teacher/classroom; report services accept school | School passed explicitly or from request/assignment |

---

## 23.6 — Templates

| Concern | Implementation | Notes |
|--------|----------------|--------|
| Resolved labels | Use {{ global_env.terminology.* }} or {{ global_env.report_labels.* }} where available | policy_injection.md; REPEATABLE_REFACTOR_PATTERN |
| Layout / branding | region_settings context processor (grading_scale, default_language, currency from policy when school set); tenant theme/colors from school or BrandProfile | No country branching in tenant templates |
| Actions/components | Sidebar uses is_feature_enabled(school, feature) to hide items; workflow/dashboard hubs use resolvers | portal_sidebar_items.py |

---

## 23.7 — Signals / DRF permissions

| Concern | File / function | Notes |
|--------|------------------|--------|
| Audit invariants | `apps.compliance.signals` — post_save/post_delete receivers; AuditLog (models_audit); audit_enabled on models | Enforce audit trail; no policy read in signals |
| Capability gates | get_effective_policy(school, capability=...) returns {"enabled": is_feature_enabled(school, capability), "policy": out}; FeatureGateMiddleware uses it for path-based gates | is_feature_enabled(school, code) in portal_sidebar_items for menu visibility |
| permission_required | apps.accounts.decorators.permission_required; used on siteconfig, portal views | DRF permissions = capability gates where API uses permission classes |

---

## References

- `docs/architecture/policy_injection.md` — main policy injection doc
- `docs/architecture/RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` — Section 23 checklist
- `apps.policies.resolver.get_effective_policy`, `apps.policies.registry.get_tenant_blueprint`, `get_policy_for_request`
