"""DSAR subject-data coverage registry (completeness guardrail).

The DSAR export/erase services (``apps.compliance.gdpr_services`` +
``apps.compliance.dsar_subjects``) cover the data subjects the platform holds
Personal Data for — student, teacher/staff, parent/guardian, applicant — plus
the User identity and the related PII-bearing rows scrubbed as part of a
subject's erasure. Coverage was, until now, enforced only by hand: nothing
stopped a newly-added PII-bearing model from silently escaping both export and
erasure. A DSAR export that omits a category of the subject's data — or an
Art.17 erasure that leaves a table of their PII behind — is a compliance
failure, so completeness is the core property of the metric.

This module makes coverage a **declarative, testable contract**. Every concrete
model in the data-subject home apps (``people``, ``accounts`` — where a new PII
model would realistically land) that carries a direct-identifier field MUST be
classified here as one of:

* ``SUBJECT``       — a data-subject root model with a dedicated exporter +
  eraser (e.g. ``people.StudentProfile``).
* ``RELATED_ERASED`` — a PII-bearing model whose columns are redacted as part of
  a subject's erasure (e.g. ``people.BadgeScanEvent`` is scrubbed by the student
  + staff erasers).
* ``EXEMPT``        — carries an identifier-shaped field but is legitimately out
  of individual-DSAR scope, with a documented legal basis / reason (security
  audit logs, immutable consent-proof, transient invite tokens, B2B org
  records).

``build_coverage_report`` introspects the live models at test time; the
companion test (``tests/test_dsar_coverage_registry.py``) fails loudly when a
PII-bearing model in scope is UNCLASSIFIED, forcing the author of a new model to
either wire an exporter/eraser or record an explicit, reviewed exemption. The
scan is deliberately scoped to the subject-home apps and keyed on a precise set
of direct-identifier field names so it stays low-noise and durable.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps

# --- PII detection ------------------------------------------------------------
# Direct-identifier field names. Deliberately precise (not a fuzzy "*name*"
# match) so the guardrail flags real identifiers without drowning in false
# positives on generic columns like ``name`` / ``title`` / ``description``.
PII_IDENTIFIER_FIELDS: frozenset[str] = frozenset(
    {
        # names
        "first_name",
        "last_name",
        "middle_name",
        "maiden_name",
        "preferred_name",
        "full_name",
        "guardian_name",
        "mother_name",
        "father_name",
        "next_of_kin",
        # electronic contact
        "email",
        "email_address",
        "personal_email",
        "contact_email",
        "phone",
        "phone_number",
        "mobile",
        "mobile_number",
        "telephone",
        "whatsapp_number",
        "whatsapp",
        # postal / geo
        "address",
        "home_address",
        "residential_address",
        "street_address",
        "place_of_birth",
        "nationality",
        # identity / regulated
        "date_of_birth",
        "dob",
        "birth_date",
        "birthday",
        "national_id",
        "ssn",
        "passport_number",
        "tax_id",
        "nin",
        "bvn",
        # biometrics / media
        "profile_photo",
        "photo",
        # staff financial identifiers
        "salary_amount",
        "pay_grade",
        "paystub_notes",
        "staff_id",
        # network identifier (personal data under GDPR)
        "ip_address",
    }
)

# Apps whose models are enforced by the coverage test — the "home" of tenant
# data subjects, where a new PII-bearing subject/related model would land.
PII_SCAN_APPS: tuple[str, ...] = ("people", "accounts")

# --- Coverage classification --------------------------------------------------
# SUBJECT: data-subject root models with a dedicated export + erase producer.
# Producers are dotted paths, verified live by the coverage test.
DSAR_SUBJECT_MODELS: dict[str, dict[str, Any]] = {
    "people.StudentProfile": {
        "subject_kind": "student",
        "export": "apps.compliance.gdpr_services.export_student_data_portability",
        "erase": "apps.compliance.gdpr_services.gdpr_scrub_student",
    },
    "people.TeacherProfile": {
        "subject_kind": "staff",
        "export": "apps.compliance.dsar_subjects.export_staff_data",
        "erase": "apps.compliance.dsar_subjects.gdpr_scrub_staff",
    },
    "people.StudentGuardian": {
        "subject_kind": "guardian",
        "export": "apps.compliance.dsar_subjects.export_guardian_data",
        "erase": "apps.compliance.dsar_subjects.gdpr_scrub_guardian",
    },
    "people.Applicant": {
        "subject_kind": "applicant",
        "export": "apps.compliance.dsar_subjects.export_applicant_data",
        "erase": "apps.compliance.dsar_subjects.gdpr_scrub_applicant",
    },
    "accounts.User": {
        # The User identity is never a standalone DSAR subject: it is exported
        # inside every subject payload ("user" block) and anonymized in place by
        # the shared core anonymizer invoked by every subject eraser.
        "subject_kind": "user_identity",
        "export": None,
        "erase": "apps.compliance.dsar_subjects._anonymize_user_core",
    },
}

# RELATED_ERASED: PII-bearing models (inside the scan apps) whose columns are
# redacted as part of a data subject's erasure. ``erased_by`` names the eraser(s)
# that scrub the row; the coverage test verifies those callables import.
DSAR_RELATED_ERASED_MODELS: dict[str, dict[str, Any]] = {
    "people.BadgeScanEvent": {
        "erased_by": [
            "apps.compliance.gdpr_services.gdpr_scrub_student",
            "apps.compliance.dsar_subjects.gdpr_scrub_staff",
        ],
        "columns": ["ip_address", "user_agent", "notes"],
        "note": (
            "Access/scan telemetry linked to the subject via student/user FK; "
            "IP + device + free-text notes are stripped when the subject is erased."
        ),
    },
}

# EXEMPT: carries an identifier-shaped field but is legitimately outside the
# individual right-to-erasure. Each entry records the legal basis so the carve
# out is reviewed, not silent.
DSAR_EXEMPT_MODELS: dict[str, dict[str, str]] = {
    "accounts.SecurityAuditLog": {
        "reason": (
            "Security / forensic event log (login, MFA change, impossible-travel). "
            "Retained under a security / fraud-prevention legitimate-interest and "
            "governed by the audit-retention purge path, not subject-erasure."
        ),
        "legal_basis": "GDPR Art.17(3)(b)/(e) + Recital 49 (security legitimate interest)",
    },
    "people.TransferConsent": {
        "reason": (
            "Immutable inter-school transfer consent-proof record. guardian_name / "
            "guardian_email + the consent-text hash are the evidence of what a "
            "guardian agreed to; redacting them would destroy the legal proof of "
            "consent for the transfer decision."
        ),
        "legal_basis": "GDPR Art.17(3)(b)/(e) (legal claims / consent evidence)",
    },
    "accounts.TenantStaffInvite": {
        "reason": (
            "Transient pre-account staff invitation token (has expires_at). The "
            "invitee is not yet a data subject with a profile; once the invite is "
            "accepted their DSAR is served via the staff (TeacherProfile) subject."
        ),
        "legal_basis": "Not an enrolled data subject; token expires by design",
    },
    "people.EmployerProfile": {
        "reason": (
            "External employer / B2B partner organisation record (company_name + "
            "organisational contact_email) for apprenticeship placements. The "
            "linked login User's identity PII is covered by the SUBJECT 'accounts."
            "User' anonymizer; the org contact fields are not individual DSAR data."
        ),
        "legal_basis": "Organisation record, not an individual data subject",
    },
}

# Documentation-only: PII-bearing models OUTSIDE the scan apps that the student
# eraser already redacts. Not enforced by the scan (their apps are not in
# PII_SCAN_APPS) but recorded here so the full erase surface is discoverable and
# the coverage test can assert these labels still resolve to live models.
DSAR_CROSS_APP_ERASED: dict[str, str] = {
    "academics.Attendance": "remarks cleared by gdpr_scrub_student",
    "academics.Incident": "description redacted by gdpr_scrub_student",
    "evals.Evaluation": "remarks cleared by gdpr_scrub_student",
    "finance.Counterparty": "contact PII redacted by _redact_counterparty_pii",
    "athletics.MedicalClearance": "notes/document scrubbed by athletics_scrub_student",
    "athletics.ParticipationConsent": "guardian PII scrubbed by athletics_scrub_student",
}


def _concrete_models_in_scope():
    """Yield concrete, non-proxy models from the scan apps."""
    for app_label in PII_SCAN_APPS:
        try:
            config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in config.get_models():
            meta = model._meta
            if meta.proxy or meta.abstract:
                continue
            yield model


def pii_fields_for(model) -> list[str]:
    """Return the sorted direct-identifier field names present on ``model``."""
    names: set[str] = set()
    for field in model._meta.concrete_fields:
        names.add(field.name)
        names.add(field.attname)
    return sorted(names & PII_IDENTIFIER_FIELDS)


def iter_pii_bearing_models():
    """Yield ``(label, [pii_fields])`` for in-scope models with identifier fields."""
    for model in _concrete_models_in_scope():
        matched = pii_fields_for(model)
        if matched:
            yield model._meta.label, matched


def build_coverage_report(
    *,
    subjects: dict[str, Any] | None = None,
    related: dict[str, Any] | None = None,
    exempt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify every in-scope PII-bearing model against the registry.

    The registry maps default to the module constants; the test passes trimmed
    copies to prove the guardrail actually trips (a removed entry surfaces as
    ``unclassified``). Returns buckets plus an ``unclassified`` list of
    ``{"label", "pii_fields"}`` — the coverage test asserts that list is empty.
    """
    subjects = DSAR_SUBJECT_MODELS if subjects is None else subjects
    related = DSAR_RELATED_ERASED_MODELS if related is None else related
    exempt = DSAR_EXEMPT_MODELS if exempt is None else exempt

    report: dict[str, Any] = {
        "covered_subjects": [],
        "related_erased": [],
        "exempt": [],
        "unclassified": [],
    }
    for label, matched in iter_pii_bearing_models():
        entry = {"label": label, "pii_fields": matched}
        if label in subjects:
            report["covered_subjects"].append(entry)
        elif label in related:
            report["related_erased"].append(entry)
        elif label in exempt:
            report["exempt"].append(entry)
        else:
            report["unclassified"].append(entry)
    return report
