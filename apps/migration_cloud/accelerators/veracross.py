"""Veracross inbound accelerator.

Veracross targets the US independent-school + boarding-school market.
Their v2 API + CSV exports use camelCase columns with ``personId`` as the
primary key. Mostly K-12 + some higher-ed (graduate certificates).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models import MigrationBundle

from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

VERACROSS_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "students.csv": (
        "students",
        {
            "personId": "external_id",
            "firstName": "first_name",
            "lastName": "last_name",
            "middleName": "middle_name",
            "dateOfBirth": "date_of_birth",
            "gender": "gender",
            "currentGrade": "grade_level",
            "studentStatus": "enrollment_status",
            "primaryEmail": "email",
            "primaryPhone": "phone",
            "schoolLevel": "grade_level",  # fallback
        },
    ),
    "faculty.csv": (
        "staff",
        {
            "personId": "staff_external_id",
            "firstName": "first_name",
            "lastName": "last_name",
            "primaryEmail": "email",
            "jobTitle": "role",
            "department": "department",
            "hireDate": "hire_date",
        },
    ),
    "parents.csv": (
        "guardians",
        {
            "personId": "guardian_external_id",
            "firstName": "first_name",
            "lastName": "last_name",
            "primaryEmail": "email",
            "primaryPhone": "phone",
            "relationship": "relationship",
            "childPersonId": "student_external_id",
        },
    ),
    "enrollments.csv": (
        "enrollment",
        {
            "personId": "student_external_id",
            "schoolYear": "academic_year",
            "gradeLevel": "grade_level",
            "homeroom": "homeroom",
            "enrollmentDate": "enrollment_date",
            "exitDate": "exit_date",
        },
    ),
    "billing.csv": (
        "finance",
        {
            "personId": "student_external_id",
            "invoiceNumber": "invoice_number",
            "feeCategory": "fee_category",
            "amount": "amount",
            "currency": "currency",
            "dueDate": "due_date",
            "amountPaid": "paid_amount",
            "balance": "balance",
        },
    ),
}


class VeracrossInboundAccelerator(Accelerator):
    source = "veracross"
    version = "v2-2025"

    def is_handle_supported(self, handle: Any) -> bool:
        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return len(names & VERACROSS_FILE_MAP.keys()) >= 2

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("Veracross accelerator requires the MigrationBundle.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in handle.artifacts.all():
            entry = VERACROSS_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_veracross",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError("Veracross accelerator matched no known filenames.")

        contract.vendor_enum_tables["studentStatus"] = {
            "Active": "active",
            "Inactive": "inactive",
            "Withdrawn": "withdrawn",
            "Graduated": "graduated",
            "Re-Enrolled": "active",
        }
        contract.notes.append(f"Pre-classified {matched} Veracross v2 export(s).")
        logger.info(
            "migration_cloud.accelerators.veracross: bundle %s files=%d", bundle_id, matched
        )
        return contract


register_accelerator("veracross", VeracrossInboundAccelerator())
