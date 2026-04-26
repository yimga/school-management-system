# Demo script — RunMyCampus

Use a **staging tenant** with seeded academics, at least one student, one teacher, and a `Plan` row assigned to the school. Adjust URLs for your hostnames (`{tenant}` / `manager.runmycampus.com`).

## 0. Preconditions (5 min)

- Operator user with `settings.manage` (and staff if you need CCC on manager).
- Know login URL for tenant portal and manager URL for CCC.
- Optional: one scheduled report row and one report template for visual interest.

## 1. Login → dashboard (3 min)

1. Open tenant login; authenticate as operator.
2. Land on **backend dashboard** (`accounts:backend_dashboard`).
3. Narrate: *operator-first school OS overview; intent pills (Executive / Operational / …) switch lens without leaving the shell.*

## 2. Configuration Control Center (4 min)

1. Open **Configuration Control Center** (`siteconfig:console_domains_hub`, path `/siteconfig/console/`). Use **manager** host or **tenant school** host — the same `siteconfig` include is available on both URLConfs; pick the host that matches your audience (operations often use the school host for a pure tenant story).
2. Walk **outcome groups** and **operational hubs** — emphasize staged configuration and links to evidence surfaces, not Django model walls.

## 3. Reports & delivery (4 min)

1. Open **Scheduled report delivery** (`siteconfig:scheduled_reports_delivery_hub`).
2. Show **Report output history (evidence)** and **Tenant schedules (evidence)** if routes are enabled.
3. State clearly: delivery runs via management command / Celery in production — the UI is visibility and configuration, not a fake “Send now” for demo unless ops runs the job.

## 4. Student / teacher (5 min)

1. From dashboard or people menu, open a **student** profile (backend or portal as appropriate to role).
2. Open a **teacher** profile — show assignments / classroom linkage.
3. Highlight **no raw admin as primary** — Advanced/Admin appears only as labeled fallback where applicable.

## 5. Marketplace (3 min)

1. Open **marketplace / app catalog** surfaces available to the demo user (tenant sandbox or super governance, depending on role).
2. Explain **install vs entitlement**: marketplace discovery vs `Plan` / `addons` gates.

## 6. Studio OS (4 min)

1. Open **Studio OS** experience or output shell (`studio_os:experience` / `studio_os:output` as appropriate).
2. Show **report card builder** or report library pane — tie back to scheduled delivery and evidence pages.

## 7. Plan & entitlements (2 min)

1. Open **`/siteconfig/billing/plan/`** on the tenant (`siteconfig:billing_plan_readonly`).
2. Read-only: current plan name, slug, included feature codes, add-ons, counts vs caps.

## 8. Close (1 min)

- Recap: unified OS, operator-first, evidence-backed, admin demoted to Advanced.
- Next step: commercial proposal + staging pilot checklist (`docs/deployment/PRODUCTION_DEPLOYMENT_CHECKLIST.md`).
