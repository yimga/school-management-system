"""
Parent-tenant (super-tenant) consolidated dashboard (Phase 4).
Users whose school is a parent_school see aggregated stats for child schools.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import render

from .models import School


@login_required
def parent_tenant_dashboard(request):
    """
    Consolidated dashboard for parent-tenant: list child schools with aggregated student/teacher counts.
    Access: user must have request.school or session school_id, and that school must have child_schools.
    """
    school = getattr(request, "school", None)
    if not school and request.session.get("school_id"):
        school = School.objects.filter(
            id=request.session["school_id"], is_active=True
        ).first()
    if not school:
        return HttpResponseForbidden("School context required.")
    child_schools = School.objects.filter(
        parent_school=school, is_active=True
    ).order_by("name")
    if not child_schools.exists():
        return HttpResponseForbidden(
            "This school has no child schools. Parent-tenant dashboard is for parent organizations only."
        )

    from apps.people.models import StudentProfile, TeacherProfile
    from apps.finance.models import Invoice, Payment

    rows = []
    for child in child_schools:
        students = StudentProfile.objects.filter(school=child).count()
        teachers = TeacherProfile.objects.filter(school=child).count()
        invoices = Invoice.objects.filter(school=child).aggregate(t=Sum("total_amount"))
        payments = Payment.objects.filter(school=child).aggregate(t=Sum("amount"))
        rows.append(
            {
                "school": child,
                "student_count": students,
                "teacher_count": teachers,
                "total_invoiced": (invoices.get("t") or 0),
                "total_paid": (payments.get("t") or 0),
            }
        )

    total_students = sum(r["student_count"] for r in rows)
    total_teachers = sum(r["teacher_count"] for r in rows)
    total_invoiced = sum(r["total_invoiced"] for r in rows)
    total_paid = sum(r["total_paid"] for r in rows)

    return render(
        request,
        "schools/parent_tenant_dashboard.html",
        {
            "parent_school": school,
            "child_rows": rows,
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
        },
    )
