"""
Seed CapabilityRegistry with standard capability codes from the manifest schema.
Run: python manage.py seed_capability_registry
Idempotent: creates only missing codes; use --reset to clear and re-seed (optional).
"""

from django.core.management.base import BaseCommand

from apps.marketplace.models import CapabilityRegistry


# Standard codes per category (code, name, description)
# 2026-05-14 wave NS-4 expansion: from 4 placeholder entries to a full
# capability vocabulary so marketplace manifests can declare what they
# extend. Codes follow `<category>.<verb>` convention.
DEFAULT_CAPABILITIES = [
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard_widget", "Dashboard widget", "Widget shown on school dashboard"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow_action", "Workflow action", "Action available in workflow automation"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow_condition", "Workflow condition", "Condition in workflow automation"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration_adapter", "Integration adapter", "External integration adapter"),
    # === Dashboard-widget capabilities (per-domain) ===
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.attendance_today", "Today's attendance widget", "Single-day attendance roll-up for the current school"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.grade_distribution", "Grade distribution widget", "Distribution chart of term grades for a cohort"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.fee_collection", "Fee collection KPI", "Real-time invoiced vs collected % over a configurable window"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.at_risk_students", "At-risk students list", "List of students flagged by the at-risk model"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.upcoming_events", "Upcoming events", "Next 7 days of calendar events for the active user"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.recent_announcements", "Recent announcements", "Last N announcements visible to this user role"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.bus_eta", "Bus ETA widget", "Live ETA for the parent's child's bus"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.payment_due", "Payment due chip", "Outstanding-balance call-to-action"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.ai_copilot_quick_actions", "AI copilot quick actions", "Two-tap AI copilot shortcut tray"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.lesson_feed", "Lesson feed", "Per-class lesson stream for parents / students"),
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard.widget.compliance_status", "Compliance status", "Tenant-level compliance posture summary"),
    # === Workflow-action capabilities ===
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.send_email", "Send email", "Email send with template + per-recipient context"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.send_sms", "Send SMS", "SMS send via configured gateway"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.send_whatsapp", "Send WhatsApp", "WhatsApp Business template send"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.create_invoice", "Create invoice", "Issue a Finance invoice"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.record_payment", "Record payment", "Record a payment against an invoice"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.assign_dashboard_pack", "Assign dashboard pack", "Bind a DashboardPack to a tenant role"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.create_task", "Create task", "Open a task for a staff member"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.approve_request", "Approve request", "Mark an approval-queue item Approved"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.reject_request", "Reject request", "Mark an approval-queue item Rejected"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.publish_grades", "Publish grades", "Publish a term's grades after approval"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.notify_role", "Notify role", "Push a notification to every user with a given role"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.export_report", "Export report", "Trigger a report template export"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow.action.invoke_ai_task", "Invoke AI task", "Call services.ai_gateway.invoke for a named task"),
    # === Workflow-condition capabilities ===
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.grade_below", "Grade below threshold", "Student term grade is below configured threshold"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.attendance_below", "Attendance below threshold", "Student attendance % falls below threshold"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.invoice_overdue", "Invoice overdue", "Invoice past its due date"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.consent_pending", "Consent pending", "Student has a pending guardian-consent record"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.user_in_role", "User in role", "Acting user's role matches one of the listed roles"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.time_window", "Time window", "Current time falls within a configured window"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow.condition.school_setting_equals", "Setting equals", "A tenant setting equals a configured value"),
    # === Integration-adapter capabilities ===
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.stripe_connect", "Stripe Connect adapter", "Stripe Connect payments + revenue-share"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.flutterwave", "Flutterwave / MoMo adapter", "Mobile money + bank gateway for West/East Africa"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.paystack", "Paystack adapter", "Paystack gateway for African markets"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.razorpay", "Razorpay adapter", "Razorpay gateway for Indian markets"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.twilio_sms", "Twilio SMS adapter", "Twilio SMS / WhatsApp programmable messaging"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.africastalking_sms", "Africa's Talking adapter", "Africa's Talking SMS / Airtime / Voice"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.sendgrid_email", "SendGrid email adapter", "Transactional + broadcast email"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.ses_email", "AWS SES adapter", "AWS Simple Email Service"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.postmark_email", "Postmark email adapter", "Postmark transactional email"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.canvas_lti", "Canvas LTI adapter", "Canvas LMS via LTI 1.3"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.google_classroom", "Google Classroom adapter", "Google Workspace for Education"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.ms_teams_education", "MS Teams for Ed adapter", "Microsoft Teams for Education Graph API"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.oneroster_v1p2", "OneRoster 1.2 adapter", "OneRoster v1.2 REST + CSV"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.clever_rostering", "Clever rostering adapter", "Clever SIS + SSO"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.classlink_rostering", "ClassLink rostering adapter", "ClassLink SIS + SSO"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.powerschool_sis", "PowerSchool SIS adapter", "PowerSchool bidirectional SIS sync"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.ollama_local", "Ollama (local AI) adapter", "Local-first Ollama inference"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.ai_gateway_premium", "AI gateway premium adapter", "Premium-tier inference through the governed AI gateway"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.vllm", "vLLM adapter", "vLLM self-hosted high-throughput inference"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration.adapter.s3_object_storage", "S3 / object storage adapter", "S3-compatible object storage"),
]


class Command(BaseCommand):
    help = "Seed CapabilityRegistry with standard capability codes (dashboard_widget, workflow_action, etc.)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all registry entries and re-seed (default: only add missing).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    def handle(self, *args, **options):
        reset = options["reset"]
        dry_run = options["dry_run"]
        if reset and not dry_run:
            deleted, _ = CapabilityRegistry.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted} capability registry entries.")
            )
        created = 0
        for category, code, name, description in DEFAULT_CAPABILITIES:
            if dry_run:
                if reset or not CapabilityRegistry.objects.filter(code=code).exists():
                    self.stdout.write(f"Would create: {code} ({category})")
                    created += 1
                continue
            _, was_created = CapabilityRegistry.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "description": description,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {code}"))
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"Dry run: would create {created} entries.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Created {created} capability registry entries."
                )
            )
