"""
Config diff API (Section 29.4): compare effective policy/settings between contexts.
Staff or config_diff capability required.
"""

from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class ConfigDiffAPI(View):
    """
    GET /api/config-diff/?base=current&compare=staged
    Or ?school_id=X&compare_school_id=Y to compare two schools' effective policy (key-level diff).
    """

    def get(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return JsonResponse({"detail": "Authentication required."}, status=401)
        if not (user.is_superuser or getattr(user, "is_staff", False)):
            school = getattr(request, "school", None)
            if not school:
                return JsonResponse({"detail": "Forbidden."}, status=403)
            from apps.schools.models import can

            if not can(school, "CONFIG_DIFF"):
                return JsonResponse({"detail": "Forbidden."}, status=403)

        school_id = request.GET.get("school_id")
        compare_school_id = request.GET.get("compare_school_id")
        from apps.policies.policy_registry import get_effective_policy
        from apps.schools.models import School

        def _safe_policy(s):
            if s is None:
                return {}
            p = get_effective_policy(s)
            # Redact keys that might hold secrets (top-level only)
            out = {}
            for k, v in p.items():
                if k == "payment_gateways" and isinstance(v, dict):
                    out[k] = {
                        kk: "***" if "secret" in str(vv).lower() else vv
                        for kk, vv in v.items()
                    }
                else:
                    out[k] = v
            return out

        base_policy = {}
        compare_policy = {}
        if school_id and compare_school_id:
            try:
                school_a = School.objects.get(pk=school_id)
                school_b = School.objects.get(pk=compare_school_id)
                base_policy = _safe_policy(school_a)
                compare_policy = _safe_policy(school_b)
            except School.DoesNotExist:
                return JsonResponse({"detail": "School not found."}, status=404)
        else:
            school = getattr(request, "school", None)
            if school:
                base_policy = _safe_policy(school)
            compare_policy = {}

        # Simple key-level diff (no deep diff)
        all_keys = set(base_policy) | set(compare_policy)
        diff = {}
        for k in all_keys:
            v1 = base_policy.get(k)
            v2 = compare_policy.get(k)
            if v1 != v2:
                diff[k] = {"base": v1 is not None, "compare": v2 is not None}
        return JsonResponse({"diff_keys": diff, "schema_version": "1.0"})
