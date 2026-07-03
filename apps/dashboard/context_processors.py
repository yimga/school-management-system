"""Dashboard context processors.

``first_run_zero_state`` exposes a per-role first-run welcome card to every
template. It is populated ONLY on a role-home landing while the tenant is still
in first-run (see ``first_run_zero_state.build_first_run_zero_state``); on every
other request it returns ``{}`` so the global cost is a couple of getattrs.

``first_run_tour`` (T17) exposes the autostart config for the per-role first-run
guided tour. It resolves the tour context ONLY on the three tenant role landings
(teacher / parent / student) and only for an authenticated user who has not yet
completed that role's tour (persisted in ``DashboardUserPreference``). On every
other request it returns ``{}``.
"""

from __future__ import annotations


def first_run_zero_state(request):
    """Inject ``first_run_zero_state`` (a render-ready card) when applicable."""
    try:
        from apps.dashboard.first_run_zero_state import build_first_run_zero_state

        payload = build_first_run_zero_state(request)
    except Exception:  # noqa: BLE001 — a context processor must never break rendering
        return {}
    return {"first_run_zero_state": payload} if payload else {}


# Tenant role-landing view name → shared tour catalog context. The engine +
# steps API + catalog already define these contexts (apps/siteconfig/tour_catalog.py);
# this just decides WHEN to autostart on a first visit.
_ROLE_LANDING_TO_TOUR = {
    "portal:teacher_dashboard_alias": "teacher_portal",
    "portal:parent_dashboard": "parent_portal",
    "portal:student_portal_grades": "student_portal",
}


def first_run_tour(request):
    """Inject the per-role first-run tour autostart config on the role landings.

    Returns ``{}`` for anonymous users and every non-landing view, so the global
    cost is a dict lookup on ``resolver_match.view_name``. On a role landing it
    exposes ``rmc_fr_tour_context`` / ``rmc_fr_tour_show`` / ``rmc_fr_tour_complete_url``
    which ``portal_base.html`` uses to emit ``#rmc-tour-page-config`` exactly once
    (and never again once the user finishes/skips the tour).
    """
    try:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return {}
        match = getattr(request, "resolver_match", None)
        view_name = getattr(match, "view_name", "") if match else ""
        context = _ROLE_LANDING_TO_TOUR.get(view_name or "")
        if not context:
            return {}

        completed = False
        try:
            from apps.runtime_blueprints.models import DashboardUserPreference

            pref = DashboardUserPreference.objects.filter(user=user).first()
            if pref:
                completed = bool(
                    (pref.dashboard_layout or {}).get(f"tour_{context}_completed")
                )
        except Exception:  # noqa: BLE001 — never let a prefs read break rendering
            completed = False

        from django.urls import reverse

        return {
            "rmc_fr_tour_context": context,
            "rmc_fr_tour_show": not completed,
            "rmc_fr_tour_complete_url": (
                reverse("accounts:mark_tour_complete") + "?context=" + context
            ),
        }
    except Exception:  # noqa: BLE001 — a context processor must never break rendering
        return {}
