"""
Quick, query-friendly mark completion stats.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps


def completion_by_class(academic_year=None):
    """
    Returns a dict keyed by classroom id with completion %, using Evaluation rows.
    """
    Evaluation = django_apps.get_model("evals", "Evaluation")
    django_apps.get_model("academics", "SubjectAssignment")

    qs = Evaluation.objects.all().select_related("student__classroom")
    if academic_year:
        qs = qs.filter(academic_year=academic_year)

    totals = defaultdict(int)
    completed = defaultdict(int)

    for eval_obj in qs.iterator():
        classroom_id = getattr(eval_obj.student.classroom, "id", None)
        if not classroom_id:
            continue
        totals[classroom_id] += 1
        if (
            eval_obj.is_complete_for_ranking
            if hasattr(eval_obj, "is_complete_for_ranking")
            else True
        ):
            completed[classroom_id] += 1

    return {
        class_id: {
            "total": totals[class_id],
            "completed": completed[class_id],
            "percent": int(round((completed[class_id] / totals[class_id]) * 100))
            if totals[class_id]
            else 0,
        }
        for class_id in totals
    }
