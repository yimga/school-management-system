# After Deploying the Master Platform Checklist — What You See & What to Run on Render

## Why the app "looks the same" after deploy

The **Master Platform Checklist** commit added mainly **documentation and backend/API code**, not new UI:

| What was added | Visible in the app? |
|----------------|----------------------|
| **Docs:** MASTER_PLATFORM_CHECKLIST.md, bounded_contexts, canonical_education_graph, siteconfig_decomposition, central_metadata_catalog, permissions_and_scope, phases_11_25, orchestration_layer, exception_discipline | No — these are in the repo only |
| **Backend:** Event catalog (`apps/events/catalog.py`), Metadata catalog API (`apps/siteconfig/metadata_catalog.py`), Runtime inspector (`apps/platform_runtime/runtime_inspector.py`) | No — no admin or control-plane **pages** were added that call them |
| **CI / scripts:** Repo hygiene, bounded-context lint, no-hardcoding allowlist, test fix | No — used in CI / pre-deploy gate, not in the browser |
| **Existing config UI:** Site Settings, Theme & Experience, Feature Control, etc. | Yes — same as before; the checklist *documents* these as the target "consoles" |

So **you will not see new "system configuration" screens** until we add views that use the new APIs (e.g. a control-plane "Runtime inspector" page or "Metadata catalog" page). The checklist marks items complete by pointing at **existing** features and the new **backend** modules.

---

## Render: make sure the new code is live

### 1. Trigger a deploy (if you only pushed)

- **Render Dashboard** → your **Web** service (`school-management-system`) → **Deployments**.
- Click **"Manual Deploy"** → **"Deploy latest commit"** (or **"Clear build cache & deploy"** if you suspect an old build).
- Wait for **Build** and **Pre-Deploy** to finish. Pre-deploy runs:
  - `migrate_schemas --shared` and `migrate_schemas --tenant` (no plain `migrate`)
  - `seed_admin_dashboard_palettes`, `import_ui_config`, `collectstatic`, etc.

You do **not** need to run migrations or collectstatic again in Shell — the **Pre-Deploy Command** (`./scripts/release/render_predeploy.sh`) already does that.

### 2. Optional: run these in Render Shell after deploy

Open **Render Dashboard** → your Web service → **Shell**, then run for verification and cache refresh:

```bash
# Sanity
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

```bash
# Optional: DB health
python manage.py db_health_check
```

```bash
# If you see stale UI (old dashboard/config), clear app cache
python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
```

**Do not run in Shell when using tenant schemas:**

- `python manage.py migrate` — use pre-deploy’s `migrate_schemas` only.
- `python manage.py collectstatic` — pre-deploy already runs it.

### 3. Confirm the new code is on the instance

In Render Shell:

```bash
git log --oneline -3
```

You should see the Master Platform Checklist commit (e.g. `7a88b5f Master Platform Checklist: phases 1-25...`). If not, trigger a new deploy from the correct branch (usually `main`).

---

## Visible control-plane pages (added)

After deploy you can open:

1. **Runtime inspector** — **Control plane** (manager/super host) → **Runtime inspector** in the sidebar, or:  
   `https://<your-manager-host>/super/runtime-inspector/`  
   Enter a school UUID (or pick a school from the quick-pick list) and click **Inspect**. You’ll see effective blueprint, active packs, route, override sources, compilation trace, localization, and integrations.

2. **Metadata catalog** — **Control plane** → **Registries** area → **Metadata catalog**, or:  
   `https://<your-manager-host>/super/metadata-catalog/`  
   The top section shows the **platform catalog** (schema, experience, runtime, registry, integration, governance) from the Master Platform Checklist. Below that is the entity/field catalog (when the metadata app is seeded).
