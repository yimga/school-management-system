# Test matrix by blueprint family

**Purpose:** Document how tests are grouped or run by blueprint family (Phase 12 / PLAN_COMPLIANCE). Ensures runtime and policy behavior can be verified per family without requiring a full fixture matrix.

**Reference:** PLAN_COMPLIANCE.md Phase 12 "Test matrix by blueprint family"; REMAINING_PHASES_EXECUTION_ORDER Phase 12.

---

## Current implementation

- **Runtime shape by family:** `apps/platform_runtime/tests/test_runtime_by_blueprint_family.py` asserts that `runtime.modules.admissions`, `runtime.modules.gradebook`, and `runtime.modules.finance` have the expected keys and that policy overrides are respected. Tests use `TenantContext.empty()` (no real school); blueprint family is not yet varied in fixtures.
- **Pytest marker:** Tests in that module are marked `blueprint_family` so you can run only those:

  ```bash
  pytest apps/platform_runtime/tests/test_runtime_by_blueprint_family.py -v
  # or with marker (if registered):
  pytest -m blueprint_family -v
  ```

- **Blueprint families (from seed):** `early_learning`, `primary`, `secondary`, `combined`, `international`, `technical`, `tertiary`, `multi_campus`.

---

## How to extend

1. **Add fixtures per family:** Create schools (or tenant contexts) with different `BlueprintPack` / family and run the same runtime assertions per family.
2. **Add more module slices:** Extend tests to cover `runtime.modules.compliance`, `runtime.modules.communication`, etc., using the same pattern.
3. **CI:** Run `pytest apps/platform_runtime/tests/test_runtime_by_blueprint_family.py` in CI so the matrix is exercised on every change.

---

## Done when

- [x] Doc exists (this file).
- [x] Reference test file exists and is runnable.
- [x] One test with real School fixture: `test_runtime_from_real_school_fixture` creates a School in DB, builds TenantContext and runtime, and asserts module shape.
- [ ] Optional: per–blueprint-family school fixtures for full matrix (when needed).
