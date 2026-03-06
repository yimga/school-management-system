# Repeatable Module Refactor Pattern (Phase 1)

Use this when refactoring a module (e.g. Admissions or Gradebook) end-to-end so that **all behavior comes from the Policy/Blueprint layer** and the module has no hardcoded tenant/country logic.

## Goal

- Module answers "How should I behave for this tenant?" only via `get_effective_policy(school)` / `get_tenant_blueprint(request)`.
- No `if tenant.country == "X"` or `if school.settings.get(...)` in views, forms, services, or templates.
- Labels, field visibility, validation rules, workflow steps, and defaults come from policy (or from resolvers that read policy).

## Steps (repeat per module)

### 1. Identify policy surface

- List every behavior that today depends on tenant, country, or school settings: labels, required fields, approval chains, status lists, number formats, document requirements, etc.
- For each, decide the **policy key** (e.g. `terminology.student_id_label`, `admissions.review_stages`, `grading.scale`). Document in policy_injection.md or module doc.

### 2. Ensure policy provides the keys

- In `get_effective_policy` (and optionally TenantBlueprint/PolicyBundle), ensure platform_defaults and region/school merge produce these keys.
- If a key is missing, add it to the resolver merge (from `school.settings`, `school.features`, or region) so modules never read `school.settings` directly.

### 3. Inject in the module

- **Views/ViewSets:** Use `request.tenant_ctx` and `global_env` (from context processor). For request-scoped policy: `policy = get_tenant_blueprint(request)` or `get_policy_for_request(request)`; then `policy.get("terminology", {}).get("student_id_label")`, etc.
- **Forms/Serializers:** Accept optional `policy` or `global_env` in `__init__` (e.g. from view); drive required/optional, choices, labels, validators from policy. Do not read `request.school.settings` in forms.
- **Services:** Accept `school` (or tenant) and optionally `policy` dict; call `get_effective_policy(school)` at service entry if needed; pass policy slice to helpers. No direct `school.settings` / `school.features` in business logic.
- **Templates:** Use `{{ global_env.terminology.student_id_label|default:"Student ID" }}` (or equivalent). No `{% if school.country == "CM" %}`.

### 4. Remove direct reads

- Search the module for `school.settings`, `school.features`, `school.default_region`, `tenant.country`, and any `if country ==` / `if region ==`. Replace with policy resolution or with data from `global_env` / `get_effective_policy(school)`.
- Keep writes (e.g. admin saving settings) in siteconfig/schools; readers are only resolver and context processor.

### 5. Tests

- Add or extend tests: with a school that has specific `settings`/`features`, assert that views/forms return the right labels, options, and behavior without the test code reading `school.settings` directly.
- Test that changing policy (e.g. terminology) changes UI/API output. Test tenant isolation (no cross-tenant data).

### 6. Document

- In the module’s doc or in policy_injection.md, list the policy keys this module consumes and where they are injected (view, form, template).

## Example (Admissions slice)

- **Policy keys:** `admissions.admission_number_strategy`, `admissions.required_documents`, `terminology.admission_number_label`, `admissions.review_stages`.
- **Resolver:** Already merges `settings` and `features`; ensure `admissions` and `terminology` keys exist in merged dict (from school.settings or region).
- **View:** Pass `get_tenant_blueprint(request)` to form or template as `policy`; form uses `policy.get("admissions", {}).get("required_documents", [])` for validation.
- **Template:** `{{ global_env.terminology.admission_number_label|default:"Admission number" }}`.
- **Service (generate admission number):** Call `get_effective_policy(school)` once; use `policy.get("admissions", {}).get("admission_number_strategy")` and existing SiteSettings admission_number_* if still the source; later move to TenantAdmissionNumberPolicy when Section 22 is implemented.

## Checklist (per module)

- [ ] Policy keys listed and provided by resolver/bundle.
- [ ] Views use request.tenant_ctx / global_env / get_tenant_blueprint(request); no school.settings in views.
- [ ] Forms/Serializers receive policy and use it for fields/validation; no school.settings in forms.
- [ ] Services receive school and use get_effective_policy(school) or policy dict; no school.settings in services.
- [ ] Templates use global_env / policy; no country/tenant conditionals for behavior.
- [ ] Tests assert behavior from policy and tenant isolation.
- [ ] Doc updated with consumed policy keys and injection points.

## After first module

- Use this pattern for Gradebook, then Finance, Attendance, Communication, etc., in refactor wave order (Blueprint foundation → Admissions → Gradebook/attendance → Finance/comms → …).
