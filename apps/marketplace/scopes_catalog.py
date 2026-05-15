"""
Pass 14: code-backed OAuth2-style scope vocabulary for the marketplace.

Source of truth for what a third-party app can request when it asks a tenant
admin for permission. Mirrors the pattern of `apps/events/catalog.py` —
declarative, exhaustive, easy to diff.

Conventions:
  - Names follow `<resource>:<access>` (read | write | admin).
  - `read` reads tenant-scoped objects; `write` mutates them; `admin` covers
    destructive operations + cross-record bulk changes.
  - `sensitivity` mirrors AuditLog.Sensitivity for downstream audit tagging.
  - `description` is what the install dialog shows the admin in plain English;
    it must be approval-ready (FERPA / GDPR data-rights language).

The `AppPermissionScope` model in models.py is the persistent mirror of this
catalog; the `seed_marketplace_scopes` management command (pass 14.B) will
upsert one row per entry here.
"""

from __future__ import annotations


MARKETPLACE_SCOPES: dict[str, dict] = {
    "students:read": {
        "domain": "students",
        "access": "read",
        "sensitivity": "HIGH",
        "description": (
            "Read student profile data (name, admission number, classroom, status). "
            "Excludes guardian contact and PII flagged sensitive."
        ),
    },
    "students:write": {
        "domain": "students",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Create or update student profiles, including admission and status changes.",
    },
    "guardians:read": {
        "domain": "guardians",
        "access": "read",
        "sensitivity": "HIGH",
        "description": "Read guardian profiles linked to students this app can already access.",
    },
    "guardians:write": {
        "domain": "guardians",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Update guardian profile and contact preferences.",
    },
    "attendance:read": {
        "domain": "attendance",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read student and teacher attendance records for the connected school.",
    },
    "attendance:write": {
        "domain": "attendance",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Submit or amend attendance records.",
    },
    "grades:read": {
        "domain": "grades",
        "access": "read",
        "sensitivity": "HIGH",
        "description": (
            "Read evaluation scores, term averages, and published grades — but only "
            "for cohorts the installing administrator can see."
        ),
    },
    "grades:write": {
        "domain": "grades",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Submit, update, or publish evaluations and term grades.",
    },
    "finance:read": {
        "domain": "finance",
        "access": "read",
        "sensitivity": "HIGH",
        "description": "Read invoices, payments, and outstanding balances for this school.",
    },
    "finance:write": {
        "domain": "finance",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Create invoices, record payments, and reconcile balances.",
    },
    "webhooks:subscribe": {
        "domain": "platform",
        "access": "read",
        "sensitivity": "LOW",
        "description": "Receive webhook notifications for the event topics the app declares.",
    },
    "files:read": {
        "domain": "files",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read documents the school has shared with the app.",
    },
    "files:write": {
        "domain": "files",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Upload documents into the school's files area on behalf of installed users.",
    },
    "users:read": {
        "domain": "users",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read names + role labels of staff and admins; no passwords or contact PII.",
    },
    "tenant:admin": {
        "domain": "platform",
        "access": "admin",
        "sensitivity": "CRITICAL",
        "description": (
            "Full administrative access on this tenant — install/uninstall other apps, "
            "change tenant configuration, and trigger destructive operations. Reserved for "
            "trusted first-party tools."
        ),
    },
    # === 2026-05-14 wave NS-4: fine-grained scopes for new app categories ===
    "messaging:read": {
        "domain": "messaging",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read outbound message history, delivery receipts, and subscriber lists.",
    },
    "messaging:write": {
        "domain": "messaging",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Send SMS, WhatsApp, or email broadcasts on behalf of the school. Subject to per-channel rate limits and opt-in audit.",
    },
    "payments:read": {
        "domain": "payments",
        "access": "read",
        "sensitivity": "HIGH",
        "description": "Read payment-gateway transaction history, payouts, and reconciliation status. Excludes raw card / bank credentials.",
    },
    "payments:write": {
        "domain": "payments",
        "access": "write",
        "sensitivity": "CRITICAL",
        "description": "Initiate refunds, payouts, or recurring-payment adjustments through configured gateways.",
    },
    "integrations:configure": {
        "domain": "integrations",
        "access": "admin",
        "sensitivity": "HIGH",
        "description": "Add or remove third-party connector credentials (SIS, LMS, SSO, payments).",
    },
    "rostering:read": {
        "domain": "rostering",
        "access": "read",
        "sensitivity": "HIGH",
        "description": "Read OneRoster-style class lists, enrollments, and term structure. Excludes grades.",
    },
    "rostering:write": {
        "domain": "rostering",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Push roster, class, and enrollment changes via OneRoster v1.2 or vendor-specific protocols.",
    },
    "lms:read": {
        "domain": "lms",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read course / assignment / submission metadata from a connected LMS (Canvas, Google Classroom, MS Teams).",
    },
    "lms:write": {
        "domain": "lms",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Push grades, assignments, and roster updates back to the connected LMS.",
    },
    "identity:read": {
        "domain": "identity",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read SSO group membership and JIT-provisioning state. Excludes session tokens.",
    },
    "identity:provision": {
        "domain": "identity",
        "access": "admin",
        "sensitivity": "CRITICAL",
        "description": "Create or deactivate user accounts via SCIM / SAML JIT provisioning.",
    },
    "calendar:read": {
        "domain": "calendar",
        "access": "read",
        "sensitivity": "LOW",
        "description": "Read academic calendar, term boundaries, and term-level events.",
    },
    "calendar:write": {
        "domain": "calendar",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Create or update events and term-level scheduling.",
    },
    "transport:read": {
        "domain": "transport",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read bus routes, stops, and student-to-route assignments.",
    },
    "transport:write": {
        "domain": "transport",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Manage routes, stops, and route assignments.",
    },
    "medical:read": {
        "domain": "medical",
        "access": "read",
        "sensitivity": "CRITICAL",
        "description": "Read student clinic-visit logs, immunization records, and medical alerts (HIPAA / PHI-class data).",
    },
    "medical:write": {
        "domain": "medical",
        "access": "write",
        "sensitivity": "CRITICAL",
        "description": "Record clinic visits, dispense medication entries, or update immunization status.",
    },
    "library:read": {
        "domain": "library",
        "access": "read",
        "sensitivity": "LOW",
        "description": "Read library catalog, loan history, and reservations.",
    },
    "library:write": {
        "domain": "library",
        "access": "write",
        "sensitivity": "LOW",
        "description": "Issue / return loans, update catalog metadata.",
    },
    "boarding:read": {
        "domain": "boarding",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read boarding-house assignments, visitor logs, and curfew status.",
    },
    "boarding:write": {
        "domain": "boarding",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Update boarding assignments, log visits, record curfew or leave permissions.",
    },
    "cafeteria:read": {
        "domain": "cafeteria",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read meal-plan subscriptions, allergens, and POS history.",
    },
    "cafeteria:write": {
        "domain": "cafeteria",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Update meal plans, log POS transactions.",
    },
    "analytics:read": {
        "domain": "analytics",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read aggregated analytics (term averages, attendance trends). No raw student PII.",
    },
    "compliance:read": {
        "domain": "compliance",
        "access": "read",
        "sensitivity": "HIGH",
        "description": "Read audit logs, consent records, and DSAR fulfilment status.",
    },
    "compliance:write": {
        "domain": "compliance",
        "access": "admin",
        "sensitivity": "CRITICAL",
        "description": "Trigger DSAR exports, record consent decisions, finalize retention policies.",
    },
    "ai:invoke": {
        "domain": "ai",
        "access": "write",
        "sensitivity": "HIGH",
        "description": "Invoke AI gateway tasks within the tenant's AI policy. High-PII content is local-only regardless of caller.",
    },
    "ai:read_audit": {
        "domain": "ai",
        "access": "read",
        "sensitivity": "MEDIUM",
        "description": "Read AI gateway audit logs and per-tenant usage metrics. Excludes prompt / response payloads.",
    },
    "reports:run": {
        "domain": "reports",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Run report templates and export aggregated data; subject to redaction rules.",
    },
    "reports:configure": {
        "domain": "reports",
        "access": "admin",
        "sensitivity": "MEDIUM",
        "description": "Create or edit report-template definitions.",
    },
    "workflow:execute": {
        "domain": "workflow",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Run already-published workflows on behalf of the school.",
    },
    "workflow:author": {
        "domain": "workflow",
        "access": "admin",
        "sensitivity": "HIGH",
        "description": "Create, edit, or publish workflow definitions in the tenant's workflow studio.",
    },
    "settings:read": {
        "domain": "settings",
        "access": "read",
        "sensitivity": "LOW",
        "description": "Read non-secret tenant settings (branding, locale, calendar). Excludes credentials.",
    },
    "settings:write": {
        "domain": "settings",
        "access": "write",
        "sensitivity": "MEDIUM",
        "description": "Update non-secret tenant settings (branding, locale, calendar).",
    },
    "files:admin": {
        "domain": "files",
        "access": "admin",
        "sensitivity": "HIGH",
        "description": "Manage the tenant's file/document spaces, including retention and legal-hold settings.",
    },
}


def list_scope_codes() -> list[str]:
    """Stable, sorted list of every scope code. Useful for tests and OpenAPI docs."""
    return sorted(MARKETPLACE_SCOPES.keys())


def is_valid_scope(code: str) -> bool:
    return code in MARKETPLACE_SCOPES
