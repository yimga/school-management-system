"""
Rosetta Stone API: cross-tenant / cross-system grade conversion.

Frictionless global student mobility: convert a grade from one scale (e.g. 16/20 Francophone)
to another (e.g. US GPA 3.2 / B+) using normalized 0.0-1.0 anchor.
"""

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from apps.api.deprecation import DeprecationHeaderViewMixin


@method_decorator(login_required, name="dispatch")
class RosettaStoneConvertAPI(DeprecationHeaderViewMixin, View):
    """
    GET ?score=<number>&from_scale=<id>&to_scale=<id>
    If from_scale is omitted, uses request.school's tenant scale.
    Returns: converted_score, normalized_value, letter_grade (when applicable).

    DEPRECATED (RFC 8594) — superseded by ``/api/v1/rosetta/convert``. Emits
    ``Deprecation`` / ``Sunset`` / ``Link`` headers; see ``apps/api/deprecation.py``.
    """

    deprecation_endpoint_id = "api.rosetta.convert"

    def get(self, request):
        school = getattr(request, "school", None)
        score_str = request.GET.get("score")
        from_scale = request.GET.get("from_scale") or None
        to_scale = request.GET.get("to_scale") or "0-20"

        if not score_str:
            return JsonResponse(
                {"error": "Missing 'score' query parameter"}, status=400
            )
        try:
            score = float(score_str)
        except ValueError:
            return JsonResponse(
                {"error": "Invalid 'score': must be a number"}, status=400
            )

        try:
            from apps.evals.rosetta_stone import convert_grade

            result = convert_grade(
                score=score, from_scale=from_scale, to_scale=to_scale, school=school
            )
            return JsonResponse(result)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)


@method_decorator(login_required, name="dispatch")
class RosettaStoneScalesAPI(DeprecationHeaderViewMixin, View):
    """GET: list of supported scale ids for conversion (0-20, 0-100, gpa, a-f, 0-10).

    DEPRECATED (RFC 8594) — superseded by ``/api/v1/rosetta/scales``. Emits
    ``Deprecation`` / ``Sunset`` / ``Link`` headers; see ``apps/api/deprecation.py``.
    """

    deprecation_endpoint_id = "api.rosetta.scales"

    def get(self, request):
        from apps.evals.rosetta_stone import get_supported_scales

        return JsonResponse({"scales": get_supported_scales()})
