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
}


def list_scope_codes() -> list[str]:
    """Stable, sorted list of every scope code. Useful for tests and OpenAPI docs."""
    return sorted(MARKETPLACE_SCOPES.keys())


def is_valid_scope(code: str) -> bool:
    return code in MARKETPLACE_SCOPES
