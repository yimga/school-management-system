# Contributing to RunMyCampus

Thank you for contributing. This document covers **non-negotiable** standards for UI and security so the product stays outcome-first, role-native, and secure.

## New and changed pages (required)

**Every new or heavily changed page must:**

1. **Conform to a page archetype** — Role Home, Setup Studio, Decision Console, Operational Workbench, or Catalog/Marketplace. See [docs/ui/PAGE_ARCHETYPES.md](docs/ui/PAGE_ARCHETYPES.md).
2. **Pass the 5-question test:**
   - What problem does this page solve?
   - What matters most right now?
   - What is the primary next action?
   - What can I do in one click?
   - What should I not have to click for?
3. Use outcome-first language (user goals, not module names).
4. Use shared design tokens and [static/css/platform-high-end.css](static/css/platform-high-end.css) where applicable (cards, CTAs, empty states).

**Checklist for PRs that add or refactor pages:** Document in the PR that the page maps to an archetype, passes the 5-question test, and uses the shared visual system. No new page may ship without this.

Reference: [docs/ui/PAGE_ARCHETYPES.md](docs/ui/PAGE_ARCHETYPES.md), [docs/ui/OPERATIONAL_WORKBENCH.md](docs/ui/OPERATIONAL_WORKBENCH.md).

## Security and runtime

- **Secrets:** Do not commit `.env`, `.env.local`, or any file with real API keys or passwords. Use `.env.example` with placeholders. See [SECURITY.md](SECURITY.md) if present.
- **Tenant-facing logic:** Do not use `SiteSettings` / `get_solo` directly in tenant-facing flows; use runtime resolvers. See [docs/security/SITESETTINGS_INVENTORY.md](docs/security/SITESETTINGS_INVENTORY.md).
- **Logging:** Use `logging.getLogger(__name__)` in application/worker code; do not use `print()` in request or task paths. See [docs/security/PRINT_DEBUG_AUDIT.md](docs/security/PRINT_DEBUG_AUDIT.md).
- **Host/domain:** Prefer [apps/schools/domain_resolution_service.py](apps/schools/domain_resolution_service.py) for base host, tenant URL, and env-specific routing instead of scattering `request.get_host()` or hardcoded domains.

## Pre-merge verification (recommended)

Before opening a PR (or after large template/i18n changes):

