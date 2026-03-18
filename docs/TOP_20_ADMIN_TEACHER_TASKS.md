# Top 20 admin / teacher tasks (BR-02)

Command palette (Ctrl+K) and role-home should cover these intents first.

| # | Role | Task | Primary surface |
|---|------|------|-----------------|
| 1 | Admin | Add student | backend_student_create |
| 2 | Admin | Add teacher | backend_teacher_create |
| 3 | Admin | Staff list | backend_teacher_list |
| 4 | Admin | Finance / invoices | finance:dashboard |
| 5 | Admin | Workflow queue | studio_os:workflow_center |
| 6 | Admin | Studio shell | studio_os:shell |
| 7 | Admin | Setup / onboarding | siteconfig:guided_onboarding |
| 8 | Admin | Reports / exams | reports:publish_term_results |
| 9 | Admin | Import grades | evals:grade_import_upload |
| 10 | Admin | RBAC | accounts:rbac |
| 11 | Admin | Messages | accounts:user_messages |
| 12 | Admin | Document library | portal:document_library_manage |
| 13 | Teacher | My classes / roster | teacher dashboard / roster |
| 14 | Teacher | Grade entry | evals / reports flows |
| 15 | Teacher | Attendance | attendance surfaces |
| 16 | Teacher | Announcements | communication:announcement_create |
| 17 | Parent | Child profile | parent dashboard |
| 18 | Parent | Messages | messaging |
| 19 | Super | Create school | super:create_school_wizard |
| 20 | Super | Trust center | super:trust_center |

**Gap closure:** Extend `apps/dashboard/action_registry.py` `BACKEND_COMMAND_PALETTE` for any missing high-traffic URLs; remove duplicate sidebar entries per §8.0.4.
