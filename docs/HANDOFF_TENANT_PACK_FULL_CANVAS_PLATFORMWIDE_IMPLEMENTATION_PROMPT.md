# Tenant Pack Full-Canvas Platform-Wide Implementation and Certification Prompt

Use this prompt as a fail-closed implementation and release gate. Do not treat it as a design exercise or a source-only assertion pass.

## Immutable approval source

The approved visual and behavioral source of truth is:

- `var/design-previews/tenant-pack-setup-full-canvas-before-after-approval-2026-07-31.html`

The **Proposed after** mode is approved. Preserve its full-canvas information hierarchy, high-density but readable catalog, page-aware decision rail, broad use of horizontal space, responsive collapse, light/dark behavior, and honest audit state. Production controls must remain genuine Django operations; prototype-only behavior must never be copied as a fake production action.

## Objective

Audit first, implement every confirmed defect, then re-audit the complete operator, tenant, shared, and Django-admin surface inventory. The primary route is the real tenant hostname route `/school/setup/packs/`, owned by `tenant_pack_setup`, `templates/platform_runtime/tenant_pack_setup.html`, and its route-scoped assets. The repair is incomplete if the real tenant host still renders the old generic panels, if the catalog remains left-clamped, or if any audited operator defect remains.

## Required implementation

1. Replace the generic tenant pack `panel + grid + card + page-shell` composition with a route-scoped full-canvas catalog.
2. Render the complete tenant-safe catalog through bounded server-side search, type filtering, and numbered pagination.
3. Keep exactly one visible H1, owned by the shared operational masthead.
4. Use a desktop decision layout of `minmax(0, 1fr) minmax(19rem, 28%)`, collapsing to one column at `1024px` and below.
5. Keep the selected-pack rail page-aware and host-scoped. Show readiness, risk, approval posture, included changes, blockers, and rollback posture from real backend data.
6. Wire Preview and Simulation to real GET execution. Wire Request approval, Apply, Deactivate, and Rollback to CSRF-protected Django POST actions with required confirmation. Remove any action that is not genuinely executable.
7. Keep operator/fleet/Studio/global-registry controls off tenant pages.
8. Keep CSS route-scoped. Do not introduce global `.panel`, `.grid`, or `.card` selectors. Stylesheet links must be emitted from a head-owned block.
9. Preserve native tables for installation history; horizontal scrolling is allowed only inside the table wrapper when table data requires it.
10. Repair every related audit finding: operator provisioning queue and live support console must use the shared steering frame without duplicate headers; long URL/history cells in the four audited control-plane tables must wrap rather than clip.
11. Add regression tests and a platform-wide source audit so the old defect signature cannot return.
12. Use an explicit cache-bust on new static assets and include deployment cache invalidation in the release steps.
13. Treat head ownership as a rendered-DOM invariant: no head partial may emit body markup, and no body component may emit a stylesheet link.
14. Resolve post-action state only after the mutation so the successful Apply response immediately renders the updated native installation table without requiring a reload.
15. Keep build ID, cache-bust ID, approval seal, and service-worker version synchronized and monotonically increasing.

## Scope and isolation gates

- Test the real manager hostname and at least one real tenant hostname separately. Do not infer host routing from `127.0.0.1`.
- Assert tenant users can see only tenant-safe packs and can mutate only their own school.
- Assert invalid or operator-only pack keys fail closed to a valid tenant-safe selection.
- Assert operator steering components do not leak into tenant content.
- Preserve existing role, MFA, tenant membership, and platform-scope gates.
- Do not mutate production tenant data merely to obtain screenshots. Use authorized test fixtures or reversible, explicitly confirmed records.

## Required source and static checks

Run from the repository root and remediate every in-scope failure:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py collectstatic --dry-run --noinput
python scripts/audit_full_canvas_catalog_contract.py --json --strict
python scripts/audit_surface_spacing_contract.py --json --strict
python scripts/audit_control_plane_template_layout.py
python scripts/verify_operational_workbench_surface.py --json
python scripts/audit_canvas_chrome_void.py --json
python scripts/verify_page_fold_standards.py
python scripts/verify_django_admin_preview_parity.py
python scripts/audit_django_admin_surface_leftovers.py
python scripts/sweep_django_admin_platformwide_layout.py
python scripts/audit_django_admin_miss_nothing.py
python scripts/verify_service_worker_version.py --check-monotonic
python manage.py test apps.platform_runtime.tests.test_tenant_pack_setup apps.platform_runtime.tests.test_tenant_school_experience_redesign apps.platform_runtime.tests.test_governed_installation_ux_flow
git diff --check -- <all files intentionally changed by this implementation>
```

If a named script has been superseded, find and run the repository's current equivalent and record the substitution. Do not silently skip a gate.

## Real-browser certification

Capture the authenticated tenant route and representative affected operator routes at `1440`, `1024`, `768`, and `390px` in light and dark themes. For every captured route assert and retain DOM/computed-style evidence for:

- HTTP 200 and the expected hostname/scope;
- one visible H1;
- zero document-level horizontal overflow;
- full-canvas content width rather than a stale max-width clamp;
- desktop two-region layout and a single-column layout at `1024px` and below;
- no broken static resources, console errors, duplicate CSS URLs, or stylesheet links in body;
- no duplicate shell/header/breadcrumb/navigation/context drawer/fixed overlay;
- no unexpected raw icon names;
- genuine preview, simulation, approval/apply, and rollback/deactivate form behavior;
- tenant isolation and absence of operator-only controls;
- correct native table display and contained table-only overflow.

Remove stale failure screenshots and reports after successful reruns so release evidence cannot contradict the final state.

The audit must explicitly rule out the known failure chain: a body element emitted by a head-only include causes the HTML parser to close `<head>` early; inherited shells then duplicate stylesheet ownership; stale collected-static manifests keep old hashed assets live; cached template loaders keep old markup live until worker restart; and pre-mutation queryset evaluation makes a successful POST appear unapplied. Also verify that legacy responsive `display: flex !important` rules cannot leave the desktop sidebar over the mobile canvas.

## Completion report and deployment

Report exact root causes, changed files, migrations (including “none”), every command and result, hostname/browser evidence paths, and any unrelated pre-existing failures kept out of scope. Production deployment must update application templates and static assets together, run `collectstatic`, invalidate CDN/proxy caches for the versioned CSS URL, restart application workers, verify service-worker/cache monotonicity where applicable, and repeat the real-host smoke matrix after deployment.

Do not claim completion until the implementation, tests, source audits, real-host browser evidence, scoped diff review, intentional commit, and requested push to `main` are all complete.
