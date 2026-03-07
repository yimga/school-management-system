# Nuance Engine (Section 7 — Multi-Tenant Extensibility)

JSON-Logic only, no raw code. Schools inject custom logic at defined hook points without editing core code. Gated by plan/add-on (`nuance_engine` or `custom_logic`).

## Hook points and allowed context keys

| Hook point       | Allowed keys (whitelist) |
|-----------------|---------------------------|
| `tuition_calc`  | fee, student_id, gpa, sibling_count, years_enrolled, is_staff_child |
| `grade_weight` | score, weight, category, student_id |
| `attendance_alert` | attendance_rate, student_id, term_id |
| `fee_discount`  | fee, gpa, sibling_count, attendance_rate, is_staff_child |
| `generic`       | value |

Context is scrubbed to these keys before execution. Only allowed JSON-Logic operations run (var, and, or, not, &lt;, &gt;, &lt;=, &gt;=, ==, +, -, *, /, if, max, min).

## How to call from core code

1. **Check plan gating (optional for read; required for save):**
   ```python
   from apps.siteconfig.nuance_engine import nuance_engine_enabled
   if nuance_engine_enabled(school):
       ...
   ```

2. **Apply nuance at a hook:**
   ```python
   from apps.siteconfig.nuance_engine import apply_nuance

   context = {"fee": 1000.0, "gpa": 3.8, "sibling_count": 2}  # only allowed keys are passed through
   result = apply_nuance(school, "fee_discount", context)
   # result is read-only: your code decides how to apply it (e.g. discount amount, multiplier)
   ```

3. **Integration example (fee discount):**  
   In `create_fee_invoices` (finance), after building invoice lines, the engine is called with `fee_discount` and context `{fee, student_id, ...}`. If the result is a positive number, it is applied as a discount line (capped at invoice total).

## Safety and approval flow

- **Safety:** `verify_nuance_safety(logic_data, test_contexts, reject_negative_fee=True)` runs before approval. Rejects negative fees, invalid types, and crashes.
- **Human-in-the-loop:** Proposals go into **PendingNuance**. Admin uses action **Approve selected pending nuances**; approval runs safety checks, then creates/updates **CustomNuance** and marks PendingNuance as APPROVED.
- **Execution:** 50ms timeout (Unix); context scrub; read-only (logic returns a value, core applies it).

## Plan gating

- **Save:** CustomNuance and PendingNuance save is allowed regardless; admin shows a warning if `nuance_engine_enabled(school)` is False.
- **Execution:** `apply_nuance` only runs for schools that have an active CustomNuance; plan/addon can be used to hide the UI or block creation in your own views.

## Monetization

- Plan add-on: `custom_logic_enabled` or `nuance_limit`. Tiers: Basic (toggles only); Plus (rule builder / N AI rules); Pro (full nuance engine); Elite (cross-module + AI audit). Check `school.plan` / `is_feature_enabled(school, "nuance_engine")` before allowing save in school-facing UI.

## Files

- **Models:** `apps.siteconfig.models.CustomNuance`, `PendingNuance`
- **Runner:** `apps.siteconfig.nuance_engine` — `apply_nuance`, `verify_nuance_safety`, `nuance_engine_enabled`, `HOOK_REGISTRY`
- **Admin:** CustomNuance and PendingNuance registered in `apps.siteconfig.admin`; PendingNuance has **Approve** action.
