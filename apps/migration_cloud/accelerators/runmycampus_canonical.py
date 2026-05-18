"""RunMyCampus canonical-template accelerator — the long-tail path.

The "Shopify CSV import" pattern applied to schools. Any operator with
data in Excel, Google Sheets, MS Access, a regional SIS not yet in the
signature table, or an in-house custom app can produce a canonical
RunMyCampus bundle by downloading our template, filling in what they
have, and uploading. No vendor accelerator needed.

Filename convention (case-insensitive, matched against the canonical
domain set):

    students.csv      staff.csv         guardians.csv      enrollment.csv
    sections.csv      attendance.csv    grades.csv         behavior.csv
    finance.csv       transcripts.csv   health.csv         payroll.csv
    communications.csv events.csv       library.csv        transport.csv
    hostel.csv        cafeteria.csv     alumni.csv         compliance.csv

Headers in each file ARE the canonical field names — there is no source-
column-to-canonical-field mapping needed because the column names already
*are* the canonical fields. The accelerator pre-classifies each file and
attaches an identity mapping so the mapper's AI tier never runs for these
columns. Custom / per-tenant columns past the canonical set still flow
through the universal mapper as ``custom_fields``.

This accelerator is what makes "RunMyCampus is the platform for the long
tail of K-12" credible — any school migrating from any tool can produce
this bundle. Pairs with a wizard-side "Download canonical template" UX
(separate workstream) that generates the empty template per-domain so
operators don't have to invent the header set.

Activation:
    - Filename matches one of the canonical names (case-insensitive), OR
    - First-row headers include >= 3 canonical field names for that
      domain (so a renamed file still gets recognized).

When in doubt the accelerator raises ``AcceleratorError`` so the
universal pipeline takes over. Never silently downgrade fidelity.
"""

from __future__ import annotations

import logging
from typing import Any


from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)


# Canonical filename → canonical domain. Headers in each file are the
# canonical field names themselves, so we don't need column mappings.
CANONICAL_FILENAME_TO_DOMAIN: dict[str, str] = {
    "students.csv": "students",
    "staff.csv": "staff",
    "teachers.csv": "staff",
    "guardians.csv": "guardians",
    "parents.csv": "guardians",
    "enrollment.csv": "enrollment",
    "enrollments.csv": "enrollment",
    "sections.csv": "sections",
    "classes.csv": "sections",
    "attendance.csv": "attendance",
    "grades.csv": "grades",
    "behavior.csv": "behavior",
    "incidents.csv": "behavior",
    "finance.csv": "finance",
    "invoices.csv": "finance",
    "transcripts.csv": "transcripts",
    "health.csv": "health",
    "payroll.csv": "payroll",
    "communications.csv": "communications",
    "events.csv": "events",
    "library.csv": "library",
    "transport.csv": "transport",
    "transport_assignments.csv": "transport_assignments",
    "hostel.csv": "hostel",
    "hostel_assignments.csv": "hostel_assignments",
    "cafeteria.csv": "cafeteria",
    "cafeteria_assignments.csv": "cafeteria_assignments",
    "alumni.csv": "alumni",
    "compliance.csv": "compliance",
}


# Per-domain canonical header set. Used as the secondary activation
# signal when filenames have been renamed (operator-friendly).
DOMAIN_CANONICAL_HEADERS: dict[str, set[str]] = {
    "students": {
        "external_id", "first_name", "last_name", "middle_name",
        "date_of_birth", "gender", "email", "phone", "grade_level",
        "enrollment_status", "admission_number", "address",
    },
    "staff": {
        "staff_external_id", "first_name", "last_name", "email",
        "role", "department", "phone",
    },
    "guardians": {
        "guardian_external_id", "first_name", "last_name", "email",
        "phone", "relationship", "is_primary", "student_external_id",
    },
    "enrollment": {
        "student_external_id", "grade_level", "enrollment_status",
        "enrollment_date", "exit_date", "section",
    },
    "sections": {
        "section_external_id", "subject_code", "subject_name",
        "term", "academic_year", "teacher_external_id",
    },
    "attendance": {
        "student_external_id", "date", "status", "code", "notes",
    },
    "grades": {
        "student_external_id", "subject_code", "term", "score",
        "letter_grade", "comments",
    },
    "behavior": {
        "student_external_id", "date", "category", "description",
        "action_taken",
    },
    "finance": {
        "reference", "student_external_id", "amount", "currency",
        "issued_date", "due_date", "status", "description",
    },
    "transcripts": {
        "student_external_id", "academic_year", "term", "subject_code",
        "final_grade", "credits_earned",
    },
    "health": {
        "student_external_id", "record_date", "category", "description",
        "provider", "follow_up",
    },
    "payroll": {
        "staff_external_id", "pay_period", "gross_amount", "net_amount",
        "currency", "issued_date",
    },
    "communications": {
        "recipient_external_id", "channel", "subject", "body",
        "sent_at", "status",
    },
    "events": {
        "title", "category", "starts_at", "ends_at", "location",
        "description",
    },
    "library": {
        "item_external_id", "title", "author", "isbn", "category",
        "status",
    },
    "transport": {
        "student_external_id", "route", "stop", "pickup_time",
        "dropoff_time", "vehicle",
    },
    "transport_assignments": {
        "student_external_id", "route", "stop", "pickup_time",
        "dropoff_time",
    },
    "hostel": {
        "student_external_id", "room", "bed", "checkin_date",
        "checkout_date",
    },
    "hostel_assignments": {
        "student_external_id", "hostel", "room", "checkin_date",
        "checkout_date",
    },
    "cafeteria": {
        "student_external_id", "meal_plan", "balance", "currency",
        "dietary_notes",
    },
    "cafeteria_assignments": {
        "student_external_id", "meal_plan", "balance", "currency",
        "dietary_notes",
    },
    "alumni": {
        "external_id", "first_name", "last_name", "graduation_year",
        "email", "phone", "current_employer", "current_role",
    },
    "compliance": {
        "subject_external_id", "category", "status", "due_date",
        "completed_date", "notes",
    },
}


