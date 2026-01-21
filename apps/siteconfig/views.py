# -*- coding: utf-8 -*-

import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.academics.services import get_active_year_and_term
from apps.people.models import StudentProfile
from apps.reports.services import term_report_context

from types import SimpleNamespace

from .forms import (
    ReportCardStyleAssignmentForm,
    ReportCardStyleForm,
    ReportCardStyleSelectionForm,
    UserPreferenceForm,
)
from .models import (
    ReportCardStyle,
    ReportCardStyleAssignment,
    ReportTemplate,
    SiteSettings,
    ThemePack,
    UserPreference,
)
from apps.accounts.decorators import permission_required

CACHE_KEY = "site_settings_v1"
SESSION_KEY = "site_preview_settings"


def maintenance_view(request):
    return render(request, "siteconfig/maintenance.html")


@permission_required("settings.manage")
def customizer(request):
    settings_obj = SiteSettings.get_solo()
    messages.info(
        request,
        "Customizer now lives inside Site Settings (admin-only) and Preferences (staff).",
    )
    theme_packs = ThemePack.objects.filter(is_active=True).order_by("-is_default", "name")
    return render(request, "siteconfig/customizer.html", {
        "settings": settings_obj,
        "site_settings_url": reverse("admin:siteconfig_sitesettings_change", args=(settings_obj.pk,)),
        "preferences_url": reverse("siteconfig:user_preferences"),
        "theme_packs": theme_packs,
    })

@permission_required("settings.manage")
def reportcard_builder(request):
    settings_obj = SiteSettings.get_solo()
    styles = ReportCardStyle.objects.order_by("name")
    assignments = (
        ReportCardStyleAssignment.objects
        .select_related("classroom", "style")
        .order_by("classroom__name")
    )
    style_form = ReportCardStyleForm(request.POST or None, prefix="style")
    assignment_form = ReportCardStyleAssignmentForm(request.POST or None, prefix="assign")
    selection_form = ReportCardStyleSelectionForm(
        request.POST or None,
        prefix="selection",
        instance=settings_obj,
    )

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "style" and style_form.is_valid():
            style_form.save()
            messages.success(request, "Report card style saved.")
            return redirect("siteconfig:reportcard_builder")
        if form_type == "assignment" and assignment_form.is_valid():
            assignment_form.save()
            messages.success(request, "Style assignments updated.")
            return redirect("siteconfig:reportcard_builder")
        if form_type == "selection" and selection_form.is_valid():
            selection_form.save()
            messages.success(request, "Default styles saved.")
            return redirect("siteconfig:reportcard_builder")

    return render(request, "siteconfig/reportcard_builder.html", {
        "settings": settings_obj,
        "styles": styles,
        "assignments": assignments,
        "style_form": style_form,
        "assignment_form": assignment_form,
        "selection_form": selection_form,
    })

def _build_style_metadata(site: SiteSettings) -> dict:
    return {
        "school_name": site.site_name,
        "school_code": site.school_code,
        "country": site.country,
        "region": site.region,
        "ministry": site.ministry,
        "tagline": site.tagline,
    }


class _PreviewTerm(SimpleNamespace):
    def get_name_display(self):
        return getattr(self, "name", "First term")


@permission_required("settings.manage")
def reportcard_style_preview(request, slug: str):
    style = get_object_or_404(ReportCardStyle, slug=slug)
    site = SiteSettings.get_solo()
    year, term = get_active_year_and_term()
    student = StudentProfile.objects.filter(is_active=True).select_related("classroom", "specialty").first()
    metadata = _build_style_metadata(site)

    if student and year and term:
        base_ctx = term_report_context(student, year, term)
        rows = base_ctx["rows"][:6]
        summary = base_ctx["summary"]
        weights = base_ctx["weights"]
        student_obj = student
        student_name = f"{student.last_name} {student.first_name}"
        year_obj = year
        term_obj = term
    else:
        student_obj = SimpleNamespace(
            last_name="Sample",
            first_name="Learner",
            classroom=SimpleNamespace(name="Form One"),
            specialty=SimpleNamespace(name="Carpentry"),
            student_code="00SAMPLE",
        )
        student_name = f"{student_obj.last_name} {student_obj.first_name}"
        year_obj = SimpleNamespace(name="2025/2026")
        term_obj = _PreviewTerm(name="First Term")
        rows = [
            {"subject": "English", "coef": 2, "seq1": 12.0, "seq2": 13.5, "exam": 14.0, "mock": 0, "practical": 0, "total": 13.25, "remark": "Very good", "complete": True},
            {"subject": "Mathematics", "coef": 4, "seq1": 11.0, "seq2": 12.0, "exam": 15.5, "mock": 0, "practical": 0, "total": 13.74, "remark": "Excellent", "complete": True},
            {"subject": "Physics", "coef": 3, "seq1": 10.0, "seq2": 11.0, "exam": 12.0, "mock": 0, "practical": 0, "total": 11.66, "remark": "Solid", "complete": True},
            {"subject": "Technical Drawing", "coef": 2, "seq1": 9.0, "seq2": 10.5, "exam": 11.0, "mock": 0, "practical": 0, "total": 10.19, "remark": "Improving", "complete": True},
            {"subject": "ICT", "coef": 1, "seq1": 13.0, "seq2": 14.0, "exam": 15.0, "mock": 0, "practical": 0, "total": 14.29, "remark": "Strong", "complete": True},
            {"subject": "Sports", "coef": 1, "seq1": 14.0, "seq2": 14.5, "exam": 0, "mock": 0, "practical": 0, "total": 14.25, "remark": "Active", "complete": False},
        ]
        summary = {
            "average": 13.21,
            "class_position": 2,
            "class_size": 28,
            "school_position": 5,
            "school_size": 120,
            "promotion_status": "PROMOTED",
            "teacher_remark": "Consistent dedication.",
        }
        weights = SimpleNamespace(seq1_weight=20, seq2_weight=20, exam_weight=60, mock_weight=0, practical_weight=0)

    context = {
        "report_style": style,
        "student": student_obj,
        "student_name": student_name,
        "year": year_obj,
        "term": term_obj,
        "rows": rows,
        "summary": summary,
        "weights": weights,
        "metadata": metadata,
        "generated_at": timezone.now(),
        "preview_mode": True,
    }
    return render(request, "siteconfig/reportcard_style_preview.html", context)
@permission_required("settings.manage")
def clear_preview(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, "Preview cleared.")
    return redirect("siteconfig:user_preferences")


@login_required
def user_preferences(request):
    preference, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = UserPreferenceForm(request.POST, instance=preference, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Preferences updated.")
            return redirect("siteconfig:user_preferences")
        messages.error(request, "Please fix the errors below.")
    else:
        form = UserPreferenceForm(instance=preference, user=request.user)

    return render(request, "siteconfig/user_preferences.html", {"form": form})


@permission_required("settings.manage")
def report_library(request):
    templates = ReportTemplate.objects.filter(is_active=True)
    return render(request, "siteconfig/report_library.html", {"reports": templates})


@permission_required("settings.manage")
def download_report(request, slug):
    template = get_object_or_404(ReportTemplate, slug=slug, is_active=True)
    headers, rows = template.get_export_data()

    if not headers:
        messages.warning(request, "No export handler registered for this report.")
        return redirect("siteconfig:report_library")

    return render_csv_response(headers, rows, template.filename())


def render_csv_response(headers, rows, filename) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response
