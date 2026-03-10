# Where to See All Master Platform Checklist Work After Deploy

**Single source of truth:** [MASTER_PLATFORM_CHECKLIST.md](MASTER_PLATFORM_CHECKLIST.md) (phase log + full checklist).  
**Plan:** `.cursor/plans/master_platform_checklist_single_plan_*.plan.md` (phase order and principle).

After deployment, use this page to verify every visible and technical outcome.

---

## 1. In the app (Control plane)

Log in as a **super-admin** and open the **Control plane** (manager host, e.g. `https://<manager-host>/super/`).

### Sidebar — new or updated links

| Label | URL | What you see |
|-------|-----|----------------|
| **Runtime inspector** | `/super/runtime-inspector/` | Inspect a school: effective blueprint, active packs, route, override sources, compilation trace, localization, integrations. Quick-pick list of schools. |
| **Metadata catalog** | `/super/metadata-catalog/` | **Platform catalog** card at top (schema, experience, runtime, registry, integration, governance). Below: entity/field catalog when metadata app is seeded. |
| **Registries** | `/super/registries/` | Existing registries overview. |
| **Tenant Health**, **Migration**, **Support**, etc. | (existing) | Unchanged; still in sidebar. |

**Direct URLs (bookmark these):**

- Runtime inspector: `https://<your-manager-host>/super/runtime-inspector/`
- Metadata catalog: `https://<your-manager-host>/super/metadata-catalog/`

---

## 2. In the repo (files added or changed)

### Docs (planning and architecture)

| File | Purpose |
|------|--------|
| `docs/MASTER_PLATFORM_CHECKLIST.md` | Single checklist: phase log + Sections 1–20, all items checked with references. |
| `docs/WHERE_TO_SEE_MASTER_CHECKLIST_AFTER_DEPLOY.md` | This file: where to see everything after deploy. |
| `docs/RENDER_AFTER_MASTER_CHECKLIST_DEPLOY.md` | Render: why app “looks the same”, which Shell commands to run, what was added. |
| `docs/architecture/bounded_contexts.md` | Bounded contexts, ownership, allowed imports. |
| `docs/architecture/canonical_education_graph.md` | Canonical entities, ownership, source-of-truth. |
| `docs/architecture/central_metadata_catalog.md` | Catalog categories, metadata rules, lineage. |
| `docs/architecture/exception_discipline.md` | Domain exceptions, broad-except inventory. |
| `docs/architecture/orchestration_layer.md` | MigrationRun, orchestration, rollback, visibility. |
| `docs/architecture/permissions_and_scope.md` | Tenant context, scope, governor limits. |
| `docs/architecture/phases_11_25_implementation.md` | Phases 11–25 implementation summary. |
| `docs/architecture/siteconfig_decomposition.md` | Siteconfig split, target consoles, config safety. |

### Code (APIs and tooling)

| File | Purpose |
|------|--------|
| `apps/events/catalog.py` | Event catalog: event types, payload keys, helpers. |
| `apps/siteconfig/metadata_catalog.py` | Central metadata catalog API: `get_catalog()`, `get_schema_metadata()`, etc. |
| `apps/platform_runtime/runtime_inspector.py` | Runtime inspector: `inspect_runtime()`, `get_runtime_inspection_for_school()`. |
| `apps/schools/super_views.py` | `super_runtime_inspector`, `super_metadata_catalog` (wired to new APIs). |
| `apps/schools/control_plane_nav.py` | Sidebar: **Runtime inspector**, **Metadata catalog**. |
| `templates/schools/super_runtime_inspector.html` | Runtime inspector page (blueprint, packs, overrides, trace). |
| `templates/schools/super_metadata_catalog.html` | Metadata catalog page (platform catalog card + entity table). |

### Scripts and CI

| File | Purpose |
|------|--------|
| `scripts/check_repo_hygiene.py` | Fails CI on conflict markers and backup/debris files. |
| `scripts/lint_bounded_context_imports.py` | Fails CI on bounded-context import violations (`--strict`). |
| `scripts/check_no_hardcoding.py` | Allowlist for payment_processors, translations; flags region hardcoding. |
| `scripts/pre_deploy_gate.sh` | Runs hygiene, bounded-context lint, Django check, tests, etc. |

---

## 3. Confirm deploy and cache

### On Render (or your host)

1. **Deploy:** Trigger a deploy from the branch that has the Master Platform Checklist commit (e.g. “Clear build cache & deploy”).
2. **Shell (optional):**
   ```bash
   git log --oneline -1
   ```
   Should show the Master Platform Checklist commit.
   ```bash
   python manage.py check
   python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
   ```

### In the browser

1. Open the **Control plane** (manager URL).
2. In the sidebar, confirm **Runtime inspector** and **Metadata catalog**.
3. Open **Runtime inspector** → pick a school → click **Inspect** → confirm cards (Effective blueprint, Active packs, Override sources, etc.).
4. Open **Metadata catalog** → confirm the **Platform catalog** card at the top (schema, experience, runtime, registry, integration, governance).

---

## 4. One-page checklist

- [ ] Control plane sidebar shows **Runtime inspector** and **Metadata catalog**.
- [ ] `/super/runtime-inspector/` loads; inspecting a school shows blueprint, packs, overrides, trace.
- [ ] `/super/metadata-catalog/` loads; **Platform catalog** card is visible at top.
- [ ] `docs/MASTER_PLATFORM_CHECKLIST.md` exists; phase log shows Phases 1–25 complete; all section checkboxes are `[x]`.
- [ ] Repo contains `apps/events/catalog.py`, `apps/siteconfig/metadata_catalog.py`, `apps/platform_runtime/runtime_inspector.py`, and the scripts above.

When all are true, the Master Platform Checklist work is visible and verifiable after deployment.
