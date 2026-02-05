# EMIS and Evals Alignment

**Purpose**: Document which EMIS export fields come from evals and ensure export uses the same logic as report cards where relevant.

## Data sources

- **Performance (academic performance)**  
  EMIS performance export uses the same grade/evaluation data as report cards: **evals** (`Evaluation`, `AssessmentWeights`, term rankings). There is no separate "report card grade" model; both reports and EMIS read from evals.

- **Enrollment, students, teachers, subjects**  
  From `apps.people` and `apps.academics` (StudentProfile, TeacherProfile, Classroom, Subject, Term).

## Alignment with report cards

- When **SiteSettings.reports_use_approved_grades_only** is True, report context filters evaluations to approved (or non-approval) grades only.  
- EMIS performance export should apply the same filter when including grades in the export, so that "submitted to government" data matches what the school considers approved for report cards.  
- Implement in `emis/services.py` (or equivalent): when building performance/enrollment-with-grades export, respect `reports_use_approved_grades_only` and filter `Evaluation` the same way as `apps.reports.services` (e.g. use approved subject_assignment_ids or equivalent).

## Optional approval step

- Submitting to government (e.g. uploading to ministry portal) should remain a **manual** action.  
- Optional: add an approval step before "submit to government" (e.g. admin reviews export and confirms) and log the action in AuditLog.

## Reference

- Report context filtering: `apps/reports/services.py` (`_approved_or_unrequested_subject_assignment_filter`, `term_report_context`, `annual_report_context`).  
- Evals models: `apps/evals.models` (`Evaluation`, `GradeApprovalRequest`).
