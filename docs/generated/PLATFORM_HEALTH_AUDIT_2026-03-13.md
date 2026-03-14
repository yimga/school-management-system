# Platform Health Audit — Links, Frames, Dashboards, Integration

**Date:** 2026-03-13  
**Scope:** Ensure things are properly linked, buttons/shortcuts work, dashboards and pages work, no 404/500 from misconfiguration, UI/UX in-frame, well-labeled, well-seeded, architecturally sound, ready for merge/deploy.

---

## 1. Changes made this run

| Area | Change |
|------|--------|
| **Tenant URLs** | Studio OS included: `path("studio/", include(("apps.studio_os.urls", "studio_os"), namespace="studio_os"))`. Tenant and platform now both expose Studio OS at `/studio/` (experience, automation, output, launch, control). |
| **Customizer redirect** | Tenant `admin/siteconfig/customizer/` now redirects to `studio_os:experience` (same as platform), so old customizer link goes to Studio OS Experience. |
| **Config cleanup** | Unused `SiteSettings` import removed from `config/urls.py` and `config/tenant_urls.py`. |
| **Control-plane frame** | `templates/control_plane_skeleton.html`: added `overflow-x: clip` on html/body and in-frame contract for container/main so content does not spill outside frames. |
| **Base template** | Already had `overflow-x: clip` on html, body, `.app-container` and min-width/overflow-wrap rules; no change. |

---

## 2. Verification

| Check | Result |
|-------|--------|
| **Smoke URL tests** | 35 tests pass (`apps.accounts.tests.test_smoke_urls`). Critical paths: home, health, accounts login/redirect/backend_dashboard, portal parent_dashboard, siteconfig customizer/preferences/feature_control/dashboard_hub, analytics, reports, evals teacher_dashboard, finance, studio_os:experience, compliance dashboard, communication group_list, public_support_hub, public_verify_hub, marketing_blog_detail. |
| **manage.py check** | No issues. |
| **Error handlers** | 403, 404, 500 handlers set in config/urls.py and config/tenant_urls.py. Custom views pass `user` in 500 context so base template renders when context_processors fail. |
| **Error templates** | 403.html, 404.html, 500.html (and _control_plane variants) extend base.html; content in container/card; buttons to login or dashboard. |
| **Redirects** | home → accounts:redirect or marketing_landing; /backend/ → accounts:backend_dashboard; /portal (no trailing slash) → portal:parent_dashboard; admin/siteconfig/customizer/ → studio_os:experience. |
| **Frames** | base.html: html/body/.app-container overflow-x: clip; control_plane_skeleton: overflow-x clip + container/main max-width 100%. |

---

## 3. Already in place (no change)

- **Shortcuts:** Command palette (Ctrl+K) wired in Studio OS shell; skip links (e.g. #studio-canvas, #cp-main-content).
- **Dashboards:** Backend dashboard, portal, Studio OS modes, compliance, analytics, finance, evals, reports, communication, etc., wired via urlconfs.
- **Seeding:** Seed commands (seed_global_regions, seed_preview_fixtures, seed_workflow_dashboard_packs, platform_inventory, etc.) documented and used in pre_deploy_gate / RELEASE_CHECKLIST.
- **Labels/structure:** Workflow centers, sidebars, and Studio OS rails use semantic markup and aria where noted in BACKLOG (§8.3, a11y).

---

## 4. Recommendation

Run full `bash scripts/pre_deploy_gate.sh` (and optional E2E/staging per launch_studio_checklist) before merge/deploy. This audit covered URL wiring, redirects, error pages, and frame containment; pre_deploy_gate adds lints, platform_inventory --check, smoke URLs, and other gates.
