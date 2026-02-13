# Multi-tenant: Creating a New School / Site

## Feature Control vs Super Admin

- **Feature Control Panel** (`/siteconfig/feature-control/`) controls **global** toggles: parent/teacher portals, offline mode, grade approval, PWA, etc. It does **not** create schools or sites.
- **Super Admin** (`/super/`) is where you **create and manage tenant schools**. Only users with role `SUPERADMIN` or `is_superuser` can access it.

## How to Create a New Site (School)

1. Log in as a **Super Admin** (role `SUPERADMIN` or Django superuser).
2. Open **Schools**:
   - From the portal sidebar: **Schools** (visible to SUPERADMIN/superuser), or
   - From Feature Control: click **Schools** in the header, or
   - Go directly to **`/super/`**.
3. On the Super Admin dashboard, click **Create School**.
4. Complete the wizard at `/super/create/` (1. Identity, 2. Region, 3. Branding, 4. Domain). Step 4 lets you optionally set a custom domain (e.g. portal.school.edu); the school can verify it later in Admin.
5. Submit; the form posts to **`POST /super/api/create-school/`**.
6. A **School** row is created and a **provisioning task** runs:
   - Admin user and `SchoolMembership`
   - Default academic year and terms
   - Optional subjects
   - School marked `is_active=True`
7. The new school is then used via **subdomain** (e.g. `slug.yourplatform.com`) or, after DNS/SSL, **custom domain**.

## Per-school vs Global

- **Global (Feature Control):** Offline mode master switch, PWA, grade approval, ministry APIs, etc. — one setting for the whole deployment. When Offline Mode is **on** globally, individual schools can still turn it **on or off** via the **Module Market** (see below).
- **Per-school (Module Market):** Each school gets its own set of modules: Library, Transport, Canteen, Cahier de Texte, **Offline Mode**, etc. You have full control: School A can have Offline + Library, School B can have only Cahier de Texte. Grading settings, region/language, and branding are also per school.

### Offline mode for a new school

1. **Global:** In Feature Control, ensure **Offline Mode** is enabled (so the platform allows offline at all).
2. **Per-school:** For the school that needs offline, go to that school’s backend → **Module Market** (or Grading Settings / Modules) and **activate “Offline Mode”**. Only schools with this module enabled get the offline status bar, sync API access, and PWA offline behavior for that school.

## Full control over which module each school gets

- **Module Market** is **per school**: when you’re in a school’s context (subdomain or selected school), **Settings → Modules** (or Module Market) lists all available modules. Activate or deactivate per school; sidebar and APIs only show/allow what that school has.
- **Feature registry** (in code) defines the list of modules (e.g. library, transport, cahier_de_texte, **offline_mode**). New modules can be added there and then appear in Module Market for every school; each school’s `School.features` JSON stores which are on.
- So: School A gets something, School B does not — use Module Market for that school and toggle the module on or off.

## Global Super Admin toggle

- In **Feature Control** → **Backend Tools**, the **“Super Admin / Schools”** flag controls whether the Super Admin UI is available.
- When **off**: `/super/` returns 403 (except the parent-tenant dashboard if applicable), and the **Schools** link is hidden from the sidebar and Feature Control header.
- Default is **on**. Turn it off to hide multi-tenant school creation for deployments that only need a single school.

## Tenant data isolation (RLS)

- On **PostgreSQL**, row-level security (RLS) is enabled on tenant-scoped tables so that when `app.current_school_id` is set by the middleware, queries only see rows for that school.
- RLS applies to: `schools_schoolmembership`, `people_teacherprofile`, `people_studentprofile`, academics (e.g. `academics_subject`, `academics_classroom`, `academics_attendance`), `finance_invoice`, `finance_payment`, `evals_evaluation`, `reports_reportcard`, `siteconfig_officialreporttemplate`, and related tenant tables.
- On SQLite/MySQL, RLS migrations are no-ops; application-level scoping by `request.school` still applies.

## Subject names per school

- **Subject** name is unique **per school**: the same name (e.g. “Mathematics”) can exist in different schools. Provisioning uses `get_or_create(school=school, name=name)` when seeding default subjects.

## Seed commands (school-aware)

- **seed_demo**, **seed_testdata_2425**, and **seed_buea_synthetic** accept an optional **`--school`** argument (school slug or ID). When provided, all created academics (years, terms, departments, subjects, etc.) are scoped to that school. When omitted, data is created with `school=None` (global/legacy).
- Example: `python manage.py seed_demo --school demo-school` or `python manage.py seed_testdata_2425 --school 1`.

## Verify RLS (PostgreSQL)

- Run **`python manage.py verify_tenant_rls`** to confirm RLS is enabled on all tenant tables. On PostgreSQL it checks each table and reports any missing or disabled RLS. On SQLite/MySQL it skips with a note. Use after deployment to PostgreSQL.

## Verification and completeness

For a checklist that maps all multi-tenant requirements (data isolation, provisioning, feature toggles, regional flexibility, Super Admin, usage monitoring) to the codebase and notes optional improvements, see **[MULTI_TENANT_VERIFICATION_AND_IMPROVEMENTS.md](MULTI_TENANT_VERIFICATION_AND_IMPROVEMENTS.md)**.

## Quick Links

| Action | Where |
|--------|--------|
| Toggle portals, offline master switch, PWA, Super Admin UI, etc. | Feature Control → `/siteconfig/feature-control/` |
| Create a new school | Schools → `/super/` → Create School (when Super Admin UI is on) |
| Enable/disable modules for a school (e.g. Offline, Library, Cahier) | Backend → Module Market (`siteconfig:module_market`) |
| School grading / language | Backend → Grading Settings (`siteconfig:grading_settings`) |
