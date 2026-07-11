"""OneRoster v1.2 inbound accelerator.

OneRoster (1EdTech) is the highest-leverage accelerator we can ship — it's
the de-facto US K-12 roster interchange standard, supported (with varying
fidelity) by PowerSchool, Infinite Campus, Blackbaud, Veracross, FACTS,
Skyward, Alma, Clever, ClassLink, Schoology, and most state DoEs.

A OneRoster CSV bundle is a fixed-name set of files:

    users.csv, students.csv, teachers.csv, parents.csv, courses.csv,
    classes.csv, enrollments.csv, orgs.csv, academicSessions.csv,
    demographics.csv, manifest.csv

Each row has a ``sourcedId`` (stable identifier) + ``status`` (active/
tobedeleted) so re-runs of the same bundle replace the same logical
record without duplicates.

What this accelerator does:
    1. Recognizes a OneRoster bundle (manifest.csv or known filename set).
    2. Pre-classifies each known file to the correct canonical domain.
    3. Pre-attaches canonical column mappings (the OneRoster spec is fixed
       so we don't need the AI mapper for these columns).
    4. Returns an ``AcceleratorContract`` for the orchestrator to apply.

When in doubt the accelerator returns ``AcceleratorError`` so the
universal pipeline takes over. Never silently downgrade fidelity.
"""

from __future__ import annotations

import logging
from typing import Any


from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

# OneRoster file → (canonical domain, {source_column: canonical_field}).
ONEROSTER_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "users.csv": (
        # Combined OneRoster user file. It carries a ``role`` column, so the
        # staff lander role-GATES each row (student/parent/guardian rows are
        # skipped, never provisioned as teachers). Bundles that also ship
        # students.csv get their students from there; a pure-1.2 export that
        # only ships users.csv needs the row-level role fan-out (follow-up) to
        # import its students — this mapping never mis-lands them as staff.
        "staff",
        {
            "sourcedId": "staff_external_id",
            "givenName": "first_name",
            "familyName": "last_name",
            "email": "email",
            "role": "role",
            "orgSourcedIds": "department",
        },
    ),
    "students.csv": (
        "students",
        {
            "sourcedId": "external_id",
            "username": "admission_number",
            "givenName": "first_name",
            "familyName": "last_name",
            "middleName": "middle_name",
            "email": "email",
            "phone": "phone",
            "birthDate": "date_of_birth",
            "grades": "grade_level",
            "enabledUser": "enrollment_status",
        },
    ),
    "teachers.csv": (
        "staff",
        {
            "sourcedId": "staff_external_id",
            "givenName": "first_name",
            "familyName": "last_name",
            "email": "email",
            "orgSourcedIds": "department",
        },
    ),
    "parents.csv": (
        "guardians",
        {
            "sourcedId": "guardian_external_id",
            "givenName": "first_name",
            "familyName": "last_name",
            "email": "email",
            "phone": "phone",
            "agentSourcedIds": "student_external_id",
        },
    ),
    "courses.csv": (
        "academics",
        {
            "sourcedId": "subject_code",
            "title": "subject_name",
            "courseCode": "subject_code",
            "subjects": "department",
        },
    ),
    "classes.csv": (
        "sections",
        {
            "sourcedId": "section_external_id",
            "courseSourcedId": "subject_code",
            "schoolSourcedId": "academic_year",
            "termSourcedIds": "term",
        },
    ),
    "enrollments.csv": (
        "enrollment",
        {
            "userSourcedId": "student_external_id",
            "classSourcedId": "homeroom",
            "schoolSourcedId": "academic_year",
            "beginDate": "enrollment_date",
            "endDate": "exit_date",
        },
    ),
    # academicSessions.csv (terms/years) is intentionally NOT pre-classified to
    # "academics": those rows are calendar sessions, NOT subjects, and mapping
    # their titles into the Subject catalog created bogus subjects. It falls
    # through to the universal pipeline (custom_fields) instead of polluting
    # apps.academics.Subject.
}


class OneRosterV1p2InboundAccelerator(Accelerator):
    """Inbound accelerator for OneRoster v1.2 CSV bundles."""

    source = "oneroster"
    version = "1.2"

    def is_handle_supported(self, handle: Any) -> bool:
        # The accelerator typically activates after the universal intake has
        # already registered the bundle's artifacts. The "handle" here is
        # the ``MigrationBundle`` instance; we inspect filenames to decide.
        from apps.migration_cloud.models import MigrationBundle

        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return "manifest.csv" in names or len(names & ONEROSTER_FILE_MAP.keys()) >= 3

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        from apps.migration_cloud.models import MigrationBundle

        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("OneRoster accelerator requires the MigrationBundle as handle.")

        artifacts = list(handle.artifacts.all())
        if not artifacts:
            raise AcceleratorError("Bundle has no artifacts to accelerate.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched_files = 0
        for artifact in artifacts:
            entry = ONEROSTER_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_oneroster_v1p2",
            }
            matched_files += 1

        if matched_files == 0:
            raise AcceleratorError(
                "OneRoster accelerator did not match any expected filenames; "
                "falling back to universal pipeline."
            )

        contract.vendor_enum_tables["enabledUser"] = {
            "true": "active",
            "false": "inactive",
            "TRUE": "active",
            "FALSE": "inactive",
        }
        contract.vendor_enum_tables["status"] = {
            "active": "active",
            "tobedeleted": "withdrawn",
        }
        contract.notes.append(
            f"Pre-classified {matched_files} OneRoster v1.2 file(s); "
            "universal mapper still runs for unmapped columns + custom fields."
        )

        logger.info(
            "migration_cloud.accelerators.oneroster: contract built for bundle %s with %d files",
            bundle_id, matched_files,
        )
        return contract


register_accelerator("oneroster", OneRosterV1p2InboundAccelerator())
