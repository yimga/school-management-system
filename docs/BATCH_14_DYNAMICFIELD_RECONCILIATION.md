# Batch 14 — DynamicField* reconciliation (siteconfig ↔ metadata)

**Authority:** [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md) Batch **14+** row. **Single execution SOT:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4.

## Status (repo vs environment)

**In this repository:** Phases **0–5b** are **implemented**: migration **`siteconfig.0168`** drops **`DynamicFieldValue`** then **`DynamicFieldDefinition`**; **`apps/siteconfig/models_metadata_catalog.py`** is **removed**; legacy siteconfig admin and **`admin/siteconfig/dynamicfield*/`** templates are **removed**; **`get_dynamic_field_map`** reads **`metadata_dynamicfield*`** only; **`METADATA_DYNAMICFIELD_SITECONFIG_FALLBACK`** and **`METADATA_DYNAMICFIELD_DUAL_WRITE_FROM_SITECONFIG`** default to **`False`** (compatibility only); **`siteconfig_dynamicfield_sync`** / **`manage.py sync_siteconfig_dynamicfields_to_metadata`** are **no-op** with an explicit retirement warning; **`siteconfig_dynamicfield_bridge.connect_siteconfig_dynamicfield_dual_write`** is a **no-op**. **Canonical:** **`apps.metadata.models.DynamicField*`** + **`apps.metadata.services`**.

**Per environment (honesty):** Do **not** claim “legacy tables merged away” or “5b complete” for a given database until **`python manage.py migrate`** has **applied `siteconfig.0168` on that database** and you have **verified** metadata parity for any migrated tenants. Greenfield databases that never had legacy rows: applying migrations through **0168** is sufficient.

**Historical copy from legacy EAV:** After **0168**, there are **no** `siteconfig_dynamicfield*` tables in the Django state, so **`sync_siteconfig_dynamicfields_to_metadata` cannot read legacy rows**. If a **production** database still held legacy rows **before** anyone applied **0168**, the operator must run the sync from a **git revision before 0168** (or run sync **before** applying **0168** on that DB). See the runbook below.

---

## 1. Problem statement (historical)

Two parallel implementations existed until **5b**:

| Location | Tables (historical) | Role |
|----------|---------------------|------|
| ~~`apps.siteconfig.models_metadata_catalog`~~ **removed** | ~~`siteconfig_dynamicfield*`~~ | Typed EAV (retired). |
| `apps.metadata.models` | `metadata_dynamicfield*` | **Canonical** engine (`get_dynamic_field_map`, `set_dynamic_field_value`); **`value_json`** envelope. |

A **rename-only** migration between table names was **invalid**: column sets and encodings differed.

---

## 2. Target architecture (current)

1. **Canonical runtime API:** **`apps.metadata.services`** + **`metadata_dynamicfield*`** only.
2. **Legacy siteconfig tables:** **removed** from Django schema when **0168** is applied.
3. **Admin:** **`metadata.apps`** **`register_both`** (tenant + platform); templates **`admin/metadata/dynamicfield*/change_form.html`**.

---

## 3. Phased execution (ledger)

| Phase | Scope | Exit criteria |
|-------|--------|----------------|
| **0–4** | Mapping, **`metadata.0009`** `required`, historical sync/fallback/dual-write (retired at **5b**) | **`dynamic_field_reconciliation.py`**; tests evolved to post-**5b** shape |
| **5a** | Canonical **`metadata.DynamicField*`** admin | **`register_both`**, metadata templates, **`test_batch14_phase5_admin_cutover`**, **`test_admin_ui_smoke`** (`admin:metadata_dynamicfield*_`) |
| **5b** | DDL retire legacy tables + code removal | **`siteconfig.0168`**; **`test_siteconfig_dynamicfield_batch14`** (retirement no-op + metadata map tests) |

---

## 4. Phase 5b operator runbook (production / staging)

Execute in order for each database that **ever** contained **`siteconfig_dynamicfield*`** rows:

1. **Backup** the database (snapshot or logical dump).
2. **Sync to metadata before dropping legacy tables:** run **`python manage.py sync_siteconfig_dynamicfields_to_metadata --dry-run`**, then without **`--dry-run`**, from a **code revision that still has** legacy models and a **working** sync implementation, **or** run that command **before** applying migration **0168** if your checkout already includes **0168** but migrate has not been applied yet. **After 0168 is applied**, the command is a **no-op** (warning only)—too late to copy rows via Django.
3. **Optional canary:** enable **`METADATA_DYNAMICFIELD_SITECONFIG_FALLBACK`** / **`METADATA_DYNAMICFIELD_DUAL_WRITE_FROM_SITECONFIG`** only on branches that still ship legacy models; on **current main** these paths are **retired** (defaults **False**).
4. **Apply migrations** so **`siteconfig.0168`** runs. **`DeleteModel`** order in migration: **`DynamicFieldValue`** first, then **`DynamicFieldDefinition`** (FK / table dependency safe order).
5. **Verify** sample tenants: custom field definitions/values in **`metadata_*`** only; application behavior and admin CRUD on **`metadata`** models.
6. **Only after migrate + verification** on that environment: treat docs/checklists for that environment as “legacy EAV tables removed.” Do not use “merged” language for the **repo** alone—clarify **migrations applied on DB X**.

---

## 5. Local development — pytest and SQLite test DB

The project uses a **file-backed** SQLite test database under **`.django_test_dbs/`** (see **`conftest.py`**, **`PYTEST_KEEPDB`** default **`1`**).

- If tests fail with **`no such table: siteconfig_dynamicfielddefinition`** (or similar), the cached test DB was likely created under an **inconsistent** migration/model state.
- **Fix:** close processes holding the file, then either delete **`.django_test_dbs/default.sqlite3`** or run tests with **`PYTEST_KEEPDB=0`** once so Django recreates the test database from current migrations (including **0168**).
- On **Windows**, if delete fails with “file in use,” stop other pytest/IDE processes using that path, then retry.

Suggested checks after a reset:

```bash
python manage.py check
python -m pytest apps/metadata/tests/test_siteconfig_dynamicfield_batch14.py apps/metadata/tests/test_batch14_phase5_admin_cutover.py -q
```

---

## 6. Code reference (current)

- **Mapping (helpers / docs):** `apps/metadata/dynamic_field_reconciliation.py`
- **Sync (retired at runtime):** `apps/metadata/siteconfig_dynamicfield_sync.py`; `manage.py sync_siteconfig_dynamicfields_to_metadata`
- **Bridge (no-op):** `apps/metadata/siteconfig_dynamicfield_bridge.py`
- **Runtime:** `apps/metadata/services.py` — `get_dynamic_field_map` (**metadata** rows only)
- **Settings:** `config/settings.py` — `METADATA_DYNAMICFIELD_SITECONFIG_FALLBACK`, `METADATA_DYNAMICFIELD_DUAL_WRITE_FROM_SITECONFIG` (**False**)
- **Canonical admin:** `apps/metadata/admin.py` + `metadata.apps` **`register_both`**
- **Migration:** `apps/siteconfig/migrations/0168_remove_legacy_dynamicfield_models.py`

---

## 7. IMPLEMENT_ALL / GAP program note

Batch **14** is tracked **here** and in SOT §11.4. **Phase GAP** closure remains per [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md).
