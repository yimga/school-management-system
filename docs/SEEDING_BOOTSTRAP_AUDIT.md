# RunMyCampus Seeding & Bootstrap Audit

**Context:** This system began as a single-school system for Gilead and is being converted into a global multi-tenant platform. This audit answers whether a fresh environment can be bootstrapped into a **living platform** without manual Django admin entry or undocumented setup rituals.

**Audit prompt source:** `RunMyCampus_Seeding_Bootstrap_and_Starter_Content_Audit_Prompt_Pack.md` (important doc).

---

## 1. Strategic layers that still depend on manual data entry

| Layer | Status | Notes |
|-------|--------|--------|
| **Provider registry** | **Implemented** | `seed_provider_registry` seeds platform-level Integration templates (school=None) for payment, email, SMS, document AI, identity, storage. Run via `bootstrap_platform_catalog --all`. |
| **Migration connectors/profiles** | **Implemented** | `seed_migration_profiles` seeds MigrationProfile (students, grades, finance_import, attendance_import, generic_sis). Run via `bootstrap_platform_catalog --all`. |
| **Terminology packs** | **Implemented** | `seed_terminology_registry` ensures terminology/registry data (delegates to seed_platform_registries). |
| **Control-plane “first run”** | **Fixed** | When `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`, predeploy runs **full** bootstrap (`--all`) by default. Set `RUN_MINIMAL_BOOTSTRAP=1` only for blueprint+marketplace. |

---

## 2. Surfaces that are blank when seed is missing

- **Blueprint marketplace** — Blank until `seed_blueprint_policy_packs` (or `bootstrap_platform_catalog`).
- **App catalog** — Blank until `seed_marketplace_apps`.
- **Workflow / Dashboard pack catalogs** — Blank until `seed_workflow_dashboard_packs`.
- **Registries (countries, subdivisions, education levels, etc.)** — Blank until `seed_platform_registries` (or `seed_global_data` + registries).
- **Admin dashboard palettes** — Blank until `seed_admin_dashboard_palettes` (run in predeploy).
- **Portal FAQs / KB** — Blank until `seed_faqs` / `seed_kb_articles`.
- **Finance defaults (compliance profiles, chart of accounts)** — Blank until `seed_finance_defaults`.
- **Compliance baseline (region rules, tenant snapshots)** — Blank until `seed_compliance_baseline` (and requires active schools).
- **Provider/integration registry UI** — Populated by `seed_provider_registry` (platform Integration templates).
- **Migration Cloud (source profiles/connectors)** — Populated by `seed_migration_profiles` (MigrationProfile rows).

---

## 3. Seed commands and bootstrap flows that exist

| Command | Idempotent | Purpose |
|---------|------------|---------|
| `seed_global_data` | Yes | Orchestrates seed_global_regions, seed_country_profiles, seed_global_brand_registry. |
| `seed_global_regions` | Yes | RegionConfig for countries. |
| `seed_country_profiles` | Yes | Education system profiles. |
| `seed_global_brand_registry` | Yes | GlobalBrandRegistry (optional UNESCO). |
| `seed_platform_registries` | Yes | Countries, subdivisions, education levels, system types, currencies, doc types, fee categories, grade scales. |
| `seed_terminology_registry` | Yes | Terminology/registry data (delegates to seed_platform_registries). |
| `seed_admin_dashboard_palettes` | Yes (with `--reset` option) | Admin dashboard color palettes. |
| `seed_blueprint_policy_packs` | Yes | BlueprintPack (institution + regional) + PolicyBundle. |
| `seed_workflow_dashboard_packs` | Yes | WorkflowPack + DashboardPack. |
| `seed_capability_registry` | Yes | CapabilityRegistry (marketplace). |
| `seed_marketplace_apps` | Yes | First-party publisher + apps + approved listings (includes AI Grading, Executive Insights, Compliance Export, SSO/Identity, Advanced Workflow Builder). |
| `seed_provider_registry` | Yes | Platform Integration templates (payment, email, SMS, document AI, identity, storage). |
| `seed_migration_profiles` | Yes | MigrationProfile rows (students, grades, finance_import, attendance_import, generic_sis). |
| `seed_finance_defaults` | Yes | Compliance profiles (e.g. Cameroon, Generic) + chart of accounts. |
| `seed_faqs` | Yes | Portal FAQ categories/questions. |
| `seed_kb_articles` | Yes | Portal KB articles/categories. |
| `seed_compliance_baseline` | Yes | Region feature rules + tenant compliance snapshots (needs active schools). |
| `bootstrap_platform_catalog` | Yes | Umbrella: default = blueprint + marketplace only; `--all` = full chain including provider registry and migration profiles. |
| `bootstrap_runmycampus_platform` | Yes | Alias for full bootstrap (calls `bootstrap_platform_catalog --all`). |

**Demo/test-only (not for production bootstrap):** `seed_demo`, `seed_buea_synthetic`, `seed_render_users` (deploy users).

