# Gilead Residue Inventory

**Purpose:** Inventory and classify every `gilead` / `Gilead` reference for §2.2 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Remove all runtime-visible, UI-visible, default-facing, or seeded Gilead references; keep only historical references in migrations/archive.

**Status:** NOT DONE — inventory created; purge in progress.

---

## 1. Classification key

| Classification | Action |
|----------------|--------|
| historical migration only | Keep; migrations/0012, 0013, etc. (school slug/name for default tenant) |
| docs/archive only | Keep in docs/archive; optionally rename or add disclaimer |
| runtime/config risk | Remove or replace with RunMyCampus-neutral default |
| UI/branding risk | Remove; replace with platform-neutral or tenant-configurable |
| theme/style/report/default risk | Replace with RunMyCampus-neutral names; reseed defaults |

---

## 2. Inventory by location

### 2.1 Migrations (historical — keep or make additive/neutral)

| File | Reference | Notes |
|------|-----------|--------|
| apps/schools/migrations/0012_seed_default_gilead_school.py | gilead-school slug/name | Default tenant; consider renaming to runmycampus-demo or keeping as migration history |
| apps/schools/migrations/0013_link_default_admin_to_gilead.py | link admin to Gilead | Migration name; keep |
| apps/siteconfig/migrations/0011_themepack_defaults.py | slug "gilead-gradient", name "Gilead Gradient" | Theme seed; replace with RunMyCampus-neutral theme name |
| apps/siteconfig/migrations/0039_report_preview_defaults.py | report_preview_contact_email "reports@gileadtech.edu", footer "Gilead Technical High School" | Default strings; replace with RunMyCampus-neutral |
| apps/customers/migrations/0003_ensure_gilead_tenant_domain.py | ensure_gilead_tenant_domain | Migration name; keep |

### 2.2 Docs (archive / reference)

| File | Notes |
|------|--------|
| docs/archive/root_history/* (SECURITY_*, START_DEV_SERVER, etc.) | Historical; keep in archive |
| docs/PLATFORM_ACCESS_AND_CREDENTIALS.md | Gilead tenant credentials; rename to "default tenant" or "demo tenant" |
| docs/CURRENT_SETUP_AND_GOOD_TO_GO.md | Gilead school setup; use "default school" / "demo school" |
| docs/ADMIN_DASHBOARD_AND_SIDEBAR_PLAN.md | GileadAdminSite; code reference — rename to RunMyCampusAdminSite when touching |
| docs/RENDER_SSL_AND_TENANT_URLS.md | gilead-school subdomain example | Keep as example or use demo-school |
| docs/FRESH_DB_FIX.md, BUEA_SEED_*, etc. | Paths/DB names | Use runmycampus or generic names |
| docs/ADMIN_BLACK_THEME.md | "Gilead School Management" | Replace with "RunMyCampus" |
| docs/PHASE_7_COMPLETION.md | "Gilead School Management System", window.Gilead | Replace with RunMyCampus |
| docs/RunMyCampus_*.md, RUNMYCAMPUS_*.md | Audit/plan docs | Already RunMyCampus-focused |
| docs/THEMEPACK_AND_PLATFORM_REVAMP_PLAN.md | "Gilead Academic" theme | Replace with neutral name |
| docs/GILEAD_RESIDUE.md | Meta-doc about residue | Keep; update as purge completes |

### 2.3 Config / backups / seeds

| File | Notes |
|------|--------|
| backups/phase0/ui_config/*.json | "Gilead Modern", "Gilead Gradient", site_name "Gilead School System", sms_sender_id "GILEAD", report_preview_contact_email "reports@gileadtech.edu" | Backup; when re-seeding, use RunMyCampus-neutral names |

### 2.4 Code (runtime / UI risk)

| File | Reference | Risk | Action |
|------|-----------|------|--------|
| config/admin.py (if present) | GileadAdminSite | UI/branding | Rename to RunMyCampusAdminSite; update all references |
| apps/siteconfig/migrations/0011 | ThemePack "gilead-gradient", "Gilead Gradient" | Default theme | Data migration to rename or add RunMyCampus default; don’t expose "Gilead" in UI |
| apps/siteconfig/migrations/0039 | report_preview_* defaults | Report footer/email | Default to RunMyCampus; e.g. "Powered by RunMyCampus" |
| scripts/lint_gilead_residue.py | Scans for gilead | N/A | Keep; CI enforcement |
| scripts/generate_platform_inventory.py | Counts gilead refs | N/A | Keep |

### 2.5 Exclusions (allowed)

- `docs/archive/**` — historical only.
- Migration files that only create/update the default school slug/name for backward compatibility (document as "legacy default tenant slug").
- Test fixtures that explicitly test Gilead→RunMyCampus migration.
- Lint/scripts that scan for residue.

---

## 3. Actions

- [ ] Replace theme default names: "Gilead Gradient" → e.g. "RunMyCampus Gradient" or "Default Gradient"; reseed or migrate.
- [ ] Replace report_preview defaults (0039) with RunMyCampus-neutral text in new migration or default in model.
- [ ] Replace any "Gilead School System" / "Gilead Tech" in default site_name/tagline with "RunMyCampus" or generic.
- [ ] Rename GileadAdminSite to RunMyCampusAdminSite (or keep name but ensure no user-facing "Gilead" in admin).
- [ ] Update docs that reference "Gilead tenant" to "default tenant" or "demo school" where user-facing.
- [ ] Ensure no live UI, theme picker, report footer, or login page shows "Gilead" by default.
- [ ] Run scripts/lint_gilead_residue.py and fix any violations in apps/templates/config/fixtures (exclude migrations/docs per script).

---

## 4. Completion gate (§2.2)

- [x] No live UI or defaults mention Gilead (migration 0155: theme → RunMyCampus Gradient; report_preview → RunMyCampus-neutral).
- [x] No theme/report/header/style defaults mention Gilead (0155 normalizes; model default already "Powered by RunMyCampus.").
- [x] Historical references isolated to migrations/archive; CI (lint_gilead_residue) passes.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.2.*
