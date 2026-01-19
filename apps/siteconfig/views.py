# -*- coding: utf-8 -*-

import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import SiteSettingsForm, UserPreferenceForm
from .models import ReportTemplate, SiteSettings, ThemePack, UserPreference

CACHE_KEY = "site_settings_v1"
SESSION_KEY = "site_preview_settings"


def maintenance_view(request):
    return render(request, "siteconfig/maintenance.html")


@staff_member_required
def customizer(request):
    settings_obj = SiteSettings.get_solo()

    if request.method == "POST":
        form = SiteSettingsForm(request.POST, request.FILES, instance=settings_obj)

        action = request.POST.get("_action")  # save | preview

        if form.is_valid():
            if action == "preview":
                cleaned = form.cleaned_data
                request.session[SESSION_KEY] = {
                    "site_name": cleaned.get("site_name"),
                    "tagline": cleaned.get("tagline"),
                    "primary_color": cleaned.get("primary_color"),
                    "accent_color": cleaned.get("accent_color"),
                    "use_dark_mode": cleaned.get("use_dark_mode"),
                    "maintenance_mode": cleaned.get("maintenance_mode"),
                    "company_name": cleaned.get("company_name"),
                    "company_address": cleaned.get("company_address"),
                    "company_phone": cleaned.get("company_phone"),
                    "company_email": cleaned.get("company_email"),
                    "ministry_registration_code": cleaned.get("ministry_registration_code"),
                    "company_slug": cleaned.get("company_slug"),
                    "enable_parent_portal": cleaned.get("enable_parent_portal"),
                    "enable_teacher_portal": cleaned.get("enable_teacher_portal"),
                    "enable_reports_pdf": cleaned.get("enable_reports_pdf"),
                    "report_downloads_enabled": cleaned.get("report_downloads_enabled"),
                    "portal_features": cleaned.get("portal_features"),
                    "notification_channels": cleaned.get("notification_channels"),
                    "default_dashboard_view": cleaned.get("default_dashboard_view"),
                    "default_refresh_rate": cleaned.get("default_refresh_rate"),
                    "top_students_default_limit": cleaned.get("top_students_default_limit"),
                    "pass_mark": cleaned.get("pass_mark"),
                    "use_promotion_rule_for_pass": cleaned.get("use_promotion_rule_for_pass"),
                    "weak_subject_threshold": cleaned.get("weak_subject_threshold"),
                    "improvement_delta_threshold": cleaned.get("improvement_delta_threshold"),
                    "deadline_mode": cleaned.get("deadline_mode"),
                }
                request.session.modified = True
                messages.success(request, "ƒo. Preview mode enabled (not saved).")
                return redirect("siteconfig:customizer")

            form.save()
            cache.delete(CACHE_KEY)
            request.session.pop(SESSION_KEY, None)
            messages.success(request, "ƒo. Site settings saved.")
            return redirect("siteconfig:customizer")

        messages.error(request, "ƒ?O Please fix the errors below.")

    else:
        form = SiteSettingsForm(instance=settings_obj)

    theme_packs = ThemePack.objects.filter(is_active=True).order_by("-is_default", "name")
    report_templates = ReportTemplate.objects.filter(is_active=True)
    context = {
        "form": form,
        "theme_packs": theme_packs,
        "report_templates": report_templates,
    }
    return render(request, "siteconfig/customizer.html", context)


@staff_member_required
def clear_preview(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, "Preview cleared.")
    return redirect("siteconfig:customizer")


@login_required
def user_preferences(request):
    preference, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = UserPreferenceForm(request.POST, instance=preference)
        if form.is_valid():
            form.save()
            messages.success(request, "Preferences updated.")
            return redirect("siteconfig:user_preferences")
        messages.error(request, "Please fix the errors below.")
    else:
        form = UserPreferenceForm(instance=preference)

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
