# -*- coding: utf-8 -*-
"""Student passport + transcript vault (read-only operator pages, North Star SLICE 13)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.people.passport_services import (
    get_or_create_passport_for_student,
    list_visible_vault_items,
)
from apps.people.student_passport_models import StudentPassportMembership
from apps.schools.hierarchy_helpers import scoped_schools_for_user


def _staff_may_view_student(request: HttpRequest, student: StudentProfile) -> bool:
    if not request.user.is_authenticated:
        return False
    u = request.user
    if getattr(u, "is_superuser", False):
        return True
    if not getattr(request, "school", None) or student.school_id != request.school.pk:
        return False
    role = (getattr(u, "role", "") or "").upper()
    return role in {
        User.Role.ADMIN,
        User.Role.LEADERSHIP,
        User.Role.PRINCIPAL,
        User.Role.ACADEMICS_STAFF,
        User.Role.TEACHER,
        User.Role.SUPERADMIN,
    }


@login_required
@require_http_methods(["GET"])
def student_passport_detail(request: HttpRequest, student_profile_id: int) -> HttpResponse:
    student = get_object_or_404(StudentProfile.objects.select_related("school"), pk=student_profile_id)
    if not _staff_may_view_student(request, student):
        return HttpResponseForbidden("Forbidden.")

    passport, _created = get_or_create_passport_for_student(student, request.user)
    if getattr(request.user, "is_superuser", False):
        memberships_qs = StudentPassportMembership.objects.filter(passport=passport)
    else:
        scoped_ids = list(
            scoped_schools_for_user(request.user, root_school=getattr(request, "school", None)).values_list(
                "pk", flat=True
            )
        )
        memberships_qs = StudentPassportMembership.objects.filter(
            passport=passport, school_id__in=scoped_ids or [-1]
        )
    memberships = memberships_qs.select_related("school", "student_profile")

    student360_url = None
    transcript_vault_url = None
    try:
        student360_url = reverse("portal:student_360_page", kwargs={"student_id": student.pk})
    except NoReverseMatch:
        pass
    try:
        transcript_vault_url = reverse(
            "portal:student_transcript_vault",
            kwargs={"student_profile_id": student.pk},
        )
    except NoReverseMatch:
        pass

    return render(
        request,
        "portal/student_passport_detail.html",
        {
            "student": student,
            "passport": passport,
            "memberships": memberships,
            "student360_url": student360_url,
            "transcript_vault_url": transcript_vault_url,
        },
    )


@login_required
@require_http_methods(["GET"])
def student_transcript_vault(request: HttpRequest, student_profile_id: int) -> HttpResponse:
    student = get_object_or_404(StudentProfile.objects.select_related("school"), pk=student_profile_id)
    if not _staff_may_view_student(request, student):
        return HttpResponseForbidden("Forbidden.")

    passport, _ = get_or_create_passport_for_student(student, request.user)
    school = getattr(request, "school", None)
    vault_items = list_visible_vault_items(
        request.user, passport, school=school if school else student.school
    )

    student360_url = None
    passport_url = None
    try:
        student360_url = reverse("portal:student_360_page", kwargs={"student_id": student.pk})
    except NoReverseMatch:
        pass
    try:
        passport_url = reverse(
            "portal:student_passport_detail",
            kwargs={"student_profile_id": student.pk},
        )
    except NoReverseMatch:
        pass

    return render(
        request,
        "portal/student_transcript_vault.html",
        {
            "student": student,
            "passport": passport,
            "vault_items": vault_items,
            "student360_url": student360_url,
            "passport_url": passport_url,
        },
    )
