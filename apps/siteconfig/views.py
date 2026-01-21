# -*- coding: utf-8 -*-

import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

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

CACHE_KEY = "site_settings_v1"
SESSION_KEY = "site_preview_settings"


def maintenance_view(request):
    return render(request, "siteconfig/maintenance.html")


@staff_member_required
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

@staff_member_required
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

@staff_member_required
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


@staff_member_required
def report_library(request):
    templates = ReportTemplate.objects.filter(is_active=True)
    return render(request, "siteconfig/report_library.html", {"reports": templates})


@staff_member_required
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
