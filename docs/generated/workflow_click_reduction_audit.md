# Workflow Click Reduction Audit

Counts are estimates unless marked measured. No 50% reduction claim is made.

| Workflow | Current routes | Pain point | Proposed low-click path | Primary action | Measurement |
| --- | --- | --- | --- | --- | --- |
| teacher_attendance | `/portal/teacher/` | Teacher needs the next class action immediately. | Teacher Workspace next-action strip opens attendance for the active class. | Take attendance | hypothesis |
| marks_entry | `/portal/teacher/` | Marks entry should be reachable from pending work. | Pending work card links directly to marks grid. | Enter marks | hypothesis |
| report_generation | `/analytics/`, `/reports/` | Report generation can split between analytics and report surfaces. | Governed report builder exposes one primary generate/export action. | Generate report | hypothesis |
| parent_payment_receipt | `/finance/` | Payment must stay honest when PSP is external. | Money Center shows invoice, manual fallback, and receipt capture together. | Capture receipt | hypothesis |
| offline_conflict_resolution | `/offline/sync/` | Manager route must not dead-end; tenant queues must remain isolated. | Manager route explains tenant scope and sends operator to school selector. | Select school | measured local route |
| tenant_onboarding | `/platform-runtime/implementation/` | Go-live blockers need one ordered queue. | Implementation Command Center exposes go-live score and primary next action. | Resolve next blocker | hypothesis |