1. **Full gate (matches CI):** `bash scripts/pre_deploy_gate.sh` — installs Chromium via npm first if you want the Playwright slice; on a quick loop use `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh`.
2. **SQLite locks (Windows):** If `migrate_gate_test_db` fails with **database is locked**, close other test runners and see [docs/TEST_DATABASE.md](docs/TEST_DATABASE.md) (`PRE_GATE_FRESH_TEST_DB=1` or a unique `DJANGO_TEST_DB_FILE` path).
3. **i18n catalog drift:** If the gate fails on `verify_i18n_catalog_fresh.py`, run `python manage.py sync_i18n_catalog --compile` and commit updated `locale/**` files. The verifier compares template/catalog fingerprints to committed `locale/*/LC_MESSAGES/django.po` (and `.mo` after compile); a failure usually means new `{% trans %}` / `gettext` strings or edited messages—regenerate catalogs rather than silencing the script. **Policy:** any PR that adds or edits user-facing translatable copy should include the refreshed `locale/**` artifacts from that command (same commit), so `verify_i18n_catalog_fresh` stays green on `main`. **Drill:** after editing [templates/siteconfig/scheduled_reports_delivery_hub.html](templates/siteconfig/scheduled_reports_delivery_hub.html), [templates/portal/support_help_hub.html](templates/portal/support_help_hub.html), [templates/finance/invoices.html](templates/finance/invoices.html), [templates/finance/suspense_queue.html](templates/finance/suspense_queue.html), [templates/finance/payments.html](templates/finance/payments.html), [templates/finance/requests.html](templates/finance/requests.html), [templates/schools/marketing_landing.html](templates/schools/marketing_landing.html), [templates/schools/marketing_product_page.html](templates/schools/marketing_product_page.html), [templates/schools/super_phase_b_snapshot_diff.html](templates/schools/super_phase_b_snapshot_diff.html), [templates/schools/super_runtime_inspector.html](templates/schools/super_runtime_inspector.html), [templates/schools/super_workflow_simulator.html](templates/schools/super_workflow_simulator.html), [templates/schools/super_support_dashboard.html](templates/schools/super_support_dashboard.html), [templates/schools/super_support_csat_dashboard.html](templates/schools/super_support_csat_dashboard.html), [templates/schools/super_pulse.html](templates/schools/super_pulse.html), [templates/schools/super_usage.html](templates/schools/super_usage.html), [templates/schools/super_support_ticket_detail.html](templates/schools/super_support_ticket_detail.html), [templates/schools/super_tenant_health.html](templates/schools/super_tenant_health.html), [templates/admin/integrations_marketplace/marketplaceapp/change_form.html](templates/admin/integrations_marketplace/marketplaceapp/change_form.html), [templates/schools/super_tenant_360.html](templates/schools/super_tenant_360.html), [templates/schools/super_command_center.html](templates/schools/super_command_center.html), [templates/orchestration/operator_workbench.html](templates/orchestration/operator_workbench.html), [templates/schools/super_dashboard.html](templates/schools/super_dashboard.html), [templates/schools/super_schools_list.html](templates/schools/super_schools_list.html), [templates/schools/super_analytics_overview.html](templates/schools/super_analytics_overview.html), [templates/schools/super_platform_operator_hub.html](templates/schools/super_platform_operator_hub.html), [templates/schools/super_migration_cloud.html](templates/schools/super_migration_cloud.html), [templates/admin/integrations_marketplace/serviceintegration/change_form.html](templates/admin/integrations_marketplace/serviceintegration/change_form.html), [templates/admin/integrations_marketplace/marketplacelisting/change_form.html](templates/admin/integrations_marketplace/marketplacelisting/change_form.html), [templates/admin/integrations_marketplace/scopegrant/change_form.html](templates/admin/integrations_marketplace/scopegrant/change_form.html), [templates/admin/integrations_marketplace/appinstallation/change_form.html](templates/admin/integrations_marketplace/appinstallation/change_form.html) (or other report/finance/operator/marketing templates with `{% trans %}`), run the same sync before merge so `msgid` churn does not block CI (batch 15 #144 / batch 16 #154 / batch 17 #169 / batch 18 #184 / batch 20 #214 / batch 21 #229 / batch 22 #244 / batch 23 #259 / batch 24 #274 / batch 25 #289 / batch 26 #304 / batch 27 #319 / batch 28 #334 / batch 29 #349 / batch 30 #364 / batch 31 #379 / batch 32 #394 / batch 33 #409 / batch 34 #424 / batch 35 #439 / batch 36 #454 / batch 37 #469 / batch 38 #484 / batch 39 #499 / batch 40 #514 / batch 41 #529).
4. **Operator Phase 10/11 slice (optional):** `python scripts/verify_operator_phase10_11_e2e.py` — use `--ux-db-file .django_test_dbs/<unique>.sqlite3` if the default file is locked.
5. **Gate-map appendix drift (docs maintainability):** `python scripts/generate_gate_map_appendix.py --check` (source: [docs/gate_map_appendix_config.json](docs/gate_map_appendix_config.json)).

CI: [.github/workflows/smoke.yml](.github/workflows/smoke.yml) runs the pre-deploy gate on **push/PR to `main`** (and can be triggered manually via **Actions → Smoke test → Run workflow**).

## Plan completion and dependencies

**Execution status:** [docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (At a glance, §11.4, §12) — single place for program gates and “what’s left.”

All plan items are complete; CI enforces the non-negotiables. Solid platform and dependency list: [docs/execution/PLATFORM_COMPLETION_AND_DEPENDENCIES.md](docs/execution/PLATFORM_COMPLETION_AND_DEPENDENCIES.md). Status: [docs/plan/UX_PLAN_FULL_COMPLETION_REGISTER.md](docs/plan/UX_PLAN_FULL_COMPLETION_REGISTER.md). Remaining track: migrate existing SiteSettings usages per [docs/security/SITESETTINGS_INVENTORY.md](docs/security/SITESETTINGS_INVENTORY.md).

## Other resources

- **Documentation governance:** [docs/documentation_governance_plan.md](docs/documentation_governance_plan.md)
- **Management commands:** [docs/MANAGEMENT_COMMANDS_INDEX.md](docs/MANAGEMENT_COMMANDS_INDEX.md), [docs/execution/MANAGEMENT_COMMAND_INVENTORY.md](docs/execution/MANAGEMENT_COMMAND_INVENTORY.md)

## Developer Certificate of Origin (DCO)

Every commit in a pull request must include a **DCO sign-off** so we can attest you have the right to contribute the change.

### How to sign off

Use Git's sign-off flag on each commit:

```bash
git commit -s -m "Your message"
```

That adds a trailer line:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use the same name and email you intend to be reachable at. Amend or rebase if a commit lacks sign-off.

### What you are certifying

By signing off, you agree to the [Developer Certificate of Origin, Version 1.1](https://developercertificate.org/):

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I have
    the right to submit it under the open source license indicated in
    the file; or

(b) The contribution is based upon previous work that, to the best of my
    knowledge, is covered under an appropriate open source license and
    I have the right under that license to submit that work with
    modifications, whether created in whole or in part by me, under
    the same open source license (unless I am permitted to submit under
    a different license), as indicated in the file; or

(c) The contribution was provided directly to me by some other person
    who certified (a), (b) or (c) and I have not modified it.

(d) I understand and agree that this project and the contribution are
    public and that a record of the contribution (including all personal
    information I submit with it, including my sign-off) is maintained
    indefinitely and may be redistributed consistent with this project
    or the open source license(s) involved.
```

### Pull requests without sign-off

Maintainers may ask you to amend commits (`git commit --amend -s` or interactive rebase) before merge. The README [Contributing & security](README.md#contributing--security) section already references this requirement.
