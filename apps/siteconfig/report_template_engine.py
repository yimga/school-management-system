"""
Official report template engine: inject data into uploadable HTML templates (Phase 2).
Placeholders: {{ student_name }}, {{ grades }}, etc. Produces HTML; optional PDF via WeasyPrint.
"""
from django.template import Context, Template
from django.template.exceptions import TemplateSyntaxError


def render_official_template_html(template_content: str, context: dict) -> str:
    """
    Replace {{ key }} placeholders in template_content with context values.
    Supports nested keys via dot: {{ student.first_name }} (flattened in context as student_first_name or pass nested dicts).
    """
    if not template_content:
        return ""
    # Django-style {{ variable }} substitution
    try:
        t = Template(template_content)
        ctx = Context(context)
        return t.render(ctx)
    except (TemplateSyntaxError, KeyError, ValueError, TypeError, AttributeError):
        pass
    # Fallback: simple {{ key }} replace
    out = template_content
    for key, value in context.items():
        if value is None:
            value = ""
        if isinstance(value, (dict, list)):
            continue
        out = out.replace("{{ " + key + " }}", str(value))
        out = out.replace("{{ " + key + "}}", str(value))
        out = out.replace("{{" + key + " }}", str(value))
        out = out.replace("{{" + key + "}}", str(value))
    return out


def get_report_context_for_student(student, term=None, academic_year=None, school=None):
    """Build a minimal context dict for report template injection (extend as needed)."""
    from apps.evals.models import Evaluation
    context = {
        "school_name": getattr(school, "name", "") if school else "",
        "student_name": f"{getattr(student, 'first_name', '')} {getattr(student, 'last_name', '')}".strip() or str(student),
        "student_code": getattr(student, "student_code", "") or getattr(student, "id", ""),
        "term": getattr(term, "name", "") if term else "",
        "academic_year": getattr(academic_year, "name", "") if academic_year else "",
    }
    if term and academic_year:
        evals = Evaluation.objects.filter(
            student=student,
            subject_assignment__term=term,
            subject_assignment__academic_year=academic_year,
        ).select_related("subject_assignment__subject")
        grades_list = [f"{e.subject_assignment.subject.name}: {e.score}" for e in evals]
        context["grades"] = "; ".join(grades_list)
        context["grades_list"] = grades_list
    return context
