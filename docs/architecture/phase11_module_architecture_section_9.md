# Phase 11 — Module Architecture (Section 9)

Each module split into five concerns: core domain, policy layer, workflow layer, presentation layer, integration layer. Reference implementation: **Admissions** (and Evals/Gradebook).

---

## Five concerns (definitions)

| # | Concern | Description |
|---|---------|-------------|
| 1 | **Core domain** | Stable business entities and rules (models, invariants, domain logic). |
| 2 | **Policy layer** | How this tenant is allowed to use the module (feature flags, config from policy/blueprint; no hardcoded tenant behavior). |
| 3 | **Workflow layer** | How actions move through states (approval chains, state machines, workflow_resolver, TenantWorkflow). |
| 4 | **Presentation layer** | Which dashboard, forms, widgets, views appear (dashboard_resolver, form_policy, role-based UI). |
| 5 | **Integration layer** | Search, reporting, messaging, AI, external apps (APIs, webhooks, LTI, OneRoster). |

---

## Module map (major modules and five-concern split)

| Module | Core domain | Policy layer | Workflow layer | Presentation layer | Integration layer |
|--------|-------------|---------------|----------------|--------------------|-------------------|
| **Admissions** | StudentProfile, admission number generation, required docs (people); application/enrollment entities | policy["admissions"], terminology.admission_number_label; TenantAdmissionNumberPolicy; get_effective_policy(school) | Optional approval/workflow via workflow_resolver | LinkChildForm, StudentOnboardingForm (apply_form_policy); portal onboarding views | — |
| **Evals / Gradebook** | Evaluation, Grade, Submission, rubric (evals); academic year, subject (academics) | policy["grading"], policy["grade_approval"]; get_grade_approval_policy(school) | Grade approval workflow (create_grade_approval_request, workflow_resolver for approval) | Marksheet views, grade approval list/detail; dashboard_for_role(teacher) | Import (evals.importers); reporting (reports) |
| **Academics** | Course, Subject, Classroom, Syllabus, Program (academics) | policy["grading_scale"], terminology; region/policy for term structure | Workflow for syllabus approval / course approval if configured | Syllabus views, class views; dashboard widgets | OneRoster, LTI (interop) |
| **Finance** | Invoice, Payment, FeeTemplate, Ledger (finance) | policy["payment_gateways"]; finance gateways registry from policy | Payment flows; optional approval workflows | Invoice/payment views; finance dashboard | PaymentProvider; billing webhooks |
| **People** | StudentProfile, TeacherProfile, Guardian, User (people, accounts) | policy["admissions"] for student numbering; RBAC, capability | Onboarding workflows; optional approval | Profile forms, list/detail views; apply_form_policy | — |
| **Portal** | PortalFeatureItem, FormSignature, LessonPlan, Document (portal) | terminology, form_policy; policy for labels/mode | workflow_resolver for form signature / approval | Portal templates, backend dashboard, parent/student views | AI copilot (portal); KB |
| **Reports** | ReportCard, ReportTemplate (reports) | policy["report_labels"], grading_scale, education_profile_code | — | Report views; report card PDF; dashboard widgets | BI/export (reports.services) |
| **Communication** | ContactRequest, channels (communication) | Channels, fallback order (policy/SiteSettings) | — | Contact forms, comms dashboard | MessagingProvider |
| **Siteconfig** | SiteSettings, DashboardTemplate, TenantLayoutAssignment, TenantWorkflow, WorkflowTemplate (siteconfig) | Policy merge; tenant_config; feature flags | workflow_resolver, workflow_engine; dashboard_resolver | Workflow hub, dashboard hub, tenant settings | — |
| **Compliance** | AuditLog, consent, evidence packs (compliance) | Retention, sensitivity (policy/compliance profile) | — | Admin/evidence views; inspector portal | Export, GDPR services |

---

## Reference implementation: Admissions

| Concern | Where implemented |
|---------|--------------------|
| **1. Core domain** | `people.StudentProfile`; admission number generation; required documents (model/clean). |
| **2. Policy layer** | `get_effective_policy(school)["admissions"]`, `terminology.admission_number_label`; TenantAdmissionNumberPolicy merged by resolver; `StudentProfile._get_admissions_policy(school)`; no direct SiteSettings in business logic. |
| **3. Workflow layer** | Optional approval/workflow via workflow_resolver; onboarding steps. |
| **4. Presentation layer** | `LinkChildForm(..., policy=...)`, `StudentOnboardingForm(..., policy=...)`; labels and validation from policy; portal link_child, student_onboarding_wizard. |
| **5. Integration layer** | — (admissions-specific integrations optional). |

**Reference:** policy_injection.md § Admissions module; section_22 (TenantAdmissionNumberPolicy); identifier_policy_service.

---

## Reference implementation: Evals / Gradebook

| Concern | Where implemented |
|---------|--------------------|
| **1. Core domain** | `evals`: Evaluation, Grade, Submission, rubric; academics: Course, Subject, Classroom. |
| **2. Policy layer** | `get_effective_policy(school)["grading"]`, `["grade_approval"]`; `get_grade_approval_policy(school)`; evals.approval uses policy only. |
| **3. Workflow layer** | Grade approval: create_grade_approval_request, approval roles and deadline from policy; workflow_resolver for approval definition. |
| **4. Presentation layer** | Marksheet view, grade approval list/detail; deadline_note, final_roles from policy; dashboard_for_role(teacher). |
| **5. Integration layer** | evals.importers (bulk grade import); reports (report cards). |

**Reference:** policy_injection.md § Gradebook/evals; evals.approval; phase1 grade_approval slice.

---

## Checklist summary (Section 9)

| Id | Requirement | Status |
|----|-------------|--------|
| 9.1 | Core domain — stable business entities and rules | Done per module (models, domain logic). |
| 9.2 | Policy layer — how tenant is allowed to use the module | Done: get_effective_policy, policy slices per module; Admissions/Evals reference. |
| 9.3 | Workflow layer — how actions move through states | Done: workflow_resolver, TenantWorkflow, grade approval, form signature. |
| 9.4 | Presentation layer — dashboard, forms, widgets, views | Done: dashboard_resolver, form_policy, role-based views. |
| 9.5 | Integration layer — search, reporting, messaging, AI, external apps | Done: search_api, reports, communication, interop, AI copilot. |

**Reference:** policy_injection.md, section_28_data_architecture_and_provisioning.md (28.6 module vs feature), section_23_injection_verification.md.
