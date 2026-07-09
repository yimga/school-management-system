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
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView

from .forms_cockpit import CockpitPayloadForm
from .tenant_experience_policy import user_may_configure_tenant_experience


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

        # config-resolver-allow: namespace returned as the form instance CockpitPayloadForm edits and saves
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
        return user_may_configure_tenant_experience(self.request.user)

    # ------------------------------------------------------------------
    # FormView wiring — instance + initial come from the tenant SiteSettings.
    # ------------------------------------------------------------------

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = _resolve_site_settings_instance(self.request)
        kwargs["configure_request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        form: CockpitPayloadForm = ctx["form"]
        ctx["footer_fields"] = [form[name] for name in form.FOOTER_FIELDS]
        ctx["tenant_experience_policy_fields"] = [
            form[name] for name in getattr(form, "TENANT_EXPERIENCE_POLICY_FIELDS", ())
        ]
        from apps.siteconfig.tenant_experience_policy import (
            portal_experience_preset_ui_context,
            resolve_tenant_experience_policy,
        )

        ctx.update(
            portal_experience_preset_ui_context(
                self.request,
                resolve_tenant_experience_policy(self.request),
                post_url=self.request.path,
            )
        )
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
        # v3.57.13: 5 NEW rich-editor fieldsets extending the Agent D+H pattern
        # to forecast_lane / slo_clocks / trust_nutrition / parent_teacher_thread
        # / financial_timeline. Same getattr() guard so older form revisions
        # still render — the template short-circuits when the list is empty.
        ctx["forecast_lane_fields"] = [
            form[name] for name in getattr(form, "FORECAST_LANE_FIELDS", ())
        ]
        ctx["slo_clocks_fields"] = [
            form[name] for name in getattr(form, "SLO_CLOCKS_FIELDS", ())
        ]
        ctx["trust_nutrition_fields"] = [
            form[name] for name in getattr(form, "TRUST_NUTRITION_FIELDS", ())
        ]
        ctx["parent_teacher_thread_fields"] = [
            form[name] for name in getattr(form, "PARENT_TEACHER_THREAD_FIELDS", ())
        ]
        ctx["financial_timeline_fields"] = [
            form[name] for name in getattr(form, "FINANCIAL_TIMELINE_FIELDS", ())
        ]
        # v3.57.14: 6 NEW rich-editor fieldsets extending the Agent D+H+M
        # pattern to operator_presence / operator_notebook / tenant_heatmap
        # / revenue_waterfall / realtime_presence / calendar_weather. Same
        # getattr() guard so older form revisions still render — the
        # template short-circuits when the list is empty.
        ctx["operator_presence_fields"] = [
            form[name] for name in getattr(form, "OPERATOR_PRESENCE_FIELDS", ())
        ]
        ctx["operator_notebook_fields"] = [
            form[name] for name in getattr(form, "OPERATOR_NOTEBOOK_FIELDS", ())
        ]
        ctx["tenant_heatmap_fields"] = [
            form[name] for name in getattr(form, "TENANT_HEATMAP_FIELDS", ())
        ]
        ctx["revenue_waterfall_fields"] = [
            form[name] for name in getattr(form, "REVENUE_WATERFALL_FIELDS", ())
        ]
        ctx["realtime_presence_fields"] = [
            form[name] for name in getattr(form, "REALTIME_PRESENCE_FIELDS", ())
        ]
        ctx["calendar_weather_fields"] = [
            form[name] for name in getattr(form, "CALENDAR_WEATHER_FIELDS", ())
        ]
        # v3.57.16: 5 NEW rich-editor fieldsets (final batch) extending the
        # Agent D+H+M+P pattern to workspace_context_tenant / activity_ticker
        # / gradebook_trend / attendance_heatmap / life_event_timeline.
        # Same getattr() guard so older form revisions still render — the
        # template short-circuits when the list is empty.
        ctx["workspace_context_tenant_fields"] = [
            form[name]
            for name in getattr(form, "WORKSPACE_CONTEXT_TENANT_FIELDS", ())
        ]
        ctx["activity_ticker_fields"] = [
            form[name] for name in getattr(form, "ACTIVITY_TICKER_FIELDS", ())
        ]
        ctx["live_banner_studio_fields"] = [
            form[name] for name in getattr(form, "LIVE_BANNER_STUDIO_FIELDS", ())
        ]
        try:
            from apps.siteconfig.cockpit_live_banner_program import build_live_banner_preview

            payload = getattr(form.instance, "cockpit_payload", None) or {}
            if not isinstance(payload, dict):
                payload = {}
            ctx["live_banner_manager_preview"] = build_live_banner_preview(
                payload.get("activity_ticker") or {},
                self.request,
            )
            ctx["live_banner_tenant_preview"] = build_live_banner_preview(
                payload.get("tenant_activity_ticker") or {},
                self.request,
            )
        except Exception:
            ctx["live_banner_manager_preview"] = {}
            ctx["live_banner_tenant_preview"] = {}
        ctx["gradebook_trend_fields"] = [
            form[name] for name in getattr(form, "GRADEBOOK_TREND_FIELDS", ())
        ]
        ctx["attendance_heatmap_fields"] = [
            form[name] for name in getattr(form, "ATTENDANCE_HEATMAP_FIELDS", ())
        ]
        ctx["life_event_timeline_fields"] = [
            form[name] for name in getattr(form, "LIFE_EVENT_TIMELINE_FIELDS", ())
        ]
        # v3.57.17: final cockpit editor — AI Copilot rail. Closes the
        # ai_copilot_rail complexity deferral; sibling_compare stays
        # code-only by design (privacy gate). Same getattr() guard so
        # older form revisions still render — the template short-circuits
        # when the list is empty.
        ctx["ai_copilot_rail_fields"] = [
            form[name] for name in getattr(form, "AI_COPILOT_RAIL_FIELDS", ())
        ]
        # v3.58.x Wave 9: sibling-compare operator-editable rich-editor
        # fieldset — closes the cockpit-section-editor track to 100%
        # (28/28). PRIVACY CONTRACT: this editor configures ONLY copy +
        # chrome (title / subtitle / CTA / consent banner / denied
        # state). It cannot toggle the per-parent ``opt_in`` consent
        # flag — sibling data still requires per-family consent before
        # any value renders. See
        # ``apps/siteconfig/cockpit_context._sibling_compare_defaults()``
        # docstring for the full contract.
        ctx["sibling_compare_fields"] = [
            form[name] for name in getattr(form, "SIBLING_COMPARE_FIELDS", ())
        ]
        # v3.57.18 Wave 8: public school-signup form rich-editor fieldset.
        # Defaults to enabled=True (front-door section) so the page renders
        # the moment the cascade lands. Same getattr() guard so older form
        # revisions still render — template short-circuits when empty.
        ctx["signup_form_fields"] = [
            form[name] for name in getattr(form, "SIGNUP_FORM_FIELDS", ())
        ]
        ctx["login_canvas_fields"] = [
            form[name] for name in getattr(form, "LOGIN_CANVAS_FIELDS", ())
        ]
        try:
            from apps.accounts.login_immersive_canvas import (
                build_login_canvas_cockpit_preview,
                login_canvas_pro_enabled,
                resolve_login_immersive_section,
            )

            preview_request = self.request
            preview_request.site_settings = form.instance
            section = resolve_login_immersive_section(preview_request)
            ctx["login_canvas_preview"] = build_login_canvas_cockpit_preview(
                section, self.request
            )
            pro_section = {
                "pro_enabled": bool(form["lic_pro_enabled"].value()),
            }
            ctx["login_canvas_pro_entitled"] = login_canvas_pro_enabled(
                self.request, pro_section
            )
        except Exception:
            ctx["login_canvas_preview"] = {}
            ctx["login_canvas_pro_entitled"] = False
        try:
            ctx["login_canvas_gallery_upload_url"] = reverse(
                "siteconfig:login_canvas_gallery_upload"
            )
        except Exception:
            ctx["login_canvas_gallery_upload_url"] = ""
        try:
            ctx["login_canvas_billing_url"] = reverse("siteconfig:billing_plan_readonly")
        except Exception:
            ctx["login_canvas_billing_url"] = ""
        # v3.58.x Wave 10 Agent S: trust pillars alerts editor — closes
        # the v8 200x preview's alerts-feed gap. Enable toggle + chrome
        # copy + 7 pillar label overrides. Same getattr() guard so older
        # form revisions still render — template short-circuits empty.
        ctx["trust_pillars_alerts_fields"] = [
            form[name]
            for name in getattr(form, "TRUST_PILLARS_ALERTS_FIELDS", ())
        ]
        ctx["page_title"] = _("Cockpit configuration")
        ctx["cockpit_configure_url"] = self.request.path
        # v3.99.25: accept ?section=<section_id> from the dashboard gallery's
        # cockpit-configure deep-link. The template uses this to scroll/focus
        # the matching fieldset; no-op when missing or unknown.
        requested_section = (self.request.GET.get("section") or "").strip().lower()
        if requested_section and requested_section.replace("_", "").replace("-", "").isalnum():
            ctx["focus_section"] = requested_section
        else:
            ctx["focus_section"] = ""
        return ctx

    # ------------------------------------------------------------------
    # Success path.
    # ------------------------------------------------------------------

    def form_valid(self, form: CockpitPayloadForm) -> HttpResponse:
        # ``form.clean()`` mirrored the nested dict onto the instance;
        # save persists the JSON column.
        instance = form.instance
        # Phase B: cockpit_payload is stored in RuntimeDefaults.payload (not a
        # SiteSettings column). Persist via the accessor; form.clean() still
        # builds cleaned_data["cockpit_payload"], and reads go through __getattr__.
        type(instance).set_cockpit_payload(form.cleaned_data.get("cockpit_payload", {}))
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
        if request.POST.get("action") == "apply_portal_experience_preset":
            return self._handle_apply_portal_experience_preset(request)
        return super().post(request, *args, **kwargs)

    def _handle_apply_portal_experience_preset(self, request: HttpRequest) -> HttpResponse:
        from apps.siteconfig.tenant_experience_policy import (
            apply_and_persist_experience_preset,
        )
        from apps.siteconfig.tenant_experience_presets import (
            EXPERIENCE_PRESET_IDS,
            ROLE_PRESET_BUCKETS,
            ROLE_PRESET_INHERIT,
        )

        instance = _resolve_site_settings_instance(request)
        preset_id = str(request.POST.get("preset_id") or "").strip().lower()
        role_bucket = str(request.POST.get("role_bucket") or "").strip().upper()

        if role_bucket in ROLE_PRESET_BUCKETS:
            if preset_id == ROLE_PRESET_INHERIT:
                apply_and_persist_experience_preset(
                    instance, ROLE_PRESET_INHERIT, role_bucket=role_bucket
                )
                messages.success(
                    request,
                    _("%(role)s theme reset to inherit school default.")
                    % {"role": role_bucket.title()},
                )
            elif preset_id in EXPERIENCE_PRESET_IDS and preset_id != "custom":
                apply_and_persist_experience_preset(
                    instance, preset_id, role_bucket=role_bucket
                )
                messages.success(
                    request,
                    _("%(role)s theme set to “%(preset)s”.")
                    % {
                        "role": role_bucket.title(),
                        "preset": preset_id.replace("_", " ").title(),
                    },
                )
            else:
                messages.error(request, _("Unknown portal experience preset."))
            return HttpResponseRedirect(self._success_url())

        if preset_id not in EXPERIENCE_PRESET_IDS or preset_id == "custom":
            messages.error(request, _("Unknown portal experience preset."))
            return HttpResponseRedirect(self._success_url())
        apply_and_persist_experience_preset(instance, preset_id)
        messages.success(
            request,
            _("Portal experience preset “%(preset)s” applied.")
            % {"preset": preset_id.replace("_", " ").title()},
        )
        return HttpResponseRedirect(self._success_url())

    def _handle_reset(self, request: HttpRequest) -> HttpResponse:
        instance = _resolve_site_settings_instance(request)
        # Phase B: persist via accessor (RuntimeDefaults.payload), not a column.
        type(instance).set_cockpit_payload({})
        messages.info(request, _("Cockpit configuration reset to defaults."))
        return HttpResponseRedirect(self._success_url())


# ---------------------------------------------------------------------------
# Wave 15 (v3.62.20 — 2026-05-23) — per-tenant marketing voice rich-edit.
#
# Sister of CockpitConfigureView; targets the narrower
# ``SiteSettings.cockpit_payload["marketing_voice"]`` sub-tree via a
# dedicated form so the main 5000-line CockpitPayloadForm doesn't need
# to grow another 15 fields. Live preview ships alongside the form
# (template re-uses the same side-by-side layout + JS as the Wave 13
# CountryRegistry admin form).
# ---------------------------------------------------------------------------


class MarketingVoiceConfigureView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """GET renders the per-tenant marketing voice form; POST saves it.

    Same access policy as ``CockpitConfigureView`` — staff OR superuser.
    """

    template_name = "siteconfig/super/marketing_voice_configure.html"
    raise_exception = True

    def get_form_class(self) -> Any:
        from .forms_marketing_voice import MarketingVoiceForm
        return MarketingVoiceForm

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = _resolve_site_settings_instance(self.request)
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Marketing voice (per-tenant)")
        ctx["marketing_voice_url"] = self.request.path
        return ctx

    def form_valid(self, form: Any) -> HttpResponse:
        instance = form.instance
        # Phase B: cockpit_payload stored in RuntimeDefaults.payload via accessor.
        type(instance).set_cockpit_payload(form.cleaned_data.get("cockpit_payload", {}))
        messages.success(self.request, _("Marketing voice saved for this tenant."))
        return HttpResponseRedirect(self.request.path)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.POST.get("action") == "reset_marketing_voice":
            instance = _resolve_site_settings_instance(request)
            payload = getattr(instance, "cockpit_payload", None) or {}
            if isinstance(payload, dict) and "marketing_voice" in payload:
                payload = {k: v for k, v in payload.items() if k != "marketing_voice"}
                # Phase B: persist via accessor (RuntimeDefaults.payload).
                type(instance).set_cockpit_payload(payload)
                messages.info(request, _("Marketing voice cleared — country defaults will apply."))
            return HttpResponseRedirect(request.path)
        return super().post(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# v8 cockpit shell chrome settings (skin per surface, header composition,
# emoji nav glyphs, page-header action buttons). Sister of CockpitConfigureView
# but targets the ``cockpit_*`` brand_experience virtual keys (chrome behaviour)
# rather than the ``cockpit_payload`` content dict. SOT: cockpit_config.py.
# ---------------------------------------------------------------------------


class CockpitShellConfigureView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """GET renders the cockpit shell settings; POST persists the cockpit_* keys.

    Same access policy as ``CockpitConfigureView`` — staff OR superuser.
    """

    template_name = "siteconfig/super/cockpit_shell_configure.html"
    raise_exception = True

    def get_form_class(self) -> Any:
        from .forms_cockpit_shell import CockpitShellSettingsForm

        return CockpitShellSettingsForm

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))

    def get_initial(self) -> dict[str, Any]:
        from .forms_cockpit_shell import CockpitShellSettingsForm

        site = _resolve_site_settings_instance(self.request)
        return CockpitShellSettingsForm.initial_from_site(site)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Cockpit shell")
        ctx["cockpit_shell_configure_url"] = self.request.path
        return ctx

    def form_valid(self, form: Any) -> HttpResponse:
        from .models import SiteSettings

        SiteSettings.update_cockpit_shell_settings(form.to_updates())
        messages.success(self.request, _("Cockpit shell settings saved."))
        return HttpResponseRedirect(self.request.path)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.POST.get("action") == "reset_cockpit_shell":
            from .cockpit_config import all_cockpit_keys
            from .models import SiteSettings

            # Reset by writing each knob back to its module default.
            from .cockpit_config import cockpit_setting_default

            SiteSettings.update_cockpit_shell_settings(
                {key: cockpit_setting_default(key) for key in all_cockpit_keys()}
            )
            messages.info(request, _("Cockpit shell settings reset to defaults."))
            return HttpResponseRedirect(request.path)
        return super().post(request, *args, **kwargs)