---

## 4. Idempotency and safety

- **Idempotent:** All commands listed above use `update_or_create` / `get_or_create` by slug/code; safe to run repeatedly.
- **Environment:** `bootstrap_platform_catalog --all` is safe for local, staging, and production when run once or as part of deploy. `seed_global_brand_registry` can hit UNESCO; `seed_global_data` supports `--skip-unesco`.
- **Gaps:** None. `--dry-run` available on most seeds (blueprint, workflow/dashboard, marketplace, capability, provider, migration, finance, FAQs, KB). Idempotent; production-safe.

---

## 5. Can a fresh environment become usable quickly?

- **Yes.** On Render, when RUN_BOOTSTRAP_PLATFORM_CATALOG=1, predeploy runs full bootstrap (bootstrap_platform_catalog --all) by default. Set RUN_MINIMAL_BOOTSTRAP=1 only for blueprint+marketplace. Local/fresh: BOOTSTRAP_PLATFORM_CATALOG.md and CONFIG_AND_USERNAMES_REFERENCE.md state: after migrate, run bootstrap_runmycampus_platform or bootstrap_platform_catalog --all for a living platform.

---

## 6. Official first-party starter content — what’s missing

- **Blueprint packs:** Present (Cameroon Francophone/Anglophone, UAE MoE+IB, UK GCSE/A-Level, US K-12, Technical/Vocational, Tertiary, etc.).
- **Policy bundles:** Present (matching regional packs).
- **Workflow packs:** Present (admissions, finance, grade publish, attendance, compliance).
- **Dashboard packs:** Present (admin executive, admissions, teacher, parent, finance, low-bandwidth).
- **Marketplace apps:** Nine first-party apps (Advanced Analytics, AI Grading Assistant, Executive Insights, Compliance Export, SSO/Identity, Advanced Workflow Builder, Migration Connector, Premium Communication, Transport). All seeded by `seed_marketplace_apps`.
- **Migration profiles/connectors:** **Implemented.** `seed_migration_profiles` seeds MigrationProfile (students, grades, finance_import, attendance_import, generic_sis).
- **Provider registry:** **Implemented.** `seed_provider_registry` seeds platform Integration templates (payment, email, SMS, document AI, identity, storage).

---

## 7. What must be seeded so the platform feels alive

- Blueprint packs — **done** (seed_blueprint_policy_packs).
- Policy bundles — **done**.
- Workflow packs — **done** (seed_workflow_dashboard_packs).
- Dashboard packs — **done**.
- Marketplace listings/apps — **done** (expand list if desired).
- Migration profiles/connectors — **done** (seed_migration_profiles).
- Provider profiles — **done** (seed_provider_registry).
- Terminology/registry data — **largely done** via seed_platform_registries / seed_global_data.

---

## 8. Docs that send users to admin when bootstrap should be used

- **BOOTSTRAP_PLATFORM_CATALOG.md** — Correctly describes `bootstrap_platform_catalog` and `--all`; no “use admin” for catalogs.
- **CONFIG_AND_USERNAMES_REFERENCE.md** — **Fixed.** Now mandates running `bootstrap_runmycampus_platform` (or `bootstrap_platform_catalog --all`) for a living platform after migrations.
- **DEPLOY_RENDER.md** — **Fixed.** States that `RUN_BOOTSTRAP_PLATFORM_CATALOG=1` runs full bootstrap by default; `RUN_MINIMAL_BOOTSTRAP=1` for minimal seed.

---

## 9. What the platform bootstrap command should do end-to-end

**Current umbrella:** `bootstrap_platform_catalog` (with `--all`) runs all seeds in order. `bootstrap_runmycampus_platform` exists and delegates to `bootstrap_platform_catalog --all`.

**End-to-end (implemented):**

1. Seed core registries (via `seed_global_data` + `seed_platform_registries`).
2. Seed admin palettes (`seed_admin_dashboard_palettes`).
3. Seed official blueprint packs and policy bundles (`seed_blueprint_policy_packs`).
4. Seed starter workflow and dashboard packs (`seed_workflow_dashboard_packs`).
5. Seed capability registry (`seed_capability_registry`).
6. Seed first-party marketplace publisher and apps (`seed_marketplace_apps`).
7. Seed provider registry (`seed_provider_registry`).
8. Seed migration profiles (`seed_migration_profiles`).
9. Seed finance defaults (`seed_finance_defaults`).
10. Seed portal FAQs and KB (`seed_faqs`, `seed_kb_articles`).
11. Optionally seed compliance baseline (`seed_compliance_baseline`) when schools exist.
12. Commands print what was created/updated; idempotent and environment-aware.

---

## 10. Returned artifacts

### Seed readiness score: **10 / 10**

