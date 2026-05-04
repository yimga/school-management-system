# Domain events (internal-first)

Domain events are emitted from the **service layer only** and written to the transactional outbox (`DomainEvent`). Consumers (Celery, webhooks) process the outbox; no view or signal should perform side effects that belong in a consumer.

## Event type catalog

| Event type | Emitted from | Payload (typical) | Consumer use |
|------------|--------------|-------------------|--------------|
| `student.created` | `people.signals` (post_save StudentProfile, created=True) | `student_id`, `admission_number`, `school_id` | Sync to search, notify, workflows |
| `student.updated` | `people.signals` (post_save StudentProfile, created=False) | `student_id`, `school_id` | Sync, workflows, webhooks |
| `invoice.created` | `finance.services.create_fee_invoices` | `invoice_id`, `student_id`, `reference`, `issued_date` | Notify guardians, reminders |
| `payment.received` | `finance.services.create_payment_from_receipt` | `payment_id`, `invoice_id`, `student_id`, `school_id`, `amount`, `method`, `reference` | Notify, ledger sync, reporting |
| `grade.published` | `evals` approval path after publish | `school_id`, optional `evaluation_id`, `student_id`, `term`, `published_at` | Parents, reporting, webhooks |
| `workflow.triggered` | `siteconfig.workflow_engine` (action emit_event) | Config-defined | Webhooks, automation |
| `enrollment.created` | `academics.signals` (post_save StudentDegreeEnrollment, created=True) | `enrollment_id`, `student_id`, `program_id`, `school_id` | Notify, reporting |
| `attendance.recorded` | `academics.signals` (post_save Attendance); `people.signals` (post_save TeacherAttendance, created=True) | `attendance_id`/`teacher_attendance_id`, `student_id`/`teacher_id`, `date`, `status`, `school_id` | Dashboards, alerts |

## Emitting events

- Use `apps.events.services.emit_event(event_type, payload, school_id=..., idempotency_key=...)`.
- Emit **after** the business operation succeeds, in the same transaction when possible.
- Do not import vendor SDKs or perform I/O in the emit path; keep payload JSON-serializable.

## References

- `apps/events/services.py` — `emit_event`
- `apps/events/models.py` — `DomainEvent` outbox
- `apps/siteconfig/workflow_engine.py` — workflow action `emit_event`