class LoginCanvasGalleryUploadView(LoginRequiredMixin, UserPassesTestMixin, View):
    """POST gallery image for login canvas; returns JSON ``public_url``.

    # rbac-allow: staff-configure-login-canvas-gallery-upload
    """

    http_method_names = ["post", "options"]
    raise_exception = True

    def test_func(self) -> bool:
        return user_may_configure_tenant_experience(self.request.user)

    def post(self, request: HttpRequest) -> HttpResponse:
        from apps.accounts.login_canvas_media import accept_login_canvas_gallery_image
        from apps.siteconfig.views_tenant_studio_hub import (
            _read_upload_bounded,
            _resolve_logo_max_bytes,
        )

        school = getattr(request, "school", None)
        if school is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "missing_tenant",
                    "error_message": "tenant context is required",
                },
                status=400,
            )

        uploaded = request.FILES.get("image") if hasattr(request, "FILES") else None
        if uploaded is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "missing_file",
                    "error_message": "image field is required",
                },
                status=400,
            )

        max_bytes = _resolve_logo_max_bytes()
        declared_size = int(getattr(uploaded, "size", 0) or 0)
        if declared_size > max_bytes:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "oversize",
                    "error_message": f"image exceeds {max_bytes // 1024} KB cap",
                },
                status=400,
            )

        image_bytes = _read_upload_bounded(uploaded, max_bytes=max_bytes)
        if image_bytes is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "oversize",
                    "error_message": f"image exceeds {max_bytes // 1024} KB cap",
                },
                status=400,
            )

        result = accept_login_canvas_gallery_image(
            school,
            image_bytes,
            original_filename=(getattr(uploaded, "name", "") or "").strip(),
        )
        if not result.ok:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                },
                status=400,
            )

        return JsonResponse(
            {
                "ok": True,
                "public_url": result.public_url,
                "storage_path": result.storage_path,
            },
            status=200,
        )
