"""
50X route-level page explainers — high-friction operator + tenant URLs.

Pairs with workflow-registry routes and Zero-Friction zone ledger priorities.
Target: >= 50 named route keys in the merged route index (with workflows).
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


def _r(
    title: str,
    body: str,
    *,
    surface: str = "tenant",
    fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "title": _(title),
        "body": _(body),
        "surface": surface,
        "fields": fields,
    }


ROUTE_HELP_SOVEREIGN_50X: dict[str, dict[str, Any]] = {
    # Operator / super (12)
    "super:dashboard": _r(
        "Manager dashboard",
        "Cross-tenant KPIs, provisioning shortcuts, and operator health signals.",
        surface="operator",
    ),
    "super:schools_list": _r(
        "Schools directory",
        "Search tenants, open 360 views, and launch impersonation for support.",
        surface="operator",
    ),
    "super:command_center": _r(
        "Command center",
        "Incident, workflow, and platform pulse in one operator console.",
        surface="operator",
    ),
    "super:create_school_wizard": _r(
        "Create school wizard",
        "Provision a tenant with education profile, subdomain, and defaults.",
        surface="operator",
    ),
    "super:signup_verifications": _r(
        "Signup verifications",
        "Approve signups and retry provisioning when onboarding stalls.",
        surface="operator",
    ),
    "super:offboarding_queue": _r(
        "Offboarding queue",
        "Preview and execute irreversible tenant purge with audit receipt.",
        surface="operator",
    ),
    "super:api_create_school": _r(
        "Create school API",
        "Programmatic tenant creation — same provisioning contract as the wizard.",
        surface="operator",
    ),
    "super:native_roster_connectors": _r(
        "Native roster connectors",
        "District-level LMS and roster integrations across authorized schools.",
        surface="operator",
    ),
    "super:mat_group_hub_dashboard": _r(
        "MAT group hub",
        "Multi-academy trust rollup when group operating mode is enabled.",
        surface="operator",
    ),
    "super:customer_success_dashboard": _r(
        "Customer success",
        "Onboarding milestones and tenant health for operator CS workflows.",
        surface="operator",
    ),
    "super:signup_diagnostics": _r(
        "Signup diagnostics",
        "Trace signup funnel failures without exposing PII in logs.",
        surface="operator",
    ),
    "schoolops:email_configure": _r(
        "Email configuration",
        "Platform SMTP relay and encrypted secrets for tenant notifications.",
        surface="operator",
        fields=("smtp_host", "smtp_port", "smtp_username", "smtp_password", "from_email"),
    ),
    # Migration cloud (4)
    "migration_cloud:connector_home": _r(
        "Migration connector",
        "Authorize SIS read access and stage canonical import bundles.",
        surface="tenant",
    ),
    "migration_cloud:maa_sign": _r(
        "Sign migration agreement",
        "Capture Migration Authorization Agreement before data ingest.",
        surface="tenant",
    ),
    "migration_cloud:wizard": _r(
        "Migration wizard",
        "Map, validate, and apply artifact waves into the tenant schema.",
        surface="tenant",
    ),
    "migration_cloud:operator_health": _r(
        "Migration health",
        "Cross-tenant delivery, signing, and keypair status for operators.",
        surface="operator",
    ),
    # Studio OS (5)
    "studio_os:mode_experience": _r(
        "Studio — Experience",
        "Configure tenant-facing portal theme and published content.",
        surface="tenant",
    ),
    "studio_os:mode_automation": _r(
        "Studio — Automation",
        "Author tenant-scoped triggers and rule packs.",
        surface="tenant",
    ),
    "studio_os:mode_output": _r(
        "Studio — Outputs",
        "Report cards, PDF, and email output surfaces.",
        surface="tenant",
    ),
    "studio_os:mode_launch": _r(
        "Studio — Launch",
        "Go-live checklist with approval gates before tenant activation.",
        surface="tenant",
    ),
    "studio_os:mode_control": _r(
        "Studio — Control",
        "Operator control panel for tenant Studio OS surfaces.",
        surface="tenant",
    ),
    # Academics + evals / teacher (10)
    "academics:daily_attendance": _r(
        "Daily attendance",
        "Mark present, late, or absent — QR-first when enabled.",
        surface="tenant",
        fields=("status", "date"),
    ),
    "academics:marks_entry": _r(
        "Marks entry",
        "Enter assessment scores; may require leadership approval before publish.",
        surface="tenant",
        fields=("score", "weight"),
    ),
    "evals:teacher_dashboard": _r(
        "Teacher dashboard",
        "Workflow center for marks, approvals, and class rankings.",
        surface="tenant",
    ),
    "evals:teacher_marks_entry": _r(
        "Teacher marks entry",
        "Grid entry for class assessments with offline WAL when configured.",
        surface="tenant",
        fields=("score",),
    ),
    "evals:teacher_marks_list": _r(
        "Marks list",
        "Review submitted marks and open row detail for one student.",
        surface="tenant",
    ),
    "evals:bulk_grade_entry": _r(
        "Bulk grade entry",
        "Paste or import many scores — validate before commit.",
        surface="tenant",
    ),
    "evals:grade_approval_list": _r(
        "Grade approvals",
        "Leadership queue for marks awaiting sign-off.",
        surface="tenant",
    ),
    "evals:evaluation_admin": _r(
        "Evaluation admin",
        "Configure rubrics, terms, and evaluation cycles.",
        surface="tenant",
    ),
    "evals:class_ranking": _r(
        "Class ranking",
        "Rankings respect school policy and approval state.",
        surface="tenant",
    ),
    "evals:school_ranking": _r(
        "School ranking",
        "Aggregate rankings across classes for leadership review.",
        surface="tenant",
    ),
    # People / accounts backend (6)
    "accounts:backend_student_list": _r(
        "Students",
        "Search roster; open row drawer for 360 detail without extra navigation.",
        surface="tenant",
        fields=("admission_number", "class_level", "status"),
    ),
    "accounts:backend_student_create": _r(
        "Create student",
        "Enroll a student with guardian links and class assignment.",
        surface="tenant",
    ),
    "accounts:backend_student_detail": _r(
        "Student detail",
        "One-record view with tags, finance, and attendance shortcuts.",
        surface="tenant",
    ),
    "accounts:backend_applicant_list": _r(
        "Applicants",
        "Admissions pipeline from enquiry through enrollment.",
        surface="tenant",
        fields=("stage", "status"),
    ),
    "accounts:district_interop_hub": _r(
        "District interoperability",
        "Connect LMS and roster systems across district schools.",
        surface="operator",
        fields=("lms_url", "client_id", "client_secret", "api_token"),
    ),
    "accounts:backend_dashboard": _r(
        "Backend dashboard",
        "Operational KPIs vs setup checklist for school administrators.",
        surface="tenant",
    ),
    # Finance (5)
    "finance:invoices": _r(
        "Invoices",
        "Search and export fee invoices; status drives parent reminders.",
        surface="tenant",
        fields=("reference", "status", "due_date"),
    ),
    "finance:payments": _r(
        "Payments",
        "Recorded receipts and gateway settlements.",
        surface="tenant",
        fields=("amount", "payment_method", "reference"),
    ),
    "finance:billing_setup": _r(
        "Billing setup",
        "Configure payment provider and fee structures before go-live.",
        surface="tenant",
    ),
    "finance:invoice_pay": _r(
        "Pay invoice",
        "Parent checkout for an outstanding invoice.",
        surface="tenant",
    ),
    "finance:marketplace_integration_credentials": _r(
        "Integration credentials",
        "Adapter secrets for marketplace apps — rotate after staff changes.",
        surface="tenant",
        fields=("api_key", "client_secret", "webhook_secret", "token"),
    ),
    # Portal / parent (6)
    "portal:backend_dashboard": _r(
        "Portal dashboard",
        "Role-specific landing widgets and zero-click command strip.",
        surface="tenant",
    ),
    "portal:link_child": _r(
        "Link a child",
        "Verify guardianship to access a child's portal data.",
        surface="tenant",
    ),
    "portal:parent_finance_pay_all": _r(
        "Pay all balances",
        "Single checkout for every open family invoice.",
        surface="tenant",
    ),
    "portal:parent_contact_school": _r(
        "Contact school",
        "Submit a support request to the school office.",
        surface="tenant",
    ),
    "portal:support_help_hub": _r(
        "Help hub",
        "Search knowledge base or open a support ticket.",
        surface="tenant",
    ),
    "evals:compliance_dashboard": _r(
        "Evaluations compliance",
        "Deadline and policy compliance for published marks.",
        surface="tenant",
    ),
    # Marketplace + platform (4)
    "marketplace:browse": _r(
        "Marketplace",
        "Browse and install apps with permission review.",
        surface="tenant",
    ),
    "platform_runtime:tenant_lifecycle": _r(
        "Tenant lifecycle",
        "Provision, suspend, or retire tenants from the control plane.",
        surface="operator",
    ),
    "apicenter:api_keys": _r(
        "API keys",
        "Mint scoped tokens for integrations — store like passwords.",
        surface="tenant",
        fields=("api_key", "scope"),
    ),
    "analytics:dashboard": _r(
        "Analytics dashboard",
        "KPI widgets with governed filters — export when entitled.",
        surface="tenant",
    ),
    # Compliance + payroll + reports (3)
    "compliance:dashboard": _r(
        "Compliance dashboard",
        "Data-quality scores and remediation actions.",
        surface="tenant",
    ),
    "payroll:create_run": _r(
        "Payroll run",
        "Create a pay period run with leave and deduction rules.",
        surface="tenant",
    ),
    "reports:publish_term_results": _r(
        "Publish term reports",
        "Publish report cards after grade approval gates pass.",
        surface="tenant",
    ),
}
