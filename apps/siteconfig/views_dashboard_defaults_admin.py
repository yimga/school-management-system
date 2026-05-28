"""Per-role/page dashboard defaults admin (v3.99.24).

Manages the operator-curated defaults that new users inherit for each
(role, page) combination — specifically the two settings written by the
add-widget gallery:

* ``__settings__.requested_widget_ids`` — built-in widgets to pre-include
  on first visit, even if not on the role's default catalog
* ``__settings__.promoted_cockpit_ids`` — cockpit sections promoted to
  live as dashboard widgets for that role/page

Persisted via the ``DashboardLayout`` model with ``user=None, is_default=True``;
that row is the per-role/page default the existing layout API falls back to
when a user has no personal layout. This is the same pattern the legacy
``_get_default_layout`` helper uses, so no new model is needed.

Permission marker (audited by ``audit_role_permission_matrix.py``):

* ``# rbac-allow: super-staff-dashboard-defaults-admin``
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


# (role, page) pairs the admin form manages. Mirrors _allowed_roles_for_page
# entries that actually carry dashboards (skip portal-kb / entity-console).
_MANAGED_PAGES: tuple[tuple[str, str], ...] = (
    ("ADMIN",         "backend"),
    ("IT_ADMIN",      "backend"),
    ("LEADERSHIP",    "backend"),
    ("PRINCIPAL",     "backend"),
    ("FINANCE_STAFF", "finance"),
    ("ACADEMICS_STAFF","analytics"),
    ("TEACHER",       "teacher"),
    ("PARENT",        "parent"),
    ("STUDENT",       "student"),
)


def _resolve_default_layout(role: str, page: str):
    """Fetch (or create) the DashboardLayout row with user=None, is_default=True."""
    from apps.runtime_blueprints.models import DashboardLayout

    layout, _ = DashboardLayout.objects.get_or_create(
        user=None,
        role=role,
        page=page,
        defaults={"is_default": True, "layout": {"items": [], "__settings__": {}}},
    )
    if not layout.is_default:
        layout.is_default = True
        layout.save(update_fields=["is_default", "updated_at"])
    return layout


def _read_requested_and_promoted(layout) -> tuple[list[str], list[str]]:
    raw = (layout.layout if layout else {}) or {}
    settings = (raw.get("__settings__") or {}) if isinstance(raw, dict) else {}
    requested = settings.get("requested_widget_ids") or []
    promoted = settings.get("promoted_cockpit_ids") or []
    if not isinstance(requested, list):
        requested = []
    if not isinstance(promoted, list):
        promoted = []
    return [str(x) for x in requested if str(x)], [str(x) for x in promoted if str(x).startswith("cockpit-")]


def _write_requested_and_promoted(layout, *, requested_ids: list[str], promoted_ids: list[str]) -> None:
    raw = (layout.layout if layout else {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    settings = dict(raw.get("__settings__") or {})
    settings["requested_widget_ids"] = sorted(set(requested_ids))
    settings["promoted_cockpit_ids"] = sorted(set(p for p in promoted_ids if p.startswith("cockpit-")))
    raw["__settings__"] = settings
    raw.setdefault("items", [])
    layout.layout = raw
    layout.is_default = True
    layout.save(update_fields=["layout", "is_default", "updated_at"])


def _build_catalogs_for_page(page: str) -> dict[str, Any]:
    """Return all built-in widgets + cockpit catalog for the given page."""
    out: dict[str, Any] = {"widgets": [], "cockpit_widgets": []}
    try:
        from apps.runtime_blueprints.models import DashboardWidget

        widgets = list(
            DashboardWidget.objects.filter(page=page, is_active=True).order_by("order").values("id", "name", "description")
        )
        out["widgets"] = widgets
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard_defaults_admin: built-in widget query failed: %s", exc)
    try:
        from apps.siteconfig.cockpit_widget_bridge import list_cockpit_widget_catalog

        out["cockpit_widgets"] = list_cockpit_widget_catalog(page=page)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard_defaults_admin: cockpit bridge failed: %s", exc)
    return out


@method_decorator(staff_member_required, name="dispatch")
class DashboardDefaultsAdminView(LoginRequiredMixin, View):
    """Operator-only admin: manage requested_widget_ids + promoted_cockpit_ids
    per (role, page).

    GET: render a per-pair editor. POST: save the selected pair, then redirect
    to the same page so the operator can save the next pair.

    # rbac-allow: super-staff-dashboard-defaults-admin
    """

    template = "siteconfig/super_dashboard_defaults_admin.html"

    def _selected_pair(self, request: HttpRequest) -> tuple[str, str]:
        role = (request.GET.get("role") or request.POST.get("role") or _MANAGED_PAGES[0][0]).strip().upper()
        page = (request.GET.get("page") or request.POST.get("page") or _MANAGED_PAGES[0][1]).strip().lower()
        if (role, page) not in _MANAGED_PAGES:
            return _MANAGED_PAGES[0]
        return role, page

    def get(self, request: HttpRequest) -> HttpResponse:
        role, page = self._selected_pair(request)
        layout = _resolve_default_layout(role, page)
        requested_ids, promoted_ids = _read_requested_and_promoted(layout)
        catalogs = _build_catalogs_for_page(page)
        context = {
            "managed_pairs": [
                {"role": r, "page": p, "is_selected": (r == role and p == page)}
                for (r, p) in _MANAGED_PAGES
            ],
            "selected_role": role,
            "selected_page": page,
            "requested_ids_set": set(requested_ids),
            "promoted_ids_set": set(promoted_ids),
            "available_widgets": catalogs["widgets"],
            "cockpit_widgets": catalogs["cockpit_widgets"],
            "post_url": reverse("siteconfig:dashboard_defaults_admin"),
            "save_count": len(requested_ids) + len(promoted_ids),
        }
        return render(request, self.template, context)

    def post(self, request: HttpRequest) -> HttpResponse:
        role, page = self._selected_pair(request)
        layout = _resolve_default_layout(role, page)
        # Collect from form
        requested_ids = [w for w in request.POST.getlist("requested_widget_id") if w]
        promoted_ids = [w for w in request.POST.getlist("promoted_cockpit_id") if w]
        _write_requested_and_promoted(layout, requested_ids=requested_ids, promoted_ids=promoted_ids)
        logger.info(
            "dashboard_defaults_admin: actor=%s role=%s page=%s saved requested=%d promoted=%d",
            getattr(request.user, "pk", None), role, page, len(requested_ids), len(promoted_ids),
        )
        url = reverse("siteconfig:dashboard_defaults_admin") + f"?role={role}&page={page}&saved=1"
        return redirect(url)
