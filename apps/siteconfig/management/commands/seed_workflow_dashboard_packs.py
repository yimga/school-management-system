"""
Phase 4: Seed initial Workflow Packs and Dashboard Packs (platform-level).
Idempotent: update_or_create by code.
"""

from django.core.management.base import BaseCommand

from apps.siteconfig.models_workflow import WorkflowPack
from apps.siteconfig.models_dashboard import DashboardPack


# §7 MARKETPLACE_SEED_TARGETS: workflow minimum 30+, dashboard minimum 20+. Idempotent by code.
WORKFLOW_PACKS = [
    {
        "code": "admissions-standard",
        "name": "Admissions Standard",
        "family": "admissions",
        "description": "Standard application and review flow.",
    },
    {
        "code": "admissions-interview-offer",
        "name": "Admissions Interview + Offer",
        "family": "admissions",
        "description": "Interview stage and formal offer workflow.",
    },
    {
        "code": "admissions-waitlist",
        "name": "Admissions Waitlist",
        "family": "admissions",
        "description": "Waitlist management and offer release.",
    },
    {
        "code": "admissions-document-verify",
        "name": "Admissions Document Verification",
        "family": "admissions",
        "description": "Document upload and verification workflow.",
    },
    {
        "code": "finance-basic",
        "name": "Finance Basic",
        "family": "finance",
        "description": "Single-approval fee and invoice workflow.",
    },
    {
        "code": "finance-dual-approval",
        "name": "Finance Dual Approval",
        "family": "finance",
        "description": "Dual approval for fees and refunds.",
    },
    {
        "code": "finance-refund-approval",
        "name": "Finance Refund Approval",
        "family": "finance",
        "description": "Refund request and approval chain.",
    },
    {
        "code": "finance-scholarship-review",
        "name": "Finance Scholarship Review",
        "family": "finance",
        "description": "Scholarship application and award workflow.",
    },
    {
        "code": "grade-publish-controlled",
        "name": "Grade Publish Controlled Review",
        "family": "gradebook",
        "description": "Controlled grade publication with review step.",
    },
    {
        "code": "grade-submission-deadline",
        "name": "Grade Submission Deadline",
        "family": "gradebook",
        "description": "Grade submission reminders and lock.",
    },
    {
        "code": "grade-appeals",
        "name": "Grade Appeals",
        "family": "gradebook",
        "description": "Grade appeal request and resolution.",
    },
    {
        "code": "attendance-escalation",
        "name": "Attendance Escalation",
        "family": "attendance",
        "description": "Absence escalation and counselor notification.",
    },
    {
        "code": "attendance-truancy",
        "name": "Attendance Truancy Alert",
        "family": "attendance",
        "description": "Truancy threshold and guardian notification.",
    },
    {
        "code": "attendance-makeup",
        "name": "Attendance Makeup Log",
        "family": "attendance",
        "description": "Makeup session and excuse workflow.",
    },
    {
        "code": "compliance-evidence-review",
        "name": "Compliance Evidence Review",
        "family": "compliance",
        "description": "Document and evidence review workflow.",
    },
    {
        "code": "compliance-audit-trail",
        "name": "Compliance Audit Trail",
        "family": "compliance",
        "description": "Audit log and retention workflow.",
    },
    {
        "code": "hr-staff-onboarding",
        "name": "HR Staff Onboarding",
        "family": "hr",
        "description": "New staff onboarding and checklist.",
    },
    {
        "code": "hr-leave-request",
        "name": "HR Leave Request",
        "family": "hr",
        "description": "Leave request and approval workflow.",
    },
    {
        "code": "hr-performance-review",
        "name": "HR Performance Review",
        "family": "hr",
        "description": "Annual review and goal setting.",
    },
    {
        "code": "communications-broadcast",
        "name": "Communications Broadcast",
        "family": "communications",
        "description": "Approved broadcast and announcement workflow.",
    },
    {
        "code": "communications-parent-outreach",
        "name": "Communications Parent Outreach",
        "family": "communications",
        "description": "Targeted parent communication campaigns.",
    },
    {
        "code": "enrollment-reenroll",
        "name": "Enrollment Re-enrollment",
        "family": "enrollment",
        "description": "Returning student re-enrollment flow.",
    },
    {
        "code": "enrollment-withdrawal",
        "name": "Enrollment Withdrawal",
        "family": "enrollment",
        "description": "Withdrawal request and exit checklist.",
    },
    {
        "code": "discipline-incident-report",
        "name": "Discipline Incident Report",
        "family": "discipline",
        "description": "Incident report and follow-up workflow.",
    },
    {
        "code": "discipline-appeal",
        "name": "Discipline Appeal",
        "family": "discipline",
        "description": "Discipline decision appeal and review.",
    },
    {
        "code": "reporting-data-export",
        "name": "Reporting Data Export",
        "family": "reporting",
        "description": "Approved data export and delivery.",
    },
    {
        "code": "reporting-scheduled-run",
        "name": "Reporting Scheduled Run",
        "family": "reporting",
        "description": "Scheduled report generation and distribution.",
    },
    {
        "code": "fee-waiver-approval",
        "name": "Fee Waiver Approval",
        "family": "finance",
        "description": "Fee waiver request and approval.",
    },
    {
        "code": "notification-digest",
        "name": "Notification Digest",
        "family": "communications",
        "description": "Digest and notification batching rules.",
    },
    {
        "code": "safety-drill-log",
        "name": "Safety Drill Log",
        "family": "compliance",
        "description": "Safety drill documentation and compliance.",
    },
    # === 2026-05-14 wave NS-4: domain coverage expansion ===
    # HR / Staff lifecycle
    {"code": "hr-staff-onboarding-v2", "name": "HR — Staff Onboarding (v2)", "family": "hr", "description": "End-to-end teacher / staff onboarding: contract, training, asset issue."},
    {"code": "hr-staff-offboarding", "name": "HR — Staff Offboarding", "family": "hr", "description": "Exit checklist, asset return, knowledge handover."},
    {"code": "hr-leave-request", "name": "HR — Leave Request", "family": "hr", "description": "Staff leave request with substitute coverage + payroll impact."},
    {"code": "hr-performance-review", "name": "HR — Performance Review", "family": "hr", "description": "Periodic appraisal cycle with goals + feedback rollup."},
    {"code": "hr-contract-renewal", "name": "HR — Contract Renewal", "family": "hr", "description": "Yearly contract renewal cadence with finance gate."},
    # Discipline / Behavior
    {"code": "discipline-incident-intake", "name": "Discipline — Incident Intake", "family": "discipline", "description": "Multi-role intake (teacher, dean, parent) with severity routing."},
    {"code": "discipline-appeal", "name": "Discipline — Appeal", "family": "discipline", "description": "Disciplinary appeal review with hearing scheduling."},
    {"code": "discipline-suspension-cycle", "name": "Discipline — Suspension Cycle", "family": "discipline", "description": "Suspension lifecycle: notice → counselor follow-up → return interview."},
    # Transport
    {"code": "transport-route-publish", "name": "Transport — Route Publish", "family": "transport", "description": "Publish bus routes with student-stop assignments + guardian notification."},
    {"code": "transport-incident-report", "name": "Transport — Incident Report", "family": "transport", "description": "Bus incident reporting with chain-of-custody."},
    {"code": "transport-driver-handover", "name": "Transport — Driver Handover", "family": "transport", "description": "End-of-shift handover with vehicle state + receipts."},
    # Library
    {"code": "library-loan-overdue", "name": "Library — Overdue Loan", "family": "library", "description": "Escalation cascade for overdue items: reminder → parent CC → admin lock."},
    {"code": "library-acquisition-request", "name": "Library — Acquisition Request", "family": "library", "description": "Teacher / department acquisition request with budget approval."},
    # Medical / Clinic
    {"code": "medical-immunization-renewal", "name": "Medical — Immunization Renewal", "family": "medical", "description": "Annual immunization-status verification with parent consent."},
    {"code": "medical-visit-followup", "name": "Medical — Visit Follow-Up", "family": "medical", "description": "Clinic visit follow-up workflow + guardian notification."},
    # Boarding
    {"code": "boarding-leave-permission", "name": "Boarding — Leave Permission", "family": "boarding", "description": "Boarder leave permission with parent acknowledgement."},
    {"code": "boarding-visitor-log", "name": "Boarding — Visitor Log", "family": "boarding", "description": "Visitor sign-in with photo capture + curfew gate."},
    # Cafeteria
    {"code": "cafeteria-meal-plan-renewal", "name": "Cafeteria — Plan Renewal", "family": "cafeteria", "description": "Term meal-plan renewal with allergen review."},
    {"code": "cafeteria-allergen-update", "name": "Cafeteria — Allergen Update", "family": "cafeteria", "description": "Guardian-initiated allergen update with kitchen notification."},
    # Communications
    {"code": "communications-emergency-broadcast", "name": "Comms — Emergency Broadcast", "family": "communications", "description": "Multi-channel emergency broadcast with delivery audit."},
    {"code": "communications-newsletter-monthly", "name": "Comms — Monthly Newsletter", "family": "communications", "description": "Monthly newsletter with section ownership + sign-off."},
    # Compliance
    {"code": "compliance-dsar-fulfilment", "name": "Compliance — DSAR Fulfilment", "family": "compliance", "description": "GDPR / FERPA DSAR (data subject access request) fulfilment workflow with redaction step."},
    {"code": "compliance-retention-purge", "name": "Compliance — Retention Purge", "family": "compliance", "description": "Periodic retention-policy purge with approval gate."},
    {"code": "compliance-evidence-collection", "name": "Compliance — Evidence Collection", "family": "compliance", "description": "SOC 2 / ISO evidence collection cadence with auditor handoff."},
    # Integration / Migration
    {"code": "integration-sis-sync-failure", "name": "Integration — SIS Sync Failure", "family": "integration", "description": "Sync failure triage + tenant notification + rollback option."},
    {"code": "migration-bundle-review", "name": "Migration — Bundle Review", "family": "migration", "description": "Migration Cloud bundle review with reconciliation sampling + sign-off."},
]

