"""
Phase 4: Seed initial Workflow Packs and Dashboard Packs (platform-level).
Idempotent: update_or_create by code.
"""

from django.core.management.base import BaseCommand

from apps.siteconfig.models_workflow import WorkflowPack
from apps.siteconfig.models_dashboard import DashboardPack, DashboardTemplate
from apps.siteconfig.dashboard_pack_catalog import DASHBOARD_PACKS, apply_seed


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

        templates_ensured = 0
        if not dry_run:
            templates_ensured = apply_seed(DashboardPack, DashboardTemplate)
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run: would ensure {len(WORKFLOW_PACKS)} workflow packs, "
                    f"{len(DASHBOARD_PACKS)} dashboard packs, and one template per pack."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dashboard packs: {len(DASHBOARD_PACKS)} ensured "
                    f"({templates_ensured} new templates)."
                )
            )
