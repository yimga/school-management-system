from apps.reports.models import TermPublishStatus

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

