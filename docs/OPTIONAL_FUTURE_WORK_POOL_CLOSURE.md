# Optional / future-work pool — closure

**Purpose:** Record that all items in the optional/future-work pool have been implemented. The pool is **empty**; there is no remaining “next round” work in that set.

---

## 1. RUNMYCAMPUS_UI_IMPROVEMENTS.md — All Done

| Item | Status |
|------|--------|
| Command palette / global search (Ctrl+K) | **Done** — Control plane: Ctrl+K focuses search; manager search API returns nav + schools + incidents + subscriptions; empty query shows top shortcuts. |
| PDF export (single-page North Star + financial + operational) | **Done** — `GET /super/export/summary.pdf?month=YYYY-MM` (reportlab). |
| Per-user saved layout (DB) for super dashboard | **Done** — `SuperAdminDashboardPreference`; GET/POST `/super/api/dashboard-layout/`; section order persisted per user. |

See **docs/RUNMYCAMPUS_UI_IMPROVEMENTS.md** for design guidance and implementation status table.

---

## 2. MARKETING_PUBLIC_SURFACE_BACKLOG.md — All Done

- **Wave 3:** Buyer toolkit + implementation checklist, implementation timeline with role ownership, integration trust block (integrations page), public SLA/uptime (trust-center). **Done.**
- **Wave 4:** Conversion funnel dashboard (`/funnel-dashboard/`), evidence-driven copy by geo/utm, media optimization (lazy loading, etc.). **Done.**

See **docs/MARKETING_PUBLIC_SURFACE_BACKLOG.md** for full checklist.

---

## 3. LOCAL_FIRST_BACKLOG_STATUS.md

No pool items — doc records local-first/cost-control work as **complete**. No action.

---

## 4. GraphQL — Done

- **GraphQL:** Full schema at `POST /graphql/` using **config.schema** (graphene-django). Query: `health`, `me { username email isStaff isSuperuser }`, `schoolCount` (staff only), `schools(limit: N) { id name slug }` (staff only). Introspection supported.

---

## 5. Feedback module — Done

- **ProductFeedback** (siteconfig): region, module, title, description, status (Submitted / Planned / In Development / Released / Won't Do), upvotes. Admin: ProductFeedbackAdmin. **Roadmap view:** `/siteconfig/feedback-roadmap/` (staff) — lists Planned, In Development, Released.

---

## 6. Applications list + form draft — Done

- **Applications list:** `backend_applicant_list` at `/authentication/backend/applicants/` — search (q), filter by stage, CSV export (`?format=csv`). Applicant model (admissions funnel) with stages Lead → Enrolled.
- **Form draft for application:** FormDraft form_key `application_form`; `form_draft_url` passed in applicant list context so any "Add applicant" / long application form can use `GET/POST /siteconfig/api/form-draft/application_form/` to save/load draft.

---

## Summary

- **UI backlog (3 items):** Command palette, PDF export, per-user super layout — **all implemented.**
- **Marketing (Wave 3 + Wave 4):** **all implemented** per MARKETING_PUBLIC_SURFACE_BACKLOG.md.
- **GraphQL:** Full schema (config.schema) wired in graphql_view.
- **Feedback module:** ProductFeedback + feedback_roadmap view.
- **Applications list + draft:** Applicant list with search/filter/export + form_draft_url for application_form.
- **Optional/future-work pool:** **Empty.** All items in scope are implemented.

**Canonical refs:**  
- **docs/RUNMYCAMPUS_UI_IMPROVEMENTS.md**  
- **docs/MARKETING_PUBLIC_SURFACE_BACKLOG.md**