# Minimum canonical headers that must be present for the second-tier
# (header-only) activation to fire when the filename has been renamed.
HEADER_MATCH_MIN_HITS = 3


class RunMyCampusCanonicalAccelerator(Accelerator):
    """Accelerator for the canonical RunMyCampus template format.

    Activates when uploaded artifacts match either the canonical
    filename set or the canonical header set per domain. Pre-classifies
    each artifact with identity mappings so the mapper's AI tier never
    runs for known canonical columns.
    """

    source = "runmycampus_canonical"
    version = "1.0"

    def is_handle_supported(self, handle: Any) -> bool:
        from apps.migration_cloud.models import MigrationBundle

        if not isinstance(handle, MigrationBundle):
            return False
        # Filename signal first (cheap).
        artifact_names = {
            (name or "").strip().lower()
            for name in handle.artifacts.values_list("filename", flat=True)
        }
        if artifact_names & CANONICAL_FILENAME_TO_DOMAIN.keys():
            return True
        # Header signal second — covers renamed files.
        for artifact in handle.artifacts.all():
            domain = _domain_from_headers(artifact)
            if domain is not None:
                return True
        return False

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        from apps.migration_cloud.models import MigrationBundle

        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError(
                "RunMyCampus canonical accelerator requires the MigrationBundle as handle."
            )

        artifacts = list(handle.artifacts.all())
        if not artifacts:
            raise AcceleratorError("Bundle has no artifacts to accelerate.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in artifacts:
            domain = _domain_for_artifact(artifact)
            if domain is None:
                continue
            canonical_headers = DOMAIN_CANONICAL_HEADERS.get(domain, set())
            # Identity mapping: every header that matches a canonical field
            # name is mapped to itself. Unknown headers stay for the mapper
            # to handle as custom_fields.
            artifact_headers = _artifact_headers(artifact)
            mappings = {h: h for h in artifact_headers if h in canonical_headers}
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": mappings,
                "method": "accelerator_runmycampus_canonical",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError(
                "RunMyCampus canonical accelerator did not match any artifacts; "
                "falling back to universal pipeline."
            )

        # Common enum normalizations operators are likely to use in the
        # canonical template (English-language defaults).
        contract.vendor_enum_tables["enrollment_status"] = {
            "active": "active",
            "enrolled": "active",
            "current": "active",
            "withdrawn": "withdrawn",
            "dropped": "withdrawn",
            "graduated": "graduated",
            "inactive": "inactive",
        }
        contract.vendor_enum_tables["is_primary"] = {
            "yes": "true", "true": "true", "1": "true", "y": "true",
            "no": "false", "false": "false", "0": "false", "n": "false",
        }
        contract.notes.append(
            f"Pre-classified {matched} canonical-template artifact(s) with "
            "identity mappings; universal mapper still runs for non-canonical columns."
        )

        logger.info(
            "migration_cloud.accelerators.runmycampus_canonical: "
            "contract built for bundle %s with %d artifacts",
            bundle_id, matched,
        )
        return contract


def _artifact_headers(artifact: Any) -> set[str]:
    """Pull the lowercased canonical header set from an artifact's profile."""
    profile = getattr(artifact, "profile", None) or {}
    cols = profile.get("columns") or []
    headers = set()
    for c in cols:
        name = (c.get("name") or "").strip().lower()
        if name:
            headers.add(name)
    return headers


def _domain_from_headers(artifact: Any) -> str | None:
    """Best-matching domain based on canonical-header overlap, or None."""
    headers = _artifact_headers(artifact)
    if not headers:
        return None
    best_domain: str | None = None
    best_hits = 0
    for domain, canonical in DOMAIN_CANONICAL_HEADERS.items():
        hits = len(headers & canonical)
        if hits >= HEADER_MATCH_MIN_HITS and hits > best_hits:
            best_domain = domain
            best_hits = hits
    return best_domain


def _domain_for_artifact(artifact: Any) -> str | None:
    """Resolve an artifact to a canonical domain via filename first, then headers."""
    filename = ((getattr(artifact, "filename", "") or "").strip().lower())
    if filename in CANONICAL_FILENAME_TO_DOMAIN:
        return CANONICAL_FILENAME_TO_DOMAIN[filename]
    return _domain_from_headers(artifact)


register_accelerator("runmycampus_canonical", RunMyCampusCanonicalAccelerator())
