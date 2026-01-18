from apps.reports.models import TermPublishStatus, PromotionRule

def is_term_published(academic_year_id: int, term_id: int, classroom_id: int) -> bool:
    """
    Published if either:
    - whole-school publish exists, OR
    - class-level publish exists
    """
    school_pub = TermPublishStatus.objects.filter(
        academic_year_id=academic_year_id,
        term_id=term_id,
        classroom__isnull=True,
        is_published=True,
    ).exists()

    class_pub = TermPublishStatus.objects.filter(
        academic_year_id=academic_year_id,
        term_id=term_id,
        classroom_id=classroom_id,
        is_published=True,
    ).exists()

    return school_pub or class_pub


def get_promotion_status(student, academic_year, overall_average):
    if overall_average is None:
        return "NO_DATA"

    rule = PromotionRule.objects.filter(
        academic_year=academic_year,
        classroom=student.classroom,
    ).first()
    if not rule:
        rule = PromotionRule.objects.filter(academic_year=academic_year, classroom__isnull=True).first()

    if not rule:
        return "PENDING"

    avg = float(overall_average)
    if avg >= float(rule.promotion_average):
        return "PROMOTED"
    if avg < float(rule.demotion_average):
        return "DEMOTED"
    return "REPEAT"