DASHBOARD_PACKS = [
    {
        "code": "school-admin-executive",
        "name": "School Admin Executive",
        "family": "admin",
        "description": "Executive summary and KPIs for school admins.",
    },
    {
        "code": "school-admin-operations",
        "name": "School Admin Operations",
        "family": "admin",
        "description": "Day-to-day operations and tasks.",
    },
    {
        "code": "admissions-operations",
        "name": "Admissions Operations",
        "family": "admissions",
        "description": "Pipeline and application queue for admissions team.",
    },
    {
        "code": "admissions-analytics",
        "name": "Admissions Analytics",
        "family": "admissions",
        "description": "Application metrics and funnel view.",
    },
    {
        "code": "teacher-command-center",
        "name": "Teacher Command Center",
        "family": "teacher",
        "description": "Classes, grading, and attendance for teachers.",
    },
    {
        "code": "teacher-gradebook-quick",
        "name": "Teacher Gradebook Quick",
        "family": "teacher",
        "description": "Quick grade entry and class roster.",
    },
    {
        "code": "teacher-planner",
        "name": "Teacher Planner",
        "family": "teacher",
        "description": "Lesson plans and calendar view.",
    },
    {
        "code": "parent-mobile-feed",
        "name": "Parent Mobile Feed",
        "family": "parent",
        "description": "Mobile-friendly parent dashboard.",
    },
    {
        "code": "parent-student-progress",
        "name": "Parent Student Progress",
        "family": "parent",
        "description": "Grades, attendance, and feedback.",
    },
    {
        "code": "parent-payments",
        "name": "Parent Payments",
        "family": "parent",
        "description": "Fees, payments, and payment history.",
    },
    {
        "code": "finance-office-ledger",
        "name": "Finance Office Ledger",
        "family": "finance",
        "description": "Invoices, payments, and outstanding fees.",
    },
    {
        "code": "finance-reconciliation",
        "name": "Finance Reconciliation",
        "family": "finance",
        "description": "Bank reconciliation and audit view.",
    },
    {
        "code": "finance-aid",
        "name": "Finance Aid Overview",
        "family": "finance",
        "description": "Financial aid and scholarship dashboard.",
    },
    {
        "code": "low-bandwidth-compact",
        "name": "Low-Bandwidth Compact",
        "family": "compact",
        "description": "Minimal widgets for low-bandwidth users.",
    },
    {
        "code": "counselor-caseload",
        "name": "Counselor Caseload",
        "family": "counselor",
        "description": "Student caseload and intervention tracking.",
    },
    {
        "code": "counselor-attendance-alerts",
        "name": "Counselor Attendance Alerts",
        "family": "counselor",
        "description": "At-risk and attendance alerts.",
    },
    {
        "code": "principal-school-summary",
        "name": "Principal School Summary",
        "family": "principal",
        "description": "School-wide metrics and alerts.",
    },
    {
        "code": "principal-discipline",
        "name": "Principal Discipline",
        "family": "principal",
        "description": "Discipline incidents and follow-ups.",
    },
    {
        "code": "registrar-enrollment",
        "name": "Registrar Enrollment",
        "family": "registrar",
        "description": "Enrollment and schedule management.",
    },
    {
        "code": "registrar-transcripts",
        "name": "Registrar Transcripts",
        "family": "registrar",
        "description": "Transcript requests and fulfillment.",
    },
    {
        "code": "nurse-health-log",
        "name": "Nurse Health Log",
        "family": "nurse",
        "description": "Health room visits and medication log.",
    },
    # === 2026-05-14 wave NS-4: per-role + per-domain dashboard coverage ===
    {"code": "principal-academic-pulse", "name": "Principal — Academic Pulse", "family": "principal", "description": "Grade-distribution heatmap + on-track / at-risk band per cohort."},
    {"code": "principal-parent-engagement", "name": "Principal — Parent Engagement", "family": "principal", "description": "Parent-portal adoption + outbound message reach."},
    {"code": "vice-principal-discipline-trends", "name": "Vice Principal — Discipline Trends", "family": "principal", "description": "Discipline incident heatmap by grade / classroom / category."},
    {"code": "bursar-collection-rate", "name": "Bursar — Collection Rate", "family": "finance", "description": "Real-time collection rate by term + cohort with aging buckets."},
    {"code": "bursar-aging-report", "name": "Bursar — Aging Report", "family": "finance", "description": "Outstanding-balance aging report drilling into 30/60/90+ buckets."},
    {"code": "it-admin-system-health", "name": "IT Admin — System Health", "family": "it_admin", "description": "Health probes, integration sync state, AI provider reachability."},
    {"code": "it-admin-audit-trail", "name": "IT Admin — Audit Trail", "family": "it_admin", "description": "Recent admin actions, login anomalies, RBAC change feed."},
    {"code": "hr-staff-pipeline", "name": "HR — Staff Pipeline", "family": "hr", "description": "Open positions, candidates, onboarding/offboarding in flight."},
    {"code": "transport-fleet-status", "name": "Transport — Fleet Status", "family": "transport", "description": "Bus location, route on-time %, driver shift state."},
    {"code": "library-circulation", "name": "Library — Circulation", "family": "library", "description": "Active loans, overdue items, top-circulated titles."},
    {"code": "nurse-clinic-pulse", "name": "Nurse — Clinic Pulse", "family": "nurse", "description": "Visits today, recurring complaints, immunization due."},
    {"code": "boarding-house-summary", "name": "Boarding — House Summary", "family": "boarding", "description": "Occupancy, visitor count, leave-permission requests pending."},
    {"code": "cafeteria-meal-uptake", "name": "Cafeteria — Meal Uptake", "family": "cafeteria", "description": "Plan subscribers, daily uptake %, allergen incidents."},
    {"code": "student-self-service", "name": "Student — Self Service", "family": "student", "description": "Today's classes, assignments due, attendance % to date."},
    {"code": "admissions-funnel-conversion", "name": "Admissions — Funnel Conversion", "family": "admissions", "description": "Inquiry → application → offer → enrol conversion with stage SLAs."},
    {"code": "alumni-engagement-summary", "name": "Alumni — Engagement Summary", "family": "alumni", "description": "Alumni roster activity + donation flow + event RSVP."},
    {"code": "compliance-evidence-room", "name": "Compliance — Evidence Room", "family": "compliance", "description": "SOC 2 / ISO evidence collection status by control."},
]


class Command(BaseCommand):
    help = "Seed initial Workflow Packs and Dashboard Packs (Phase 4). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        for row in WORKFLOW_PACKS:
            if not dry_run:
                WorkflowPack.objects.update_or_create(
                    code=row["code"],
                    defaults={
                        "name": row["name"],
                        "family": row.get("family", ""),
                        "description": row.get("description", ""),
                        "version": "1.0",
                        "is_active": True,
                    },
                )
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Workflow packs: {len(WORKFLOW_PACKS)} ensured.")
            )

        for row in DASHBOARD_PACKS:
            if not dry_run:
                DashboardPack.objects.update_or_create(
                    code=row["code"],
                    defaults={
                        "name": row["name"],
                        "family": row.get("family", ""),
                        "description": row.get("description", ""),
                        "version": "1.0",
                        "is_active": True,
                    },
                )
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run: would ensure {len(WORKFLOW_PACKS)} workflow packs and {len(DASHBOARD_PACKS)} dashboard packs."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Dashboard packs: {len(DASHBOARD_PACKS)} ensured.")
            )
