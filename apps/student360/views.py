"""
Student 360 full-page view (Section 26.1).
Permission-gated; uses get_student_360_summary and get_student_timeline_feed.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from .services import get_student_360_summary, get_student_timeline_feed


@login_required
def student_360_page(request, student_id):
    """
    Full Student 360 page: summary + timeline. Requires view permission on the student.
    """
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile
    student = get_object_or_404(StudentProfile, pk=student_id, school=school, is_active=True)
    # Permission: user must be able to view this student (staff or same classroom/role)
    user = request.user
    if not user.is_staff:
        from apps.accounts.permissions import can_view_student_data
        if not can_view_student_data(user, student_id):
            return HttpResponseForbidden("You do not have permission to view this student.")
    summary = get_student_360_summary(school.id, student_id, include_timeline_count=True, include_export_available=True)
    timeline = get_student_timeline_feed(school.id, student_id, limit=50)
    return render(request, "student360/student_360_page.html", {
        "student": student,
        "summary": summary,
        "timeline": timeline,
    })


@login_required
def student_360_export(request, student_id):
    """Permission-gated export pack (JSON) for Student 360."""
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile
    student = get_object_or_404(StudentProfile, pk=student_id, school=school, is_active=True)
    user = request.user
    if not user.is_staff:
        from apps.accounts.permissions import can_view_student_data
        if not can_view_student_data(user, student_id):
            return HttpResponseForbidden("You do not have permission to export this student.")
    from .services import export_student_pack
    import json
    from django.http import HttpResponse
    data = export_student_pack(school.id, student_id, format="json")
    if not data:
        return HttpResponseForbidden("Export not available.")
    response = HttpResponse(json.dumps(data, indent=2, default=str), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="student_360_export_{student_id}.json"'
    return response
