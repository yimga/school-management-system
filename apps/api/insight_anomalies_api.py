"""JSON API for insight anomaly cards (dashboard + future mobile)."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods


@method_decorator(login_required, name="dispatch")
@method_decorator(require_http_methods(["GET"]), name="dispatch")
class InsightAnomaliesAPIView(View):
    def get(self, request):
        school = getattr(request, "school", None)
        if not school:
            return JsonResponse({"anomalies": []})
        try:
            from apps.dashboard.services.insight_anomalies import (
                build_insight_anomaly_cards,
            )

            return JsonResponse(
                {"anomalies": build_insight_anomaly_cards(request, limit=12)}
            )
        except Exception:
            return JsonResponse({"anomalies": []})
