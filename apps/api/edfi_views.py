"""Ed-Fi API endpoints: serve Ed-Fi resource shapes from canonical models via mapping layer."""

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.api.rate_limit import throttle_ip_request
from apps.evals.models import Evaluation
from apps.interop.edfi.adapter import (
    evaluation_to_edfi_grade,
    student_school_association_to_edfi,
    student_to_edfi,
)
from apps.people.models import StudentProfile
from apps.schools.models import School

EDFI_RATE_LIMIT_WINDOW = 60 * 15
EDFI_RATE_LIMIT_MAX = 300


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    slug = (
        (request.GET.get("school_slug") or "").strip()
        or (request.headers.get("X-School-Slug") or "").strip()
    )
    if not slug:
        return None
    return School.objects.filter(slug=slug, is_active=True).first()


def _auth_guard(request):
    school = _resolve_school(request)
    if not school:
        return None, JsonResponse({"error": "School context required"}, status=400)
    if not request.user.is_authenticated:
        return None, JsonResponse({"error": "Authentication required"}, status=401)
    if not getattr(request.user, "is_staff", False) and school != getattr(request, "school", None):
        return None, JsonResponse({"error": "Forbidden"}, status=403)
    return school, None


def _edfi_rate_limited(request, scope: str):
    allowed, retry_after = throttle_ip_request(
        request,
        scope=f"edfi:{scope}",
        max_count=EDFI_RATE_LIMIT_MAX,
        window_seconds=EDFI_RATE_LIMIT_WINDOW,
    )
    if allowed:
        return None
    r = JsonResponse({"error": "Too many requests"}, status=429)
    r["Retry-After"] = str(retry_after)
    return r


def _pagination(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0) or 0))
    except ValueError:
        offset = 0
    try:
        limit = int(request.GET.get("limit", 100) or 100)
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 200))
    return offset, limit


@require_GET
def edfi_students(request):
    """GET Ed-Fi shaped students for the school (mapping layer)."""
    rl = _edfi_rate_limited(request, "students")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    qs = StudentProfile.objects.filter(school=school).order_by("pk")[offset : offset + limit]
    for student in qs:
        rows.append(student_to_edfi(student, school))
    return JsonResponse(
        {"students": rows, "pagination": {"offset": offset, "limit": limit, "count": len(rows)}},
        status=200,
    )


@require_GET
def edfi_student_school_associations(request):
    """GET Ed-Fi studentSchoolAssociations for the school."""
    rl = _edfi_rate_limited(request, "associations")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    qs = StudentProfile.objects.filter(school=school).order_by("pk")[offset : offset + limit]
    for student in qs:
        rows.append(student_school_association_to_edfi(student, school))
    return JsonResponse(
        {
            "studentSchoolAssociations": rows,
            "pagination": {"offset": offset, "limit": limit, "count": len(rows)},
        },
        status=200,
    )


@require_GET
def edfi_grades(request):
    """GET Ed-Fi-style grades (from Evaluation) for the school."""
    rl = _edfi_rate_limited(request, "grades")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    qs = (
        Evaluation.objects.filter(school=school)
        .select_related("student", "subject_assignment")
        .order_by("pk")[offset : offset + limit]
    )
    for ev in qs:
        obj = evaluation_to_edfi_grade(ev, school)
        if obj:
            rows.append(obj)
    return JsonResponse(
        {"grades": rows, "pagination": {"offset": offset, "limit": limit, "count": len(rows)}},
        status=200,
    )
