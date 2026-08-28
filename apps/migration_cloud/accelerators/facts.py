"""FACTS / RenWeb inbound accelerator (Catholic / faith-based market).

FACTS Education Solutions (formerly RenWeb + FACTS Management) dominates
the US Catholic / Christian / Jewish independent-school market. Their
exports use ``StudentID`` / ``FamilyID`` + religion / sacrament fields
unique to faith-based schools — those land in ``custom_fields`` since
they're outside the secular canonical ontology.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models import MigrationBundle

from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

FACTS_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "Students.csv": (
        "students",
        {
            "StudentID": "external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "MiddleName": "middle_name",
            "DateOfBirth": "date_of_birth",
            "Gender": "gender",
            "GradeLevel": "grade_level",
            "Status": "enrollment_status",
            "Email": "email",
            "HomePhone": "phone",
            "Address1": "address",
        },
    ),
    "Parents.csv": (
        "guardians",
        {
            "ParentID": "guardian_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "Email": "email",
            "MobilePhone": "phone",
            "Relationship": "relationship",
            "StudentID": "student_external_id",
            "PrimaryContact": "is_primary",
        },
    ),
    "Faculty.csv": (
        "staff",
        {
            "FacultyID": "staff_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "Email": "email",
            "Position": "role",
            "Department": "department",
            "HireDate": "hire_date",
        },
    ),
    "Billing.csv": (
        "finance",
        {
            "FamilyID": "student_external_id",  # FACTS bills by family — approximation
            "InvoiceID": "invoice_number",
            "FeeType": "fee_category",
            "Amount": "amount",
            "DueDate": "due_date",
            "PaidAmount": "paid_amount",
            "Balance": "balance",
        },
    ),
    "Courses.csv": (
        "academics",
        {
            "CourseID": "subject_code",
            "CourseName": "subject_name",
            "CourseTitle": "subject_name",
            "Department": "department",
            "Credits": "credits",
        },
    ),
    # Sacrament data is faith-school-specific — preserve as custom_fields.
    "Sacraments.csv": ("custom_fields", {}),
    "Religion.csv": ("custom_fields", {}),
}


class FactsInboundAccelerator(Accelerator):
    source = "facts"
    version = "SIS-2025"

    def is_handle_supported(self, handle: Any) -> bool:
        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return len(names & FACTS_FILE_MAP.keys()) >= 2

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("FACTS accelerator requires the MigrationBundle.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in handle.artifacts.all():
            entry = FACTS_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_facts",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError("FACTS accelerator matched no known filenames.")

        contract.vendor_enum_tables["Status"] = {
            "A": "active",
            "I": "inactive",
            "W": "withdrawn",
            "G": "graduated",
            "P": "pending",
        }
        contract.notes.append(
            f"Pre-classified {matched} FACTS / RenWeb export(s); sacrament + "
            "religion data preserved as custom_fields (faith-specific)."
        )
        logger.info(
            "migration_cloud.accelerators.facts: bundle %s files=%d", bundle_id, matched
        )
        return contract


register_accelerator("facts", FactsInboundAccelerator())
