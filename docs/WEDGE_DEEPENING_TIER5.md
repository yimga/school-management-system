# Tier 5 wedge deepening (Phases III–V hook)

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11 Phases III–V and the North-star table (N1–N29). This doc is **not** a parallel roadmap—it records concrete Tier 4/5 instrumentation tied to that ledger.

## Tier 4 (observability / outbox)

- **Event catalog:** `GET /api/internal/north-star/event-catalog/` (staff). Includes `provisioning_started`, `provisioning_completed`, `learning_institution_packs_applied`, `learning_wedge_pack_applied` plus existing BR/package events.
- **Emit sites:** `schools.tasks._do_provision` (start/complete); `learning_institution_runtime.apply_learning_institution_packs` / `apply_single_wedge_pack_slug`.

## Tier 5 (wedge operator surfaces)

- **Wedge playbook API:** `GET /api/internal/north-star/wedge-playbook/` — delivery modes, institution types, ministry stub keys; **BR-11** (Clever/ClassLink native) remains **BLOCKED**; substitute = OneRoster + district hub (URLs in JSON).
- **N17 impact preview:** `GET /api/internal/north-star/package-impact/?package_id=…&school_id=…` — uses `PackageVersion.payload_sections` + `preview_diff`; falls back to stored `InstalledPackage.impact_summary` when no version row.

## Role home (N1/N6/N27/N28/N29)

- `build_north_star_recommended_steps` merges into `role_home_service` → `get_contextual_actions(recommended_steps=…)` for backend dashboard “next best.”

## N17 marketplace (done this increment)

- Tenant: **Review impact & install** → modal (`/settings/install-impact-preview/`).
- Control plane: **Preview impact** before **Install to sandbox**.
- `marketplace_app_installed` event + per-scope metadata lineage on `install_app`.

## Tier 4 Celery (catalog-wide)

- **`apps/platform_runtime/celery_task_events.py`:** `task_prerun` → `celery_task_started`, `task_postrun` → `celery_task_completed`, `task_failure` → `celery_task_failed` for every app task. Wired from `config/celery.py` and `PlatformRuntimeConfig.ready()` (eager/tests).
- **Note:** Tasks that catch exceptions and return error dicts (e.g. some AI tasks) still emit **completed** from Celery’s perspective; fix by re-raising if strict failure events are required.

## Next increments (ledger)

- Remaining Celery tasks → `celery_task_*` events.
- BR-13 premium pass (sidebar/touring). BR-11 still blocked.
