"""
Admissions CRM (Phase 5): Lead Capture API.
Public POST by school_slug (or subdomain); creates Applicant. Rate-limit and validate.
"""
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator

from apps.schools.models import School
from apps.people.models import Applicant


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class LeadCaptureAPI(View):
    """
    POST body (JSON): school_slug, first_name, last_name, email, lead_source (optional).
    Resolves school by slug; creates Applicant. Duplicate check by (email, school).
    """

    def post(self, request):
        import json
        try:
            body = json.loads(request.body) if request.body else {}
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        school_slug = (body.get("school_slug") or "").strip() or request.GET.get("school_slug", "").strip()
        if not school_slug:
            return JsonResponse({"error": "school_slug required"}, status=400)
        school = School.objects.filter(slug=school_slug, is_active=True).first()
        if not school:
            return JsonResponse({"error": "School not found"}, status=404)
        first_name = (body.get("first_name") or "").strip()
        last_name = (body.get("last_name") or "").strip()
        email = (body.get("email") or "").strip()
        if not email or not (first_name or last_name):
            return JsonResponse({"error": "first_name, last_name, and email required"}, status=400)
        existing = Applicant.objects.filter(school=school, email=email).first()
        if existing:
            return JsonResponse({
                "ok": True,
                "applicant_id": existing.pk,
                "message": "Applicant already exists for this school/email",
            }, status=200)
        applicant = Applicant.objects.create(
            school=school,
            first_name=first_name or "—",
            last_name=last_name or "—",
            email=email,
            lead_source=(body.get("lead_source") or "").strip() or "api",
            stage=Applicant.Stage.LEAD,
            extra_data=body.get("extra_data") or {},
        )
        return JsonResponse({"ok": True, "applicant_id": applicant.pk}, status=201)
