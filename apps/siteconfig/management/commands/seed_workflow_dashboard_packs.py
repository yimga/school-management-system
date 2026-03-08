"""
Phase 4: Seed initial Workflow Packs and Dashboard Packs (platform-level).
Idempotent: update_or_create by code.
"""
from django.core.management.base import BaseCommand

from apps.siteconfig.models_workflow import WorkflowPack
from apps.siteconfig.models_dashboard import DashboardPack


WORKFLOW_PACKS = [
    {"code": "admissions-standard", "name": "Admissions Standard", "family": "admissions", "description": "Standard application and review flow."},
    {"code": "admissions-interview-offer", "name": "Admissions Interview + Offer", "family": "admissions", "description": "Interview stage and formal offer workflow."},
    {"code": "finance-basic", "name": "Finance Basic", "family": "finance", "description": "Single-approval fee and invoice workflow."},
    {"code": "finance-dual-approval", "name": "Finance Dual Approval", "family": "finance", "description": "Dual approval for fees and refunds."},
    {"code": "grade-publish-controlled", "name": "Grade Publish Controlled Review", "family": "gradebook", "description": "Controlled grade publication with review step."},
    {"code": "attendance-escalation", "name": "Attendance Escalation", "family": "attendance", "description": "Absence escalation and counselor notification."},
    {"code": "compliance-evidence-review", "name": "Compliance Evidence Review", "family": "compliance", "description": "Document and evidence review workflow."},
]

DASHBOARD_PACKS = [
    {"code": "school-admin-executive", "name": "School Admin Executive", "family": "admin", "description": "Executive summary and KPIs for school admins."},
    {"code": "admissions-operations", "name": "Admissions Operations", "family": "admissions", "description": "Pipeline and application queue for admissions team."},
    {"code": "teacher-command-center", "name": "Teacher Command Center", "family": "teacher", "description": "Classes, grading, and attendance for teachers."},
    {"code": "parent-mobile-feed", "name": "Parent Mobile Feed", "family": "parent", "description": "Mobile-friendly parent dashboard."},
    {"code": "finance-office-ledger", "name": "Finance Office Ledger", "family": "finance", "description": "Invoices, payments, and outstanding fees."},
    {"code": "low-bandwidth-compact", "name": "Low-Bandwidth Compact", "family": "compact", "description": "Minimal widgets for low-bandwidth users."},
]


class Command(BaseCommand):
    help = "Seed initial Workflow Packs and Dashboard Packs (Phase 4). Idempotent."

    def handle(self, *args, **options):
        for row in WORKFLOW_PACKS:
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
        self.stdout.write(self.style.SUCCESS(f"Workflow packs: {len(WORKFLOW_PACKS)} ensured."))

        for row in DASHBOARD_PACKS:
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
        self.stdout.write(self.style.SUCCESS(f"Dashboard packs: {len(DASHBOARD_PACKS)} ensured."))
