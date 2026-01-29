"""
Services for certification/GCE workflow, including CA marks export.

Handles:
- Technical education Theory/Practical splits
- Coefficient-weighted averages
- Preset-based CA mapping
- Document checklist summaries
"""

from decimal import Decimal
from typing import Dict, List, Optional
from django.db.models import Q, Sum, F
from django.utils import timezone

from apps.academics.models import (
    CertificationExamSession,
    CertificationCandidate,
    CertificationExamPreset,
    CertificationDocumentChecklist,
    CertificationDocumentItem,
    CertificationCandidateDocumentStatus,
    SubjectAssignment,
)
from apps.evals.models import Evaluation
from apps.people.models import StudentProfile


def compute_ca_marks_for_candidate(
    candidate: CertificationCandidate,
    preset: Optional[CertificationExamPreset] = None,
    academic_year=None,
    term=None,
) -> Dict[str, any]:
    """
    Compute CA marks for a candidate based on preset config.
    
    Supports:
    - General education (seq1, seq2, exam)
    - Technical education (Theory + Practical splits)
    - Coefficient-weighted averages
    - Preset-specific subject mapping
    
    Returns dict with:
    - subject_marks: {subject_code: {theory: float, practical: float, total: float, coefficient: float}}
    - total_ca: weighted average
    - general_subtotal: general subjects average
    - technical_subtotal: technical subjects average (if applicable)
    """
    if not academic_year:
        academic_year = candidate.session.academic_year
    if not term:
        from apps.academics.services import get_active_year_and_term
        _, term = get_active_year_and_term()
        if not term:
            return {"error": "No active term"}

    if not preset:
        preset = candidate.session.preset

    student = candidate.student
    if not student.classroom or not student.specialty:
        return {"error": "Student missing classroom/specialty"}

    # Get subject assignments for this student's classroom/specialty
    subject_assignments = SubjectAssignment.objects.filter(
        academic_year=academic_year,
        term=term,
        classroom=student.classroom,
        specialty=student.specialty,
    ).select_related("subject")

    # Get evaluations for this student
    evaluations = Evaluation.objects.filter(
        academic_year=academic_year,
        term=term,
        student=student,
        subject_assignment__in=subject_assignments,
    ).select_related("subject_assignment", "subject_assignment__subject")

    # Preset config for CA calculation
    ca_config = preset.ca_export_config if preset else {}
    use_practical_split = ca_config.get("use_practical_split", False)  # Technical schools
    ca_components = ca_config.get("ca_components", ["seq1", "seq2"])  # Default: seq1 + seq2
    weight_seq1 = ca_config.get("weight_seq1", 50)  # Default 50% each
    weight_seq2 = ca_config.get("weight_seq2", 50)

    subject_marks = {}
    total_weighted_sum = Decimal("0")
    total_coefficient_sum = Decimal("0")
    general_weighted_sum = Decimal("0")
    general_coefficient_sum = Decimal("0")
    technical_weighted_sum = Decimal("0")
    technical_coefficient_sum = Decimal("0")

    for eval_obj in evaluations:
        subject = eval_obj.subject_assignment.subject
        coefficient = Decimal(str(eval_obj.subject_assignment.coefficient or 1.0))
        is_professional = subject.category == "PROFESSIONAL" if hasattr(subject, "category") else False

        # Compute CA from components
        ca_score = None
        theory_score = None
        practical_score = None

        if "seq1" in ca_components and eval_obj.seq1_score is not None:
            seq1_val = Decimal(str(eval_obj.seq1_score))
        else:
            seq1_val = Decimal("0")

        if "seq2" in ca_components and eval_obj.seq2_score is not None:
            seq2_val = Decimal(str(eval_obj.seq2_score))
        else:
            seq2_val = Decimal("0")

        # Calculate CA (weighted average of seq1 and seq2)
        if seq1_val > 0 or seq2_val > 0:
            total_weight = weight_seq1 + weight_seq2
            if total_weight > 0:
                ca_score = (seq1_val * weight_seq1 + seq2_val * weight_seq2) / total_weight
            else:
                ca_score = (seq1_val + seq2_val) / 2 if (seq1_val + seq2_val) > 0 else None

        # For technical schools: separate Theory and Practical
        if use_practical_split:
            theory_score = ca_score  # CA is theory component
            if eval_obj.practical_score is not None:
                practical_score = Decimal(str(eval_obj.practical_score))
                # Combined score: (Theory * theory_weight + Practical * practical_weight) / total_weight
                theory_weight = ca_config.get("theory_weight", 60)
                practical_weight = ca_config.get("practical_weight", 40)
                total_weight_tp = theory_weight + practical_weight
                if total_weight_tp > 0:
                    ca_score = (theory_score * theory_weight + practical_score * practical_weight) / total_weight_tp

        if ca_score is None:
            continue

        subject_marks[subject.code if hasattr(subject, "code") else subject.name] = {
            "subject_name": subject.name,
            "theory": float(theory_score) if theory_score else None,
            "practical": float(practical_score) if practical_score else None,
            "total": float(ca_score),
            "coefficient": float(coefficient),
        }

        # Accumulate for totals
        weighted_value = ca_score * coefficient
        total_weighted_sum += weighted_value
        total_coefficient_sum += coefficient

        if is_professional:
            technical_weighted_sum += weighted_value
            technical_coefficient_sum += coefficient
        else:
            general_weighted_sum += weighted_value
            general_coefficient_sum += coefficient

    # Calculate totals
    total_ca = float(total_weighted_sum / total_coefficient_sum) if total_coefficient_sum > 0 else None
    general_subtotal = float(general_weighted_sum / general_coefficient_sum) if general_coefficient_sum > 0 else None
    technical_subtotal = float(technical_weighted_sum / technical_coefficient_sum) if technical_coefficient_sum > 0 else None

    return {
        "subject_marks": subject_marks,
        "total_ca": total_ca,
        "general_subtotal": general_subtotal,
        "technical_subtotal": technical_subtotal,
        "use_practical_split": use_practical_split,
    }


def get_document_checklist_summary(candidate: CertificationCandidate) -> Dict[str, any]:
    """
    Get document checklist completion status for a candidate.
    
    Returns:
    - total_items: int
    - required_items: int
    - completed_items: int
    - missing_items: List[dict]
    - status_by_item: Dict[item_code: status]
    """
    session = candidate.session
    checklist = session.document_checklist
    if not checklist:
        if session.preset:
            checklist = session.preset.document_checklists.filter(is_default_for_preset=True).first()
    
    if not checklist:
        return {
            "total_items": 0,
            "required_items": 0,
            "completed_items": 0,
            "missing_items": [],
            "status_by_item": {},
        }

    items = checklist.items.all()
    statuses = CertificationCandidateDocumentStatus.objects.filter(
        candidate=candidate,
        item__in=items,
    ).select_related("item")

    status_by_item = {s.item.code: s.status for s in statuses}
    required_items = items.filter(required=True).count()
    completed_items = sum(
        1 for s in statuses
        if s.status in ["RECEIVED", "VERIFIED", "WAIVED"]
    )
    missing_items = [
        {
            "code": item.code,
            "label": item.label,
            "required": item.required,
        }
        for item in items
        if item.code not in status_by_item or status_by_item[item.code] == "MISSING"
    ]

    return {
        "total_items": items.count(),
        "required_items": required_items,
        "completed_items": completed_items,
        "missing_items": missing_items,
        "status_by_item": status_by_item,
    }
