"""Operator admin view for the cockpit configurability cascade (v3.56).

Renders ``CockpitPayloadForm`` against the tenant SiteSettings singleton
and writes the nested ``cockpit_payload`` dict on POST. Staff/superuser
only — both layers (LoginRequired + UserPassesTest) are enforced so the
view rejects unauthenticated traffic AND non-operator authenticated
users.

URL: ``/super/configure/cockpit/`` — wired in ``apps.siteconfig.urls``
under the ``siteconfig:`` namespace as ``cockpit_configure``. The
``/super/`` prefix in the path comes from the ``include('super/', …)``
mount; this view does not assume the host is the manager surface (it
runs whichever schema the request resolves into so the form persists
the tenant's own cockpit_payload).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from .forms_cockpit import CockpitPayloadForm


def _resolve_site_settings_instance(request: HttpRequest) -> Any:
    """Return the per-tenant SiteSettings instance the form should edit.

    Resolution order (mirrors how ``cockpit_context.py`` reads the
    value):

    1. ``apps.siteconfig.config_service.get_effective_site_settings`` —
       authoritative tenant-aware resolver.
    2. ``SiteSettings.get_solo`` — singleton fallback (creates the
       row on first access).
    """
    # Tenant-aware resolver — preferred path.
    try:
        from .config_service import get_effective_site_settings

        site = get_effective_site_settings(request=request)
        if site is not None and getattr(site, "pk", None) is not None:
            return site
    except Exception:
        # Defensive — never let resolver errors crash the operator UI;
        # fall through to the singleton path.
        pass

    from .models import SiteSettings

    return SiteSettings.get_solo()


class CockpitConfigureView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """GET renders the form; POST persists ``cockpit_payload``.

    Access is staff OR superuser. Non-staff authenticated users hit
    ``handle_no_permission()`` and receive a 403, NOT a redirect to
    login (that would mask the permission failure).
    """

    template_name = "siteconfig/super/cockpit_configure.html"
    form_class = CockpitPayloadForm

    # ``UserPassesTestMixin`` raises PermissionDenied (-> 403) instead
    # of redirecting on test failure, which is the correct UX for an
    # operator surface.
    raise_exception = True

    # ------------------------------------------------------------------
    # Access control.
    # ------------------------------------------------------------------

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))

    # ------------------------------------------------------------------
    # FormView wiring — instance + initial come from the tenant SiteSettings.
    # ------------------------------------------------------------------

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = _resolve_site_settings_instance(self.request)
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        form: CockpitPayloadForm = ctx["form"]
        ctx["footer_fields"] = [form[name] for name in form.FOOTER_FIELDS]
        ctx["community_fields"] = [form[name] for name in form.COMMUNITY_FIELDS]
        ctx["newsletter_fields"] = [form[name] for name in form.NEWSLETTER_FIELDS]
        # v3.57.1: enable toggles for the 20 NEW v3.57 cockpit sections.
        # Guarded with getattr so older form revisions that don't carry the
        # tuples still render — the template short-circuits when the list
        # is missing/empty.
        ctx["front_office_fields"] = [
            form[name] for name in getattr(form, "FRONT_OFFICE_FIELDS", ())
        ]
        ctx["tenant_v3_extended_fields"] = [
            form[name] for name in getattr(form, "TENANT_V3_EXTENDED_FIELDS", ())
        ]
        # v3.57.2: 4 rich-editor fieldsets that promote selected sections
        # from enable-toggle-only to full content editor. Guarded with
        # getattr so older form revisions still render.
        ctx["lesson_of_day_fields"] = [
            form[name] for name in getattr(form, "LESSON_OF_DAY_FIELDS", ())
        ]
        ctx["ai_study_buddy_fields"] = [
            form[name] for name in getattr(form, "AI_STUDY_BUDDY_FIELDS", ())
        ]
        ctx["teacher_spotlight_fields"] = [
            form[name] for name in getattr(form, "TEACHER_SPOTLIGHT_FIELDS", ())
        ]
        ctx["upcoming_events_fields"] = [
            form[name] for name in getattr(form, "UPCOMING_EVENTS_FIELDS", ())
        ]
        # v3.57.12: 6 NEW rich-editor fieldsets extending the Agent D pattern.
        # Same getattr() guard so older form revisions still render.
        ctx["today_snapshot_fields"] = [
            form[name] for name in getattr(form, "TODAY_SNAPSHOT_FIELDS", ())
        ]
        ctx["quick_actions_grid_fields"] = [
            form[name] for name in getattr(form, "QUICK_ACTIONS_GRID_FIELDS", ())
        ]
        ctx["activity_timeline_fields"] = [
            form[name] for name in getattr(form, "ACTIVITY_TIMELINE_FIELDS", ())
        ]
        ctx["achievements_card_fields"] = [
            form[name] for name in getattr(form, "ACHIEVEMENTS_CARD_FIELDS", ())
        ]
        ctx["live_world_map_fields"] = [
            form[name] for name in getattr(form, "LIVE_WORLD_MAP_FIELDS", ())
        ]
        ctx["audit_feed_fields"] = [
            form[name] for name in getattr(form, "AUDIT_FEED_FIELDS", ())
        ]
        ctx["page_title"] = _("Cockpit configuration")
        ctx["cockpit_configure_url"] = self.request.path
        return ctx

    # ------------------------------------------------------------------
    # Success path.
    # ------------------------------------------------------------------

    def form_valid(self, form: CockpitPayloadForm) -> HttpResponse:
        # ``form.clean()`` mirrored the nested dict onto the instance;
        # save persists the JSON column.
        instance = form.instance
        instance.cockpit_payload = form.cleaned_data.get("cockpit_payload", {})
        try:
            instance.save(update_fields=["cockpit_payload", "updated_at"])
        except Exception:
            # Fall back to a full save for instances where update_fields
            # doesn't apply (e.g. fresh singleton row).
            instance.save()
        messages.success(self.request, _("Cockpit configuration saved."))
        return HttpResponseRedirect(self._success_url())

    def _success_url(self) -> str:
        try:
            return reverse("siteconfig:cockpit_configure")
        except Exception:
            return self.request.path

    # ------------------------------------------------------------------
    # Optional reset-to-defaults POST sub-action.
    # ------------------------------------------------------------------

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.POST.get("action") == "reset_defaults":
            return self._handle_reset(request)
        return super().post(request, *args, **kwargs)

    def _handle_reset(self, request: HttpRequest) -> HttpResponse:
        instance = _resolve_site_settings_instance(request)
        instance.cockpit_payload = {}
        try:
            instance.save(update_fields=["cockpit_payload", "updated_at"])
        except Exception:
            instance.save()
        messages.info(request, _("Cockpit configuration reset to defaults."))
        return HttpResponseRedirect(self._success_url())
