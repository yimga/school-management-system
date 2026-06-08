"""
Expanded UI field / feature explainer catalog for operator + tenant surfaces.

Keys use ``entity.field`` or ``surface.feature``. Merged into ``ui_field_help.UI_FIELD_HELP``
at import time. Target: 500+ entries for platform-wide shell-level auto-tag wiring.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


def _h(title: str, body: str) -> dict[str, str]:
    return {"title": _(title), "body": _(body)}


# Universal form fields (tenant + operator)
_COMMON: dict[str, dict[str, str]] = {
    "common.email": _h("Email address", "Used for login, receipts, and system notifications."),
    "common.password": _h("Password", "Minimum strength rules apply; never share credentials."),
    "common.phone": _h("Phone number", "Stored for SMS alerts when your school enables them."),
    "common.name": _h("Display name", "Shown on reports, portals, and audit trails."),
    "common.slug": _h("URL slug", "Short identifier used in tenant URLs and API paths."),
    "common.status": _h("Status", "Controls visibility, workflow stage, or activation."),
    "common.date": _h("Date", "Respects your school locale and academic calendar."),
    "common.notes": _h("Notes", "Internal remarks — not always visible to parents or students."),
    "common.reference": _h("Reference", "Searchable identifier for exports and reconciliation."),
    "common.amount": _h("Amount", "Monetary value in the school currency unless noted."),
}

# Operator / control-plane
_OPERATOR: dict[str, dict[str, str]] = {
    "operator.smtp_host": _h("SMTP host", "Outbound mail server hostname for platform email."),
    "operator.smtp_port": _h("SMTP port", "Typically 587 (TLS) or 465 (SSL)."),
    "operator.smtp_username": _h("SMTP username", "Authenticated sender account for relay."),
    "operator.smtp_password": _h("SMTP password", "Stored encrypted; rotate after staff changes."),
    "operator.from_email": _h("From address", "Default sender shown to recipients."),
    "operator.signup_verification": _h("Signup verification", "Review and approve new school signups."),
    "operator.provisioning": _h("Provisioning", "Creates tenant schema, defaults, and admin access."),
    "operator.billing_plan": _h("Billing plan", "Subscription tier and feature entitlements."),
    "operator.tenant_slug": _h("Tenant slug", "Subdomain segment — immutable after go-live."),
    "operator.impersonation": _h("Open as school", "Staff session into a tenant for support."),
    "operator.migration_bundle": _h("Migration bundle", "Packaged SIS extract awaiting reconcile."),
    "operator.webhook_secret": _h("Webhook secret", "HMAC key subscribers use to verify payloads."),
    "operator.api_token": _h("API token", "Scoped credential — store like a password."),
    "operator.companion_upload": _h("Companion upload", "Sealed import from the browser extension."),
    "operator.maa_signature": _h("MAA signature", "Migration authorization agreement capture."),
    "operator.health_dashboard": _h("Migration health", "Delivery, signing, and keypair status."),
    "operator.audit_export": _h("Audit export", "Tamper-evident JSONL for compliance review."),
    "operator.key_rotation": _h("Key rotation", "Rotate encryption keys on a defined schedule."),
    "operator.region": _h("Region", "Data residency and locale defaults for the tenant."),
    "operator.sector": _h("School sector", "Primary sector drives terminology and templates."),
    "operator.demo_mode": _h("Demo sandbox", "Flagged tenants may reset data periodically."),
    "operator.feature_flag": _h("Feature flag", "Gradual rollout without redeploy."),
    "operator.cockpit_section": _h("Cockpit section", "Operator-tunable landing content block."),
    "operator.super_dashboard": _h("Manager dashboard", "Cross-tenant KPIs and quick actions."),
    "operator.school_create": _h("Create school", "Provision a new tenant from the control plane."),
    "operator.school_purge": _h("School purge", "Irreversible tenant removal — counsel required."),
    "operator.meal_plan_analytics": _h("Meal plan analytics", "Low-balance trends and notification stats."),
    "operator.signup_retry": _h("Retry provisioning", "Re-runs failed schema or default setup."),
    "operator.email_configure": _h("Email configure", "Platform relay and tenant notification defaults."),
    "operator.privacy_policy": _h("Privacy policy", "Public legal copy on the manager host."),
    "operator.district_interop": _h("District interop", "LMS and roster connectors across schools."),
    "operator.marketplace_review": _h("Marketplace review", "Moderate publisher apps before listing."),
    "operator.incident_banner": _h("Incident banner", "Platform-wide status shown in the Tools tray."),
}

# Tenant administration
_TENANT: dict[str, dict[str, str]] = {
    "student.admission_number": _h("Admission number", "Unique student identifier on reports."),
    "student.class_level": _h("Class level", "Current grade or form assignment."),
    "student.guardian_link": _h("Guardian link", "Parent portal access and fee payer."),
    "student.enrollment_status": _h("Enrollment status", "Active, withdrawn, or alumni."),
    "teacher.staff_id": _h("Staff ID", "HR identifier for payroll integrations."),
    "teacher.subject_assignment": _h("Subject assignment", "Classes this teacher may grade."),
    "parent.portal_access": _h("Portal access", "Login eligibility for the parent app."),
    "attendance.present": _h("Present", "Counted toward statutory attendance."),
    "attendance.absent": _h("Absent", "May trigger guardian notification rules."),
    "attendance.late": _h("Late", "Arrival after the configured cutoff."),
    "attendance.excused": _h("Excused absence", "Documented reason — exempt from penalties."),
    "attendance.holiday": _h("Holiday", "Institution-wide non-instructional day."),
    "grades.score": _h("Score", "Raw mark before weighting or approval."),
    "grades.approval": _h("Grade approval", "Leadership sign-off before publish."),
    "grades.weight": _h("Weight", "Contribution to term or exam aggregate."),
    "finance.invoice_due": _h("Due date", "Payment deadline for guardians."),
    "finance.payment_method": _h("Payment method", "Cash, transfer, card, or mobile money."),
    "finance.fee_structure": _h("Fee structure", "Line items billed per term or event."),
    "academics.term": _h("Term", "Reporting period within the academic year."),
    "academics.session": _h("Session", "Calendar year or cohort cycle."),
    "academics.classroom": _h("Classroom", "Physical or virtual room assignment."),
    "people.applicant_stage": _h("Applicant stage", "Pipeline from enquiry to enrollment."),
    "notification.channel": _h("Channel", "Email, SMS, push, or in-app."),
    "configuration.brand_color": _h("Brand color", "Primary accent on portals and PDFs."),
    "configuration.timezone": _h("Timezone", "Schedules and timestamps for this school."),
    "configuration.locale": _h("Locale", "Language, date format, and currency display."),
    "configuration.academic_year": _h("Academic year", "Active year for enrollments and reports."),
    "portal.dashboard_widget": _h("Dashboard widget", "Role-specific KPI on the landing page."),
    "portal.theme": _h("Portal theme", "Light/dark and tenant brand cascade."),
    "interop.lms_token": _h("LMS token", "OAuth or API token for course sync."),
    "interop.webhook_url": _h("Webhook URL", "Endpoint that receives platform events."),
    "roster.csv_upload": _h("CSV upload", "Bulk import — validate before commit."),
    "roster.field_mapping": _h("Field mapping", "Match CSV columns to canonical fields."),
    "timetable.period": _h("Period", "Slot in the daily bell schedule."),
    "timetable.room": _h("Room", "Location for this period."),
    "exam.schedule": _h("Exam schedule", "Published dates visible to students."),
    "report_card.term": _h("Report term", "Marks included on this report card."),
    "discipline.incident": _h("Incident", "Logged behavior event with severity."),
    "transport.route": _h("Transport route", "Bus or van assignment."),
    "hostel.room": _h("Hostel room", "Boarding placement."),
    "cafeteria.meal_plan": _h("Meal plan", "Prepaid balance and daily limits."),
    "library.checkout": _h("Library checkout", "Due date and fine rules."),
    "health.clinic_visit": _h("Clinic visit", "Nurse log — restricted to authorized staff."),
}

# Finance / marketplace (extends existing invoice.* keys)
_FINANCE: dict[str, dict[str, str]] = {
    "invoice.due_date": _h("Due date", "Overdue status starts the day after."),
    "invoice.line_item": _h("Line item", "Individual charge on the invoice."),
    "payment.gateway": _h("Payment gateway", "Processor handling card or mobile money."),
    "payment.receipt": _h("Receipt", "Proof of payment for guardians."),
    "billing.subscription": _h("Subscription", "Recurring platform or module fee."),
    "billing.usage_meter": _h("Usage meter", "Billable units consumed this period."),
    "marketplace.adapter_credentials": _h("Adapter credentials", "Secrets for third-party integrations."),
    "marketplace.publisher_rating": _h("Publisher rating", "Community score for marketplace apps."),
    "finance.access": _h("Finance access", "Role-gated — request broader access if hidden."),
}

# Migration cloud
_MIGRATION: dict[str, dict[str, str]] = {
    "migration.canonical_domain": _h("Canonical domain", "Standard data model slice for import."),
    "migration.bundle_status": _h("Bundle status", "Draft, reconciling, or published."),
    "migration.vendor_powerschool": _h("PowerSchool", "Vendor-specific CSV pre-processor."),
    "migration.vendor_blackbaud": _h("Blackbaud", "Vendor-specific CSV pre-processor."),
    "migration.receipt_id": _h("Receipt ID", "Idempotent upload reference from Companion."),
    "migration.legacy_hash": _h("Legacy hash", "Imported password verifier for first login."),
    "migration.webhook_delivery": _h("Webhook delivery", "Outbound event with retry policy."),
    "migration.token_scope": _h("Token scope", "Least-privilege API access for automation."),
}

# Surface features (page-level, not tied to one input)
_SURFACE: dict[str, dict[str, str]] = {
    "surface.studio_mode": _h("Studio mode", "Experience, Automation, Outputs, Launch, Control."),
    "surface.backend_intent": _h("Dashboard intent", "Operational KPIs vs setup checklist."),
    "surface.notification_severity": _h("Severity", "Alert, warning, or informational."),
    "surface.gradebook_approval": _h("Grade approval", "Marks may require leadership sign-off."),
    "surface.zero_click_hub": _h("Zero-click hub", "Keyboard-first actions from the command strip."),
    "surface.tools_tray": _h("Tools tray", "Incident, workflow, and guidance context."),
    "surface.workflow_tags": _h("Workflow tags", "Taxonomy chips describing this page's job."),
    "surface.page_explain": _h("Page help", "What this screen does and what to do next."),
}

UI_FIELD_HELP_CATALOG: dict[str, dict[str, str]] = {
    **_COMMON,
    **_OPERATOR,
    **_TENANT,
    **_FINANCE,
    **_MIGRATION,
    **_SURFACE,
}
