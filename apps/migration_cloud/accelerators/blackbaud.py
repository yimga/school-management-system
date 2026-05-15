"""Blackbaud inbound accelerator (Education Management — formerly OnRecord).

Blackbaud dominates the US independent-school market. Their SKY API
returns JSON; their CSV/Excel exports use ``UserHostID`` /
``EnrollmentStatus`` shapes. The accelerator recognises both filename
patterns and pre-attaches canonical mappings + enum tables.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models import MigrationBundle

from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

BLACKBAUD_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "Students.csv": (
        "students",
        {
            "UserHostID": "external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "MiddleName": "middle_name",
            "BirthDate": "date_of_birth",
            "Gender": "gender",
            "GradeLevel": "grade_level",
            "EnrollmentStatus": "enrollment_status",
            "PrimaryEmail": "email",
            "MobilePhone": "phone",
        },
    ),
    "Faculty.csv": (
        "staff",
        {
            "UserHostID": "staff_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "PrimaryEmail": "email",
            "Position": "role",
            "Department": "department",
            "HireDate": "hire_date",
        },
    ),
    "Parents.csv": (
        "guardians",
        {
            "UserHostID": "guardian_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "PrimaryEmail": "email",
            "MobilePhone": "phone",
            "Relationship": "relationship",
            "StudentUserHostID": "student_external_id",
            "IsPrimaryContact": "is_primary",
        },
    ),
    "Transcripts.csv": (
        "transcripts",
        {
            "UserHostID": "student_external_id",
            "SchoolYear": "academic_year",
            "CourseCode": "subject_code",
            "FinalGrade": "final_grade",
            "Credits": "credits_earned",
            "GradePoints": "gpa_points",
        },
    ),
    "AdvisorAssignments.csv": (
        "sections",
        {
            "AdvisorHostID": "teacher_external_id",
            "GradeLevel": "academic_year",
        },
    ),
    "DonorPledges.csv": (
        # Blackbaud's donor pipeline doesn't have a canonical home in the
        # K-12 ontology — falls into custom_fields for explicit handling.
        "custom_fields",
        {},
    ),
}


class BlackbaudInboundAccelerator(Accelerator):
    source = "blackbaud"
    version = "EM-2025"

    def is_handle_supported(self, handle: Any) -> bool:
        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return len(names & BLACKBAUD_FILE_MAP.keys()) >= 2

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("Blackbaud accelerator requires the MigrationBundle.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in handle.artifacts.all():
            entry = BLACKBAUD_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_blackbaud",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError("Blackbaud accelerator matched no known filenames.")

        contract.vendor_enum_tables["EnrollmentStatus"] = {
            "Currently Enrolled": "active",
            "Withdrawn": "withdrawn",
            "Graduated": "graduated",
            "Pending": "pending",
            "Inactive": "inactive",
        }
        contract.notes.append(
            f"Pre-classified {matched} Blackbaud Education Management export(s)."
        )
        logger.info(
            "migration_cloud.accelerators.blackbaud: bundle %s files=%d", bundle_id, matched
        )
        return contract


register_accelerator("blackbaud", BlackbaudInboundAccelerator())
