"""API and views for benchmark comparison (Phase 4)."""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.analytics.models import BenchmarkAggregate


class BenchmarkComparisonAPI(APIView):
    """
    GET: return comparison of current school's subject averages vs regional benchmark.
    Example: "Your Mathematics average is 12% above regional average for EN this term."
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = getattr(request, "school", None)
        if not school:
            return Response({"comparisons": [], "message": "School context required."})
        region_code = getattr(school.default_region, "code", "GLOBAL") if school.default_region else "GLOBAL"
        sub_system = getattr(school, "sub_system", "EN") or "EN"

        from django.db.models import Avg
        from apps.evals.models import Evaluation
        from apps.academics.models import SubjectAssignment

        # School's averages per subject/term (current term or all)
        school_avgs = (
            Evaluation.objects.filter(
                subject_assignment__school=school,
                subject_assignment__academic_year__is_active=True,
            )
            .values("subject_assignment__subject_id", "subject_assignment__term_id", "subject_assignment__academic_year_id")
            .annotate(avg=Avg("final_score"))
        )
        comparisons = []
        for row in school_avgs:
            subject_id = row.get("subject_assignment__subject_id")
            term_id = row.get("subject_assignment__term_id")
            ay_id = row.get("subject_assignment__academic_year_id")
            school_avg = row.get("avg")
            if school_avg is None:
                continue
            bench = BenchmarkAggregate.objects.filter(
                region_code=region_code,
                sub_system=sub_system,
                subject_id=subject_id,
                term_id=term_id,
                academic_year_id=ay_id,
                metric="average_score",
            ).first()
            if not bench or bench.value is None:
                comparisons.append({
                    "subject_id": subject_id,
                    "term_id": term_id,
                    "school_avg": float(school_avg),
                    "regional_avg": None,
                    "diff_percent": None,
                    "message": "No regional benchmark yet.",
                })
                continue
            regional_avg = float(bench.value)
            diff = float(school_avg) - regional_avg
            diff_percent = (diff / regional_avg * 100) if regional_avg else None
            comparisons.append({
                "subject_id": subject_id,
                "term_id": term_id,
                "school_avg": float(school_avg),
                "regional_avg": regional_avg,
                "diff_percent": round(diff_percent, 1) if diff_percent is not None else None,
                "message": (f"Your average is {diff_percent:+.1f}% vs regional average." if diff_percent is not None else None),
            })
        return Response({"comparisons": comparisons})
