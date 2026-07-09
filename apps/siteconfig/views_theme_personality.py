"""Operator admin view for the theme-personality cascade — v3.59.x Wave 11 Agent W.

Renders ``ThemePersonalityForm`` against the tenant SiteSettings singleton
and writes the nested ``theme_personality`` dict on POST. Staff/superuser
only — both layers (LoginRequired + UserPassesTest) are enforced so the
view rejects unauthenticated traffic AND non-operator authenticated users.

URL: ``/siteconfig/super/configure/theme-personality/`` (platform operator)
URL: ``/super/theme-personality/``                  (tenant operator alias)

Same view object handles both URLs — the request's ``public_host_kind``
determines whether the platform or tenant SiteSettings row is edited.
The tenant-aware resolver ``get_effective_site_settings`` does the routing
naturally, so this view stays thin and host-agnostic.

# rbac-allow: super-staff-theme-personality-config -- staff-gated cockpit editor
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from .forms_theme_personality import ThemePersonalityForm


def _resolve_site_settings_instance(request: HttpRequest) -> Any:
    """Return the per-tenant SiteSettings instance the form should edit.

    Resolution order (mirrors how ``page_personality.py`` reads the
    value):

    1. ``apps.siteconfig.config_service.get_effective_site_settings`` —
       authoritative tenant-aware resolver.
    2. ``SiteSettings.get_solo`` — singleton fallback (creates the
       row on first access).
    """
    try:
        from .config_service import get_effective_site_settings

        # config-resolver-allow: namespace returned as the form instance ThemePersonalityForm edits and saves
        site = get_effective_site_settings(request=request)
        if site is not None and getattr(site, "pk", None) is not None:
            return site
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass

    from .models import SiteSettings

    return SiteSettings.get_solo()


@method_decorator(staff_member_required, name="dispatch")
class ThemePersonalityConfigView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """Operator-facing theme-personality cockpit editor.

    GET  -> render the form pre-seeded from ``SiteSettings.theme_personality``.
    POST -> validate, persist the JSON column, redirect to ``?saved=1``.

    ``action=reset_to_defaults`` POST clears the JSON.

    # rbac-allow: super-staff-theme-personality-config
    """

    template_name = "siteconfig/super/theme_personality_configure.html"
    form_class = ThemePersonalityForm
    raise_exception = True

    # ------------------------------------------------------------------
    # Access control. Staff or superuser only.
    # ------------------------------------------------------------------

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        return bool(
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )

    # ------------------------------------------------------------------
    # FormView wiring — pre-seed initial from the JSON column.
    # ------------------------------------------------------------------

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        site = _resolve_site_settings_instance(self.request)
        payload = getattr(site, "theme_personality", None) or {}
        # Defer to the form's seeding helper so the round-trip logic
        # lives in one place.
        form = self.form_class(initial=dict(initial))
        form._seed_initial_from_payload(payload)
        merged = dict(initial)
        merged.update(form.initial)
        return merged

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        form: ThemePersonalityForm = ctx["form"]

        # Group fields for fieldset rendering.
        ctx["accent_fields"] = [form[name] for name in form.ACCENT_FIELDS]
        ctx["status_fields"] = [form[name] for name in form.STATUS_FIELDS]
        ctx["heatmap_fields"] = [form[name] for name in form.HEATMAP_FIELDS]
        ctx["chart_series_fields"] = [
            form[name] for name in form.CHART_SERIES_FIELDS
        ]

        # Archetype catalog for the live-preview panel (slug, label).
        from .forms_theme_personality import _ARCHETYPES

        ctx["archetype_catalog"] = [
            {"slug": slug, "label": label} for slug, label, _ph in _ARCHETYPES
        ]

        ctx["page_title"] = _("Theme personality")
        ctx["theme_personality_url"] = self.request.path
        ctx["cockpit_configure_url"] = _safe_reverse("siteconfig:cockpit_configure")
        ctx["saved_flag"] = self.request.GET.get("saved") == "1"
        return ctx

    # ------------------------------------------------------------------
    # POST routing — reset_to_defaults vs normal save.
    # ------------------------------------------------------------------

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.POST.get("action") == "reset_to_defaults":
            return self._handle_reset(request)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: ThemePersonalityForm) -> HttpResponse:
        site = _resolve_site_settings_instance(self.request)
        payload = form._build_payload(form.cleaned_data)
        # Phase B: theme_personality lives in RuntimeDefaults.payload, not as a
        # SiteSettings column. Persist via the accessor; reads still go through
        # getattr(site, "theme_personality") (the __getattr__ payload shim).
        type(site).set_theme_personality(payload)
        # PII-logging-smell-safe: never log raw hex codes; only a coarse
        # success signal + a count of populated sections.
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "theme_personality_save: ok=True sections=%d",
            len([k for k in payload.keys() if payload.get(k)]),
        )
        messages.success(self.request, _("Theme personality saved."))
        return HttpResponseRedirect(self._success_url())

    def form_invalid(self, form: ThemePersonalityForm) -> HttpResponse:
        # PII-logging-smell-safe: counts only.
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "theme_personality_save: ok=False error_count=%d",
            sum(len(errs) for errs in form.errors.values()),
        )
        return super().form_invalid(form)

    def _handle_reset(self, request: HttpRequest) -> HttpResponse:
        site = _resolve_site_settings_instance(request)
        # Phase B: persist via accessor (RuntimeDefaults.payload), not a column.
        type(site).set_theme_personality({})
        messages.info(request, _("Theme personality reset to defaults."))
        return HttpResponseRedirect(self._success_url())

    def _success_url(self) -> str:
        url = _safe_reverse("siteconfig:theme_personality_configure")
        if url:
            return url + "?saved=1"
        return self.request.path + "?saved=1"


def _safe_reverse(name: str) -> str:
    """Reverse a URL name; return empty string on NoReverseMatch."""
    try:
        return reverse(name)
    except Exception:
        return ""
