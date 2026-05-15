"""Alma SIS inbound accelerator (modern cloud SIS, mostly K-12 charter + private)."""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models import MigrationBundle

from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

ALMA_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "students.csv": (
        "students",
        {
            "alma_id": "external_id",
            "first_name": "first_name",
            "last_name": "last_name",
            "middle_name": "middle_name",
            "birth_date": "date_of_birth",
            "gender": "gender",
            "grade": "grade_level",
            "enrollment_status": "enrollment_status",
            "primary_email": "email",
            "primary_phone": "phone",
            "address1": "address",
        },
    ),
    "guardians.csv": (
        "guardians",
        {
            "alma_id": "guardian_external_id",
            "first_name": "first_name",
            "last_name": "last_name",
            "primary_email": "email",
            "primary_phone": "phone",
            "relationship": "relationship",
            "student_alma_id": "student_external_id",
            "is_primary_contact": "is_primary",
        },
    ),
    "teachers.csv": (
        "staff",
        {
            "alma_id": "staff_external_id",
            "first_name": "first_name",
            "last_name": "last_name",
            "primary_email": "email",
            "role": "role",
            "department": "department",
            "hire_date": "hire_date",
        },
    ),
    "courses.csv": (
        "academics",
        {
            "course_code": "subject_code",
            "course_name": "subject_name",
            "credits": "credits",
            "department": "department",
        },
    ),
    "sections.csv": (
        "sections",
        {
            "section_id": "section_external_id",
            "course_code": "subject_code",
            "teacher_id": "teacher_external_id",
            "academic_year": "academic_year",
            "term": "term",
        },
    ),
}


class AlmaInboundAccelerator(Accelerator):
    source = "alma"
    version = "Cloud-2025"

    def is_handle_supported(self, handle: Any) -> bool:
        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return len(names & ALMA_FILE_MAP.keys()) >= 2

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("Alma accelerator requires the MigrationBundle.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in handle.artifacts.all():
            entry = ALMA_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_alma",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError("Alma accelerator matched no known filenames.")

        contract.vendor_enum_tables["enrollment_status"] = {
            "active": "active", "inactive": "inactive",
            "withdrawn": "withdrawn", "graduated": "graduated",
        }
        contract.notes.append(f"Pre-classified {matched} Alma cloud-SIS export(s).")
        logger.info("migration_cloud.accelerators.alma: bundle %s files=%d", bundle_id, matched)
        return contract


register_accelerator("alma", AlmaInboundAccelerator())
