"""Skyward inbound accelerator (US public K-12)."""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models import MigrationBundle

from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

SKYWARD_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "students.csv": (
        "students",
        {
            "OtherID": "external_id",
            "NameKey": "external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "MiddleName": "middle_name",
            "BirthDate": "date_of_birth",
            "Gender": "gender",
            "GradeLevel": "grade_level",
            "EnrollStatus": "enrollment_status",
            "EmailAddress": "email",
            "Phone": "phone",
        },
    ),
    "guardians.csv": (
        "guardians",
        {
            "FamilyKey": "guardian_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "EmailAddress": "email",
            "Phone": "phone",
            "Relationship": "relationship",
            "StudentKey": "student_external_id",
        },
    ),
    "staff.csv": (
        "staff",
        {
            "StaffKey": "staff_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "EmailAddress": "email",
            "Position": "role",
            "Department": "department",
        },
    ),
    "courses.csv": (
        "academics",
        {
            "CourseKey": "subject_code",
            "CourseCode": "subject_code",
            "CourseName": "subject_name",
            "CourseTitle": "subject_name",
            "Department": "department",
            "CreditValue": "credits",
        },
    ),
}


class SkywardInboundAccelerator(Accelerator):
    source = "skyward"
    version = "SMS-2025"

    def is_handle_supported(self, handle: Any) -> bool:
        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return len(names & SKYWARD_FILE_MAP.keys()) >= 2

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("Skyward accelerator requires the MigrationBundle.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in handle.artifacts.all():
            entry = SKYWARD_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_skyward",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError("Skyward accelerator matched no known filenames.")

        contract.vendor_enum_tables["EnrollStatus"] = {
            "E": "active", "W": "withdrawn", "G": "graduated", "I": "inactive",
        }
        contract.notes.append(f"Pre-classified {matched} Skyward SMS export(s).")
        logger.info("migration_cloud.accelerators.skyward: bundle %s files=%d", bundle_id, matched)
        return contract


register_accelerator("skyward", SkywardInboundAccelerator())
