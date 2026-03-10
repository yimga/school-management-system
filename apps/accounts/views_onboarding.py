"""
First-login checklist and Setup Studio entry.
Dashboard assembly and recommendation logic live in apps.dashboard.context and recommendation_service.
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.urls import reverse

from .decorators import permission_required
from .views import _is_admin_user


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def dismiss_first_login_checklist(request):
    """W1-6: Dismiss the first-login checklist for this user (persisted in DashboardUserPreference)."""
    try:
        from apps.siteconfig.models_dashboard import DashboardUserPreference
        pref, _ = DashboardUserPreference.objects.get_or_create(user=request.user, defaults={"dashboard_layout": {}})
        layout = dict(pref.dashboard_layout or {})
        layout["first_login_checklist_dismissed"] = True
        pref.dashboard_layout = layout
        pref.save(update_fields=["dashboard_layout"])
    except Exception:
        pass
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("accounts:backend_dashboard")
    return redirect(next_url)
