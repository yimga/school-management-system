# Studio launch, ExperienceTemplate, and tenant action audit — 2026-08-11

Status: **implemented and validated**
Release: `2026-08-11-v17.2`
Cache bust: `20260811-experience-runtime-v172`
Service worker: `sms-v4.06.34-experience-runtime-2026-08-11`

## Scope

This audit covered the Gilead tenant journey reported at `/studio/launch/`, the ExperienceTemplate marketplace apply/preview/rollback lifecycle, starter-stack checklist state, runtime behavior across tenant portal, base, Studio/control-plane, and tenant Django admin shells, the timetable generator GET contract, and tenant-wide instructional/action affordances. Operator and tenant Django admin shells were also revalidated on their real hostnames.

## Root causes

1. ExperienceTemplate apply stopped at generic package bookkeeping. It created `InstalledPackage` and `PackInstallation` rows and a simulation marker, but it did not create the `TemplateAssignment` or a role/surface runtime payload. The success message was therefore true only for package installation, not for visible experience activation.
2. Setup Studio checked only active `TemplateAssignment` rows. Because apply never created that row, “Choose experience template” could not turn green. Old successful installations also had no self-healing path.
3. Starter-stack completion read legacy `school.addons`, while Module Market writes `school.features` and `FeatureToggleState` keys under `module.*`.
4. Package type inference did not recognize `experience_template`; installations could be mislabeled as blueprints.
5. Live preview rendered no genuine frame because its view did not supply `preview_url` or role targets. The fallback preview helper pointed to the nonexistent `/portal/preview` route.
6. Setup Studio’s admin preview is an absolute canonical tenant URL. The first sanitizer revision rejected every absolute URL, which silently dropped the admin role and selected a teacher URL that redirected an admin user. The final sanitizer accepts only exact same-host HTTP(S) targets, normalizes them to paths, and continues to reject cross-host and protocol-relative input.
7. The apply-result template always retained confirmation language after a successful POST.
8. Rollback used a parallel generic path and could leave the canonical installation applied, allowing later reconciliation to resurrect rolled-back runtime state.
9. `/academics/timetable/generate/` was POST-only even though tenant navigation linked to it as a normal GET.
10. The shared AI-guidance action had insufficient visual ownership, making “Open in AI Center” resemble ordinary text. The same action smell existed on several tenant help, finance, analytics, workflow, and configuration surfaces.
11. Runtime styling was absent from the Studio/control-plane skeleton, so a correctly activated template was not observable there.
12. Build, cache-bust, and service-worker identifiers needed a synchronized release bump to prevent an older browser cache from masking the fix.

## Implemented behavior

- A governed activation service validates the template registry overlay, repairs legacy package classification, enforces one active assignment per surface, persists `active_experience_templates`, and emits an audit event.
- Apply is transactional and idempotent. Failed runtime activation cannot leave a newly installed generic package presented as active.
- Existing successful installations can be audited or repaired with the scoped `reconcile_experience_template_runtime` command. Setup Studio also performs safe read-time reconciliation so the checklist self-heals after deployment.
- Runtime attributes and the template runtime stylesheet are present once on base, portal, Studio/control-plane, and tenant/admin shells. Palette, typography, density, layout, and responsive rules are driven by the active template rather than simulated controls.
- Preview now renders a real, same-origin iframe with working role/device controls, a genuine new-tab fallback, and no nonexistent placeholder route.
- Successful apply pages say “Template active,” show activation evidence and next actions, and no longer ask the user to confirm an already completed action.
- Canonical rollback clears the outgoing assignment and package state. When a template replaced an earlier template on the same surface, rollback atomically reactivates that prior installation and restores its runtime settings.
- Starter-stack completion follows the same canonical feature state written by Module Market.
- Timetable GET redirects to the working operations workspace; POST remains the only generation mutation.
- AI Center and audited tenant actions use visible contained/outline action styling. A nonfunctional disabled “Suggested fix” pseudo-control was removed.

## Changed files

Runtime and lifecycle:

- `apps/brand_experience/template_runtime.py`
- `apps/brand_experience/views_template_marketplace.py`
- `apps/brand_experience/management/commands/reconcile_experience_template_runtime.py`
- `apps/packages/engine.py`
- `apps/platform_runtime/context_processors.py`
- `apps/platform_runtime/live_preview.py`
- `apps/platform_runtime/pack_apply.py`
- `apps/platform_runtime/pack_rollback.py`
- `apps/setup_studio/services.py`
- `apps/academics/views_hub.py`
- `apps/academics/views_timetable.py`

