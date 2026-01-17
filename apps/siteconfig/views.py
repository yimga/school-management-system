# -*- coding: utf-8 -*-

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.shortcuts import redirect, render

from .forms import SiteSettingsForm
from .models import SiteSettings

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

                # store previewable fields in session (logo preview is tricky; skip for now)
                request.session[SESSION_KEY] = {
                    "site_name": cleaned.get("site_name"),
                    "tagline": cleaned.get("tagline"),
                    "primary_color": cleaned.get("primary_color"),
                    "accent_color": cleaned.get("accent_color"),
                    "use_dark_mode": cleaned.get("use_dark_mode"),
                    "maintenance_mode": cleaned.get("maintenance_mode"),
                    "enable_parent_portal": cleaned.get("enable_parent_portal"),
                    "enable_teacher_portal": cleaned.get("enable_teacher_portal"),
                    "enable_reports_pdf": cleaned.get("enable_reports_pdf"),
                }
                request.session.modified = True
                messages.success(request, "✅ Preview mode enabled (not saved).")
                return redirect("siteconfig_customizer")

            # default = save
            form.save()
            cache.delete(CACHE_KEY)
            request.session.pop(SESSION_KEY, None)  # clear preview after saving
            messages.success(request, "✅ Site settings saved.")
            return redirect("siteconfig_customizer")

        messages.error(request, "❌ Please fix the errors below.")

    else:
        form = SiteSettingsForm(instance=settings_obj)

    return render(request, "siteconfig/customizer.html", {"form": form})


@staff_member_required
def clear_preview(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, "Preview cleared.")
    return redirect("siteconfig_customizer")

