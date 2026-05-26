"""Wave O (v3.95.0 — 2026-05-26) — University application pathway registry.

The competitive gap: a senior-year sticky moat. Students whose RMC record
generates their UCAS / Common App / WAEC / IB / Joint Admissions package
have a hard-to-break dependency. Schools that "export to UCAS in one click"
out-bid manual transcript schools.

This module declares the **pathway specs** — what fields each major university
application platform requires, in what format, with what supporting
documents. The actual export adapters land in Wave O+1 once we have
counsel-signed agreements with each platform.

For now this is a **read-only registry** that drives:
- The Student360 "Pathway" tab UI (which exports the student is eligible for).
- The pre-submission "completeness check" (do we have all the required data?).
- The migration adapter (export shape for white-glove partner integrations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FieldRequirement:
    field_name: str  # canonical RMC field path, e.g. "student.gpa_cumulative"
    required: bool
    notes: str = ""


@dataclass(frozen=True)
class DocumentRequirement:
    doc_id: str
    display_name: str
    required: bool
    file_types: tuple[str, ...] = ("pdf",)


@dataclass(frozen=True)
class UniversityPathway:
    pathway_id: str
    display_name: str
    region: str  # "UK", "US", "Global-IB", "Nigeria", "India", "Kenya", etc.
    submission_window_months: tuple[int, ...]
    transcript_format: str  # "official_sealed_pdf" / "ucas_xml" / "common_app_json"
    fields_required: tuple[FieldRequirement, ...]
    documents_required: tuple[DocumentRequirement, ...]
    fee_amount_minor: int = 0
    fee_currency: str = ""
    docs_url: str = ""
    notes: str = ""


_REGISTRY: dict[str, UniversityPathway] = {}


def register_pathway(p: UniversityPathway) -> None:
    _REGISTRY[p.pathway_id] = p


def get_pathway(pathway_id: str) -> UniversityPathway | None:
    return _REGISTRY.get(pathway_id)


def list_pathways() -> tuple[UniversityPathway, ...]:
    return tuple(_REGISTRY.values())


def pathways_for_region(region: str) -> tuple[UniversityPathway, ...]:
    r = (region or "").strip()
    return tuple(p for p in _REGISTRY.values() if p.region == r)


def clear_registry_for_tests() -> None:
    _REGISTRY.clear()


# ---------------------------------------------------------------------------
# Completeness checker
# ---------------------------------------------------------------------------

@dataclass
class CompletenessReport:
    pathway_id: str
    ready: bool
    missing_fields: list[str] = field(default_factory=list)
    missing_documents: list[str] = field(default_factory=list)


def check_completeness(
    pathway: UniversityPathway,
    *,
    field_value_resolver,
    document_present_resolver,
) -> CompletenessReport:
    """Run a completeness check for a student against a pathway.

    ``field_value_resolver(field_name) -> Any`` returns the value at that
    canonical RMC field path. Truthy means "present"; falsy means missing.

    ``document_present_resolver(doc_id) -> bool`` returns whether the
    document is uploaded.

    Optional fields don't block readiness. The caller is responsible for
    tenant-scoped resolvers (this module performs no I/O).
    """
    rep = CompletenessReport(pathway_id=pathway.pathway_id, ready=True)
    for fr in pathway.fields_required:
        if not fr.required:
            continue
        try:
            val = field_value_resolver(fr.field_name)
        except Exception:  # noqa: BLE001
            val = None
        if not val:
            rep.missing_fields.append(fr.field_name)
    for dr in pathway.documents_required:
        if not dr.required:
            continue
        try:
            present = bool(document_present_resolver(dr.doc_id))
        except Exception:  # noqa: BLE001
            present = False
        if not present:
            rep.missing_documents.append(dr.doc_id)
    rep.ready = not (rep.missing_fields or rep.missing_documents)
    return rep


# ---------------------------------------------------------------------------
# Seeded pathways
# ---------------------------------------------------------------------------

def _seed_pathways() -> None:
    register_pathway(UniversityPathway(
        pathway_id="ucas-uk",
        display_name="UCAS (UK Undergraduate)",
        region="UK",
        submission_window_months=(9, 10, 11, 12, 1),
        transcript_format="ucas_xml",
        fields_required=(
            FieldRequirement("student.full_name", True),
            FieldRequirement("student.date_of_birth", True),
            FieldRequirement("student.nationality", True),
            FieldRequirement("student.address", True),
            FieldRequirement("student.gcse_results", True,
                              "Required: predicted A-level grades + actual GCSE results."),
            FieldRequirement("student.a_level_predicted_grades", True),
            FieldRequirement("student.personal_statement", True,
                              "Max 4,000 chars / 47 lines."),
            FieldRequirement("school.buzzword", True,
                              "UCAS centre 'buzzword' (school-issued)."),
            FieldRequirement("teacher.reference_writer", True),
        ),
        documents_required=(
            DocumentRequirement("transcript_official", "Official transcript", True),
            DocumentRequirement("teacher_reference", "Teacher reference letter", True),
            DocumentRequirement("passport_scan", "Passport (international students)", False),
        ),
        fee_amount_minor=2850,  # £28.50 for 2026 cycle
        fee_currency="GBP",
        notes="Window is one-off per year; late entries after Jan 26 deadline trigger Extra/Clearing.",
    ))

    register_pathway(UniversityPathway(
        pathway_id="common-app-us",
        display_name="Common Application (US Undergraduate)",
        region="US",
        submission_window_months=(8, 9, 10, 11, 12, 1, 2),
        transcript_format="common_app_json",
        fields_required=(
            FieldRequirement("student.full_name", True),
            FieldRequirement("student.date_of_birth", True),
            FieldRequirement("student.address", True),
            FieldRequirement("student.high_school_gpa", True),
            FieldRequirement("student.sat_act_scores", False,
                              "Many institutions are now test-optional."),
            FieldRequirement("student.essay_common_app", True,
                              "Max 650 words; one of 7 prompts."),
            FieldRequirement("student.activities_list", True,
                              "Up to 10 activities; 50/150 char descriptions."),
            FieldRequirement("student.honors_awards", False),
            FieldRequirement("counselor.recommendation", True),
        ),
        documents_required=(
            DocumentRequirement("transcript_official", "Official sealed transcript", True),
            DocumentRequirement("counselor_letter", "Counselor recommendation", True),
            DocumentRequirement("teacher_letter_1", "Teacher recommendation #1", True),
            DocumentRequirement("teacher_letter_2", "Teacher recommendation #2", False),
            DocumentRequirement("midyear_report", "Mid-year report", True),
        ),
        fee_amount_minor=0,
        fee_currency="USD",
        notes="Per-college fees billed at the college side; Common App itself is free.",
    ))

    register_pathway(UniversityPathway(
        pathway_id="ib-dp-result-release",
        display_name="IB Diploma — Final Results Release",
        region="Global-IB",
        submission_window_months=(7,),  # July results
        transcript_format="ib_official_release",
        fields_required=(
            FieldRequirement("student.ib_candidate_number", True),
            FieldRequirement("student.ib_dp_subjects", True),
            FieldRequirement("student.ib_ee_subject", True),
            FieldRequirement("student.ib_cas_completion", True),
        ),
        documents_required=(
            DocumentRequirement("ib_predicted_grades", "Predicted grades sheet", True),
            DocumentRequirement("ee_signed_copy", "Extended Essay (signed)", True),
            DocumentRequirement("tok_essay", "Theory of Knowledge essay", True),
        ),
        fee_amount_minor=0,
        fee_currency="",
        notes="Results are released directly by IBO to candidate; school issues the predicted grades + IA marks.",
    ))

    register_pathway(UniversityPathway(
        pathway_id="waec-nigeria",
        display_name="WAEC SSCE (Nigeria / West Africa)",
        region="Nigeria",
        submission_window_months=(1, 2, 3, 4),
        transcript_format="waec_csv_batch",
        fields_required=(
            FieldRequirement("student.full_name", True),
            FieldRequirement("student.date_of_birth", True),
            FieldRequirement("student.examination_number", True),
            FieldRequirement("student.subjects_registered", True,
                              "Must register minimum 8, maximum 9 subjects."),
            FieldRequirement("student.guardian_consent", True),
        ),
        documents_required=(
            DocumentRequirement("passport_photo", "Passport photo (recent)", True),
            DocumentRequirement("birth_certificate", "Birth certificate / age affidavit", True),
            DocumentRequirement("registration_fee_receipt", "Registration fee receipt", True),
        ),
        fee_amount_minor=2750000,  # ₦27,500 for 2026
        fee_currency="NGN",
    ))

    register_pathway(UniversityPathway(
        pathway_id="jamb-utme-nigeria",
        display_name="JAMB UTME (Nigeria)",
        region="Nigeria",
        submission_window_months=(1, 2, 3),
        transcript_format="jamb_csv_batch",
        fields_required=(
            FieldRequirement("student.full_name", True),
            FieldRequirement("student.date_of_birth", True),
            FieldRequirement("student.nin_number", True,
                              "National Identification Number required for JAMB."),
            FieldRequirement("student.utme_subject_combination", True,
                              "4 subjects including English."),
            FieldRequirement("student.first_choice_university", True),
            FieldRequirement("student.first_choice_course", True),
        ),
        documents_required=(
            DocumentRequirement("passport_photo", "Passport photo", True),
            DocumentRequirement("nin_slip", "NIN slip / printout", True),
        ),
        fee_amount_minor=470000,  # ₦4,700
        fee_currency="NGN",
    ))

    register_pathway(UniversityPathway(
        pathway_id="cuet-india",
        display_name="CUET (Common University Entrance Test, India)",
        region="India",
        submission_window_months=(3, 4),
        transcript_format="cuet_csv_batch",
        fields_required=(
            FieldRequirement("student.full_name", True),
            FieldRequirement("student.date_of_birth", True),
            FieldRequirement("student.aadhaar_number", True),
            FieldRequirement("student.cuet_test_subjects", True,
                              "Up to 6 domain subjects + language + general aptitude."),
            FieldRequirement("student.class_12_predicted", True),
        ),
        documents_required=(
            DocumentRequirement("passport_photo", "Passport photo", True),
            DocumentRequirement("aadhaar_scan", "Aadhaar card scan", True),
            DocumentRequirement("class_10_marksheet", "Class 10 marksheet", True),
        ),
        fee_amount_minor=85000,  # ₹850 (general)
        fee_currency="INR",
    ))

    register_pathway(UniversityPathway(
        pathway_id="kuccps-kenya",
        display_name="KUCCPS (Kenya University & College Central Placement Service)",
        region="Kenya",
        submission_window_months=(5, 6),
        transcript_format="kuccps_csv_batch",
        fields_required=(
            FieldRequirement("student.full_name", True),
            FieldRequirement("student.kcse_index_number", True),
            FieldRequirement("student.kcse_subjects", True,
                              "7 subjects including English + Maths + Kiswahili."),
            FieldRequirement("student.first_choice_program", True),
        ),
        documents_required=(
            DocumentRequirement("kcse_result_slip", "KCSE result slip", True),
            DocumentRequirement("birth_certificate", "Birth certificate", True),
        ),
        fee_amount_minor=150000,  # KES 1500
        fee_currency="KES",
    ))


_seed_pathways()


# ---------------------------------------------------------------------------
# Public summary
# ---------------------------------------------------------------------------

def summary() -> dict[str, Any]:
    pathways = list_pathways()
    return {
        "pathway_count": len(pathways),
        "by_region": {
            region: sum(1 for p in pathways if p.region == region)
            for region in {p.region for p in pathways}
        },
        "total_fields_tracked": sum(len(p.fields_required) for p in pathways),
        "total_documents_tracked": sum(len(p.documents_required) for p in pathways),
    }