Shell, preview, and action UI:

- `static/css/rmc-experience-template-runtime.css`
- `static/css/rmc-ai-guided-assistant-card.css`
- `templates/base.html`
- `templates/portal_base.html`
- `templates/control_plane_skeleton.html`
- `templates/admin/base.html`
- `templates/admin/base_site.html`
- `templates/marketplace/templates_preview_frame.html`
- `templates/marketplace/templates_apply_confirm.html`
- `templates/accounts/partials/workflow_center_main.html`
- `templates/analytics/dashboard.html`
- `templates/apicenter/partials/dashboard_body.html`
- `templates/feedback/partials/help_center_quick_feature.html`
- `templates/finance/dashboard.html`
- `templates/platform_runtime/school_configuration_center.html`
- `templates/portal/education_pack_teacher.html`
- `templates/schools/partials/manager_help_center_body.html`
- `templates/siteconfig/permission_matrix_simulator.html`
- `templates/siteconfig/zero_ticket_hub.html`

Release, tests, and audit gates:

- `static/js/service-worker.js`
- `var/admin-approval-build-lock.json`
- `var/security-audit-baseline-service-worker-version.json`
- `scripts/audit_tenant_experience_runtime_contract.py`
- `scripts/verify_tenant_experience_runtime_browser.mjs`
- `scripts/verify_template_marketplace_semantic_runtime.py`
- `scripts/verify_platform_chrome_sweep.py`
- Admin v17 audit scripts and generated PASS reports updated for the terminal stylesheet owner and v17.2 release.
- Regression coverage in brand experience, platform runtime, setup studio, tenant admin, and timetable test modules.

## Validation evidence

- Targeted Django regressions: **57/57 pass**.
- Marketplace semantic runtime: **18/18 pass across 5 classes**.
- Tenant experience runtime audit: **3 consecutive passes**, each **54 checks across 1,878 templates**.
- Real-host Studio journey: **14/14 checks pass** on `gilead-tech.runmycampus.com` mapped to the isolated server. It proves authenticated launch, green applied checklist state, active runtime key, HTTP 200 preview, one H1, genuine same-host iframe, non-404 target, and timetable GET redirect rather than 405.
- Real-host Django admin matrix: operator and tenant changelists pass at **1440, 1024, 768, and 390px**, in **light and dark**; HTTP 200, correct host/scope, zero horizontal overflow, desktop three-column grid, and responsive single-column grid at 1024px and below.
- `manage.py check`: **0 issues**.
- `makemigrations --check --dry-run`: **no changes detected**.
- `migrate --plan`: command passes. The disposable local evidence database reports pre-existing repository migrations still pending; production must run the normal migration step during deployment.
- `collectstatic --dry-run --noinput`: **pass**.
- Template compilation: **1,890 checked, 0 failures**; Django admin canvas compilation also passes.
- Admin preview parity, leftovers, platform-wide layout, miss-nothing, surface-platform contract, canvas contract, section restore, and cross-wave audit: **all pass**; cross-wave result **87 OK / 0 WARN / 0 FAIL**.
- Platform surface sweep: **129 templates, 0 findings**.
- Service-worker monotonicity: **4.6.34 >= 4.6.34 baseline** after the synchronized baseline write.
- `git diff --check`: **pass**.

## Production deployment and Gilead reconciliation

After deploying the commit:

```text
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py reconcile_experience_template_runtime --school gilead-tech
python manage.py reconcile_experience_template_runtime --school gilead-tech --apply
python manage.py reconcile_experience_template_runtime --school gilead-tech
```

The first reconciliation is audit-only, the second performs only required repairs, and the final audit must report the installation healthy. Restart web/workers, invalidate CDN/static caches for release `20260811-experience-runtime-v172`, and allow the new service worker to activate. Then verify the production tenant with a fresh authenticated session at `/studio/launch/`, the selected template preview route, `/authentication/backend/`, and `/academics/timetable/generate/`.

No production database was mutated during this audit. Gilead activation and browser evidence used an isolated copied SQLite database.
