"""PowerSchool inbound accelerator.

PowerSchool is the largest US K-12 SIS. Schools export via PowerQueries
(SQL-like report builder) or the public DAT exports. Both produce CSVs
with characteristic header shapes (``Student_Number``, ``LastFirst``,
``Enroll_Status``, ``DCID``).

This accelerator recognises a PowerSchool-shaped bundle and pre-attaches
canonical column mappings + vendor enum tables (Enroll_Status codes,
Gender codes) so the universal mapper skips its AI tiebreaker for the
columns we already know.

Columns the school added on top (custom fields, state-specific reporting
columns) still flow through the universal mapper. **No bypass.**
"""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models import MigrationBundle

from .base import Accelerator, AcceleratorContract, AcceleratorError, register_accelerator

logger = logging.getLogger(__name__)

POWERSCHOOL_FILE_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "students.csv": (
        "students",
        {
            "Student_Number": "external_id",
            "DCID": "external_id",  # fallback when Student_Number missing
            "First_Name": "first_name",
            "Last_Name": "last_name",
            "Middle_Name": "middle_name",
            "DOB": "date_of_birth",
            "Gender": "gender",
            "Grade_Level": "grade_level",
            "Enroll_Status": "enrollment_status",
            "Home_Phone": "phone",
            "Student_Email": "email",
            "Street": "address",
        },
    ),
    "teachers.csv": (
        "staff",
        {
            "TeacherNumber": "staff_external_id",
            "First_Name": "first_name",
            "Last_Name": "last_name",
            "Email_Addr": "email",
            "Title": "role",
            "Department": "department",
            "HireDate": "hire_date",
        },
    ),
    "contacts.csv": (
        "guardians",
        {
            "PersonID": "guardian_external_id",
            "FirstName": "first_name",
            "LastName": "last_name",
            "Email": "email",
            "PhoneNumber": "phone",
            "RelationshipType": "relationship",
            "Student_Number": "student_external_id",
            "IsCustodial": "is_primary",
        },
    ),
    "courses.csv": (
        "academics",
        {
            "Course_Number": "subject_code",
            "Course_Name": "subject_name",
            "Credit_Hours": "credits",
            "Department": "department",
        },
    ),
    "sections.csv": (
        "sections",
        {
            "Section_Number": "section_external_id",
            "Course_Number": "subject_code",
            "Teacher": "teacher_external_id",
            "Term": "term",
            "SchoolYear": "academic_year",
        },
    ),
    "enrollments.csv": (
        "enrollment",
        {
            "Student_Number": "student_external_id",
            "Grade_Level": "grade_level",
            "EntryDate": "enrollment_date",
            "ExitDate": "exit_date",
        },
    ),
    "attendance.csv": (
        "attendance",
        {
            "Student_Number": "student_external_id",
            "Att_Date": "date",
            "Att_Code": "status",
            "Period_Number": "period",
            "Comment": "reason",
        },
    ),
    "fees.csv": (
        "finance",
        {
            "Student_Number": "student_external_id",
            "TransactionID": "invoice_number",
            "FeeCategory": "fee_category",
            "Amount": "amount",
            "Currency": "currency",
            "DueDate": "due_date",
            "PaidAmount": "paid_amount",
        },
    ),
}


class PowerSchoolInboundAccelerator(Accelerator):
    source = "powerschool"
    version = "DAT-2025"

    def is_handle_supported(self, handle: Any) -> bool:
        if not isinstance(handle, MigrationBundle):
            return False
        names = set(handle.artifacts.values_list("filename", flat=True))
        return len(names & POWERSCHOOL_FILE_MAP.keys()) >= 2

    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        if not isinstance(handle, MigrationBundle) or handle.pk != bundle_id:
            raise AcceleratorError("PowerSchool accelerator requires the MigrationBundle.")

        contract = AcceleratorContract(bundle_id=bundle_id)
        matched = 0
        for artifact in handle.artifacts.all():
            entry = POWERSCHOOL_FILE_MAP.get(artifact.filename)
            if entry is None:
                continue
            domain, mappings = entry
            contract.pre_classified_artifacts[artifact.path_within_bundle] = {
                "domain": domain,
                "canonical_mappings": dict(mappings),
                "method": "accelerator_powerschool",
            }
            matched += 1

        if matched == 0:
            raise AcceleratorError("PowerSchool accelerator matched no known filenames.")

        # Vendor enum tables → operator sees them in the wizard + transformer attaches them.
        contract.vendor_enum_tables["Enroll_Status"] = {
            "0": "active",
            "1": "active",
            "2": "withdrawn",
            "3": "withdrawn",
            "-1": "inactive",
        }
        contract.vendor_enum_tables["Gender"] = {
            "M": "M",
            "F": "F",
            "U": "X",
            "X": "X",
        }
        contract.vendor_enum_tables["Att_Code"] = {
            "P": "P", "A": "A", "T": "T", "E": "E",
            "Present": "P", "Absent": "A", "Tardy": "T", "Excused": "E",
        }
        contract.notes.append(
            f"Pre-classified {matched} PowerSchool DAT export file(s); "
            "vendor enum tables attached for Enroll_Status / Gender / Att_Code."
        )
        logger.info(
            "migration_cloud.accelerators.powerschool: contract built for bundle %s, files=%d",
            bundle_id, matched,
        )
        return contract


register_accelerator("powerschool", PowerSchoolInboundAccelerator())
