"""
§7 MARKETPLACE_SEED_TARGETS: seed PackageVersion so first-party apps (distinct package_id) reach 25+.
Idempotent: update_or_create by (package_id, version).
Run: python manage.py seed_first_party_apps
"""
from django.core.management.base import BaseCommand

from apps.packages.models import PackageVersion


# Minimum 25 distinct package_id for platform_inventory first_party_apps count.
FIRST_PARTY_APPS = [
    {"package_id": "admissions-core", "version": "1.0", "changelog_summary": "Admissions application and review."},
    {"package_id": "admissions-document-verify", "version": "1.0", "changelog_summary": "Document verification workflow."},
    {"package_id": "finance-invoicing", "version": "1.0", "changelog_summary": "Fee and invoice management."},
    {"package_id": "finance-refunds", "version": "1.0", "changelog_summary": "Refund approval workflow."},
    {"package_id": "gradebook-standard", "version": "1.0", "changelog_summary": "Grade entry and publish."},
    {"package_id": "gradebook-appeals", "version": "1.0", "changelog_summary": "Grade appeal workflow."},
    {"package_id": "attendance-basic", "version": "1.0", "changelog_summary": "Daily attendance and escalation."},
    {"package_id": "attendance-truancy", "version": "1.0", "changelog_summary": "Truancy alerts and reporting."},
    {"package_id": "compliance-evidence", "version": "1.0", "changelog_summary": "Compliance evidence and audit."},
    {"package_id": "hr-onboarding", "version": "1.0", "changelog_summary": "Staff onboarding checklist."},
    {"package_id": "hr-leave", "version": "1.0", "changelog_summary": "Leave request and approval."},
    {"package_id": "communications-broadcast", "version": "1.0", "changelog_summary": "Announcements and broadcast."},
    {"package_id": "enrollment-reenroll", "version": "1.0", "changelog_summary": "Re-enrollment workflow."},
    {"package_id": "enrollment-withdrawal", "version": "1.0", "changelog_summary": "Withdrawal and exit checklist."},
    {"package_id": "discipline-incident", "version": "1.0", "changelog_summary": "Incident report and follow-up."},
    {"package_id": "reporting-export", "version": "1.0", "changelog_summary": "Data export and delivery."},
    {"package_id": "scheduler-bell", "version": "1.0", "changelog_summary": "Bell schedule and periods."},
    {"package_id": "scheduler-rooms", "version": "1.0", "changelog_summary": "Room and resource scheduling."},
    {"package_id": "parent-portal-basic", "version": "1.0", "changelog_summary": "Parent portal and progress."},
    {"package_id": "parent-payments", "version": "1.0", "changelog_summary": "Parent fee and payment view."},
    {"package_id": "teacher-gradebook", "version": "1.0", "changelog_summary": "Teacher gradebook and roster."},
    {"package_id": "teacher-attendance", "version": "1.0", "changelog_summary": "Teacher attendance entry."},
    {"package_id": "registrar-enrollment", "version": "1.0", "changelog_summary": "Registrar enrollment and sections."},
    {"package_id": "counselor-caseload", "version": "1.0", "changelog_summary": "Counselor caseload and notes."},
    {"package_id": "nurse-health-log", "version": "1.0", "changelog_summary": "Health log and medication."},
    {"package_id": "admin-dashboard-exec", "version": "1.0", "changelog_summary": "Executive dashboard and KPIs."},
    {"package_id": "api-public-readonly", "version": "1.0", "changelog_summary": "Public read-only API pack."},
]


class Command(BaseCommand):
    help = "Seed PackageVersion so first-party apps (distinct package_id) reach 25+ for MARKETPLACE_SEED_TARGETS §7."

    def handle(self, *args, **options):
        ensured = 0
        for item in FIRST_PARTY_APPS:
            PackageVersion.objects.update_or_create(
                package_id=item["package_id"],
                version=item["version"],
                defaults={
                    "changelog_summary": item.get("changelog_summary", ""),
                },
            )
            ensured += 1
        self.stdout.write(self.style.SUCCESS(f"First-party app versions: {ensured} ensured (distinct package_id: {len(FIRST_PARTY_APPS)})."))
        self.stdout.write("Run: python manage.py platform_inventory --format json to verify first_party_apps count.")
