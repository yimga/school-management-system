# Optional: change school admin theme (UNFOLD/JAZZMIN/SNEAT) + Theme Gallery link
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import login_required, permission_required


THEME_CHOICES = [
    ("UNFOLD", "Unfold (Modern) — recommended"),
    ("JAZZMIN", "Jazzmin (Classic)"),
    ("SNEAT", "Sneat (Enterprise)"),
]


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET", "POST"])
def school_theme_settings(request):
    """Change school admin theme (theme_choice). Link to Theme Gallery doc."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Select your school to change theme.")
        return redirect("portal:home")
    if not hasattr(school, "theme_choice"):
        messages.info(request, "Theme choice is not configured for this deployment.")
        return redirect("siteconfig:user_preferences")
    current = getattr(school, "theme_choice", "UNFOLD") or "UNFOLD"
    if request.method == "POST":
        choice = (request.POST.get("theme_choice") or "UNFOLD").strip().upper()
        if choice not in ("UNFOLD", "JAZZMIN", "SNEAT"):
            choice = "UNFOLD"
        school.theme_choice = choice
        school.save(update_fields=["theme_choice", "updated_at"])
        messages.success(request, f"Theme set to {choice}. Refresh admin/backend to see the change.")
        return redirect("siteconfig:school_theme_settings")
    return render(request, "siteconfig/school_theme_settings.html", {
        "school": school,
        "current_theme": current,
        "theme_choices": THEME_CHOICES,
    })
