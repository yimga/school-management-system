# Section 15 — Salesforce-style core: scope implemented and roadmap

**Purpose:** Close Phase 15 by documenting what is implemented vs roadmap for Section 15 (Universal Student 360, metadata-driven data layer, global ledger). Every part is either implemented or has a clear “done when” so nothing is deferred without scope.

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md Section 15; REMAINING_PHASES_EXECUTION_ORDER Phase 15.

---

## 15.1 — Universal Student 360

| Item | Status | Where / done when |
|------|--------|--------------------|
| Lifecycle (Admissions, Academic, Behavior, Financial, Health, Attendance, Parent, Alumni) | Implemented (services) | `apps/student360/services.py`: get_student_360_summary, get_student_timeline_feed, export_student_pack |
| Unified student graph / export pack | Implemented | student_360_page, student_360_export; sections_14_26_differentiators.md |
| Full 360 UI (single page, timeline, tabs) | Implemented | `templates/student360/student_360_page.html`: tabbed Summary, Academic, Finance, Attendance, Timeline; `student_360_page` view; services unchanged |
| Immutable transcript, cross-year archive | Roadmap | Add transcript model or export format; cross-year read-only archive view |

**Checklist 15.1:** Core services, export, and full tabbed UI done; immutable transcript and cross-year archive are roadmap with clear “done when” above.

---

## 15.2 — Metadata-driven data layer (DynamicField)

| Item | Status | Where / done when |
|------|--------|--------------------|
| Custom attributes without code/schema migrations | **Implemented** | apps/metadata: DynamicFieldDefinition, DynamicFieldValue (models, migrations); apps/metadata/services.py (get_dynamic_field_map, set_dynamic_field_value, etc.); apps/metadata/admin.py (admin for definitions and values). No DDL on core models. |
| Form-driven custom fields | **Implemented** | policy["forms"] and apply_form_policy for tenant overrides; DynamicField models + admin for first-class custom attributes. API/UI extensions per product. |

**Checklist 15.2:** **Complete.** DynamicField model, services, and admin implemented. Tenant/product can define and store custom attribute values per entity via admin; form_policy and API extensions when product prioritises.

---

## 15.3 — Global ledger

| Item | Status | Where / done when |
|------|--------|--------------------|
| Multi-currency, VAT/GST, scholarships | Implemented / partial | Finance models (Invoice, Payment, FeeTemplate); tax_engine; section_28; global_ledger_15_3.md |
| Payment plans, installments | Roadmap | Add payment plan model and installment schedule; invoice generation from plan |
| Double-entry ledger | Roadmap | Add ledger entries (debit/credit) or document integration with existing Invoice/Payment; global_ledger_15_3.md |

**Checklist 15.3:** Core finance and tax exist; payment plans and double-entry are roadmap with “done when” above.

---

## Phase 15 completion

- **Scope implemented or roadmap documented:** Yes — this doc.
- **Checklist Section 15 updated:** 15.1–15.3 have implemented vs roadmap; no item left without a clear “done when” or implementation reference.
