# First customer onboarding (RunMyCampus)

**Scope:** A practical sequence for the **first** paying or pilot school after staging is green. It references **real** product routes and data setup — **not** a substitute for your legal/onboarding SOP, data processing agreement, or support contract.

**Prerequisites:** Staging (or production) deploy healthy per `STAGING_RELEASE_EXECUTION.md` + `LAUNCH_SMOKE_TEST.md` on a **seeded** or **pilot** tenant. No new product features are implied below.

---

## 1. Account creation

- **Provision the school (tenant):** Create or import the `School` (and, when `USE_DJANGO_TENANTS=1`, the tenant `Client` / `Domain` records) so the **school subdomain** resolves to `request.school` on the right host. Use your org’s runbook (Render dashboard, `migrate_schools_to_tenants`, `backfill_schooldomain`, or super-admin flows — whatever your deployment already uses).
- **Assign a plan:** Set `Plan` (or org equivalent) and `included_features` so the customer sees the modules they purchased — **entitlements in data**, not a slide deck.
- **Create the initial admin user:** At least one **staff** user with the permissions needed to open the Configuration Control Center and academic setup (e.g. `settings.manage` where your product requires it for siteconfig). Use **`seed_render_users`**, super-admin UI, or your invitation flow — not a fake “demo only” user in production.

## 2. First login

- **URL:** `https://<subdomain>.<base>/` (tenant) or your chosen login path (`authentication/` namespace).
- **Expect:** Login succeeds; redirect to role-appropriate home (`accounts:redirect` / portal / backend as configured).
- **If CSRF or host errors:** Fix `CSRF_TRUSTED_ORIGINS` and `ALLOWED_HOSTS` for the **exact** browser origin and hostname (see `ENVIRONMENT_VARIABLES.md`).

## 3. Initial setup (product-grounded)

Work with the customer in this **order** (adjust to their license):

1. **School / branding (optional but common):** Theme, logo, and portal-facing identity — `user_preferences`, `school_theme`, Studio experience, or CCC-linked surfaces as you already ship.
2. **Academic year and structure:** At least one **active academic year** and **departments** (or equivalent) so classes and students have a home. Use governed flows or, for edge cases, **Advanced/Admin** changelists with tenant `urlconf` (see evidence pages: academic years, departments).
3. **Users and roles:** Teachers, staff, and (if in scope) parent accounts — with **role-appropriate** access; avoid giving everyone `settings.manage`.
4. **Students and classes:** Student profiles, classroom assignments — until this exists, **Student 360** and many reports have little to show.

**School activation (in-product):** The tenant can open **`/siteconfig/onboarding/`** (`siteconfig:onboarding`) to see a **read-only** checklist and completion percentage from **real** `AcademicYear`, `Department`, people, and package rows — not a separate wizard. Use it in CS calls to show progress without faking “done” states.

**Evidence (optional for confidence):** Ask them to open one read-only page from `LAUNCH_SMOKE_TEST.md` step 6 to confirm year/term/publish data appears as you enter it.

## 4. First success milestone

- **View dashboard:** Operator sees **backend dashboard** (`/backend/` → `accounts:backend_dashboard`) or the portal home for the role you created — no 500, correct tenant.
- **Run or view a report (real data path):**  
  - **Output / PDF:** Use an existing report path the tenant is entitled to (e.g. report card builder + preview, or parent/staff download where publish rules allow). **Do not** promise a one-click “generate all PDFs” story unless the deployment runs the **management command / job** you actually use.  
  - **Scheduled delivery:** If they use scheduled reports, show the **Scheduled report delivery** hub and the next run row — state clearly that the **process** (Celery/cron) must be running in their environment for email delivery.

## 5. Demo-to-live transition

- **Freeze the pilot scope:** List which modules and hosts are in **v1 go-live** (e.g. portal + academics + one report type).
- **Data:** If pilot used seed data, plan **import or cutover** of real SIS/people data with your migration/interop runbook.
- **Cut DNS / hosts:** Point production subdomain to the go-live service; re-verify `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `SESSION_COOKIE_DOMAIN`.
- **Run smoke again:** `LAUNCH_SMOKE_TEST.md` on the **production** school host with a real operator account; capture sign-off in `STAGING_RELEASE_EXECUTION.md`-style (date, SHA, operator).
- **Support:** One named channel (email, ticket, or Slack) and escalation path — **not** a product feature, but required for a first customer.

## Related

- `GTM_HANDOFF.md` — positioning and handoff.  
- `DEMO_SCRIPT.md` — first demo narrative.  
- `docs/deployment/STAGING_RELEASE_EXECUTION.md` — how you proved staging.  
- `PRICING_PACKAGES.md` — align what they pay for with `Plan` / `included_features` in the database.
