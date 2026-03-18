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