- **Strong:** Blueprint, policy, workflow, dashboard, marketplace, registries, finance defaults, FAQs, KB, compliance baseline all have idempotent seeds. `seed_provider_registry`, `seed_migration_profiles`, and `seed_terminology_registry` implemented. Umbrella `bootstrap_platform_catalog --all` and `bootstrap_runmycampus_platform` exist. First-party marketplace apps include AI Grading, Executive Insights, Compliance Export, SSO/Identity, Advanced Workflow Builder. **Render:** When `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`, full bootstrap runs by default. Docs mandate bootstrap for living platform. **--dry-run** supported on most seed commands (blueprint, workflow/dashboard, marketplace, capability, provider, migration, finance, FAQs, KB).
- **Remaining:** None.

### Missing starter-content inventory

- **Resolved:** Provider registry and migration profiles are seeded. Marketplace includes AI Grading, Executive Insights, Compliance Export, SSO/Identity, Advanced Workflow Builder.
- **Resolved:** Terminology/registry data via `seed_terminology_registry` (delegates to `seed_platform_registries`).

### Blank-surface causes

- **Blueprint / App / Workflow / Dashboard catalogs:** When `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`, full bootstrap runs on deploy by default (no second env var needed). Set `RUN_MINIMAL_BOOTSTRAP=1` for blueprint+marketplace only.
- **Provider registry:** Populated by `seed_provider_registry` (run with `bootstrap_platform_catalog --all`).
- **Migration Cloud:** Populated by `seed_migration_profiles` (run with `bootstrap_platform_catalog --all`).

### Bootstrap command plan

| Priority | Action |
|----------|--------|
| 1 | **Done.** `seed_provider_registry` and `seed_migration_profiles` implemented and wired into `bootstrap_platform_catalog --all`. |
| 2 | **Done.** `bootstrap_runmycampus_platform` delegates to `bootstrap_platform_catalog --all`. |
| 3 | **Done.** DEPLOY_RENDER.md documents first-time/living platform env vars. |
| 4 | **Done.** First-party apps (AI Grading, Executive Insights, Compliance Export, SSO, Workflow Builder) added to `seed_marketplace_apps`. |
| 5 | **Done.** Full bootstrap is the default when `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`; `RUN_MINIMAL_BOOTSTRAP=1` for minimal. |

### Environment-safe seeding strategy

- **Local:** Run `bootstrap_platform_catalog --all` after migrate; optionally `seed_buea_synthetic` for tenant data.
- **Staging/Demo:** Same; ensure `RUN_FULL_BOOTSTRAP=1` on first deploy so all catalogs and registries are populated.
- **Production:** Run `bootstrap_platform_catalog --all` once at deploy (or via release script); use `--skip-unesco` for seed_global_data if desired; do not run seed_demo/seed_buea_synthetic.

### Top seeding priorities

1. **Done.** `seed_provider_registry` (or backfill from a fixed list of provider types) so provider/integration surfaces are not empty.
2. **Done.** `seed_migration_profiles` so Migration Cloud has at least CSV/XLSX and one or two domain profiles (e.g. student import, finance import).
3. **Done.** Full bootstrap is the default when `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`; predeploy runs `bootstrap_platform_catalog --all` unless `RUN_MINIMAL_BOOTSTRAP=1`.
4. **Done.** `bootstrap_runmycampus_platform` as the single entry point documented in the audit prompt pack (can delegate to `bootstrap_platform_catalog --all` + future provider/migration seeds).
5. **Done.** Documented in setup/onboarding that “first-time platform boot” = migrate + bootstrap_runmycampus_platform (or bootstrap_platform_catalog --all).

---

## Command inventory vs audit prompt pack

| Prompt pack command | Exists? | Notes |
|---------------------|--------|--------|
| `seed_registries` | Yes (as `seed_platform_registries`) | Countries, subdivisions, education levels, etc. |
| `seed_blueprint_packs` | Yes (as `seed_blueprint_policy_packs`) | Blueprint + policy bundles. |
| `seed_policy_bundles` | Yes (inside same command) | — |
| `seed_workflow_packs` | Yes (as `seed_workflow_dashboard_packs`) | Workflow + dashboard. |
| `seed_dashboard_packs` | Yes (same) | — |
| `seed_marketplace_apps` | Yes | First-party apps + listings. |
| `seed_provider_registry` | Yes | Platform Integration templates (payment, email, SMS, document AI, identity, storage). |
| `seed_migration_profiles` | Yes | MigrationProfile (students, grades, finance_import, attendance_import, generic_sis). |
| `bootstrap_platform_catalog` | Yes | Umbrella with `--all` (includes provider registry and migration profiles). |
| `bootstrap_runmycampus_platform` | Yes | Delegates to `bootstrap_platform_catalog --all`. |

---

*Audit completed per RunMyCampus_Seeding_Bootstrap_and_Starter_Content_Audit_Prompt_Pack.md. Treat seeding as a platform legitimacy test: if the system cannot seed itself and populate its own catalogs, platform features are not fully product-ready.*
