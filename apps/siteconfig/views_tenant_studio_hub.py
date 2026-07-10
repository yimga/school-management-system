"""Tenant School Studio — single launch-oriented operating hub (tenant host)."""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.lifecycle.tenant_school_resolve import (
    can_access_tenant_lifecycle,
    lifecycle_access_denied_response,
    require_tenant_lifecycle_school,
    resolve_request_school,
)
from apps.platform_runtime.customer_health import (
    calculate_school_health,
    get_school_health_recommendations,
)
from apps.platform_runtime.onboarding import get_school_onboarding_progress
from apps.lifecycle.launch_rail import build_launch_rail_payload
from apps.lifecycle.unified_lifecycle import resolve_unified_lifecycle
from apps.lifecycle.wind_down import is_wind_down_mode
from apps.platform_runtime.tenant_onboarding_operator_direction import launch_lanes_for_template
from apps.siteconfig.tenant_studio_day1 import Day1MagicService
from apps.siteconfig.tenant_studio_hub_context import build_studio_ai_context
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)

logger = logging.getLogger(__name__)


def _tenant_reverse(name: str) -> str:
    try:
        return reverse(name, urlconf="config.tenant_urls")
    except NoReverseMatch:
        return reverse(name)


def _siteconfig_reverse(name: str) -> str:
    """Resolve a ``siteconfig:`` URL name preferring the tenant urlconf."""
    full = f"siteconfig:{name}" if not name.startswith("siteconfig:") else name
    try:
        return reverse(full, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            return reverse(full)
        except NoReverseMatch:
            return ""


@login_required
def school_studio_hub(request: HttpRequest) -> HttpResponse:
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return lifecycle_access_denied_response(request)

    # Day-1 Magic gate: first-time visitors with no palette locked are
    # redirected into the 3-act sequence. Operators can opt out via
    # ``?skip_day1=1`` (one-shot) or via the reset endpoint after launch.
    if Day1MagicService.is_day1_required(school):
        if request.GET.get("skip_day1") != "1":
            target = _siteconfig_reverse("tenant_studio_day1_act1")
            if target:
                return HttpResponseRedirect(target)

    progress = get_school_onboarding_progress(school, user=request.user)
    health = calculate_school_health(school)
    recommendations = get_school_health_recommendations(school, user=request.user)

    blockers: list[str] = []
    if int(progress.get("percent") or 0) < 50:
        blockers.append(_("Activation checklist below 50% — complete essentials first."))
    status = (health.get("status") or "").strip()
    if status in ("setup_needed", "at_risk"):
        blockers.append(_("School health is %(status)s — review recommended steps.") % {"status": status})

    launch_ready = int(progress.get("percent") or 0) >= 80 and status not in ("setup_needed",)
    unified = resolve_unified_lifecycle(school)
    launch_rail = build_launch_rail_payload(school, user=request.user)
    if launch_rail.get("launch_ready"):
        launch_ready = True
    ai_ctx = build_studio_ai_context(
        request,
        school=school,
        progress=progress,
        blockers=blockers,
    )

    return render_siteconfig_stem(
        request,
        "tenant_studio_hub",
        {
            "school": school,
            "onboarding": progress,
            "health": health,
            "health_recommendations": recommendations,
            "launch_lanes": launch_lanes_for_template(),
            "launch_rail": launch_rail,
            "unified_lifecycle": unified,
            "wind_down_mode": is_wind_down_mode(school),
            "launch_blockers": blockers,
            "launch_ready": launch_ready,
            "readiness_score": health.get("score"),
            "readiness_status": health.get("status"),
            "studio_link_urls": _studio_hub_link_urls(),
            "day1_required": False,
            "day1_reset_url": _siteconfig_reverse("tenant_studio_day1_reset"),
            **ai_ctx,
        },
        cp_title=_("School Studio"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("School Studio"), active=True),
        ),
    )


def _studio_hub_link_urls() -> dict[str, str]:
    """Pre-resolve tenant URLs so templates never call {% url %} against root urlconf."""
    specs = (
        ("onboarding", "siteconfig:onboarding"),
        ("provisioning", "tenant_provisioning_status"),
        ("fast_path", "tenant_launch_fast_path"),
        ("lifecycle", "tenant_lifecycle_command_center"),
        ("studio_os", "studio_os:shell"),
        ("school_help_ai", "school_help_ai"),
        ("help_center", "feedback:help_center"),
        ("offboarding", "tenant_offboarding"),
    )
    return {key: _tenant_reverse(name) for key, name in specs}


@login_required
def school_studio_redirect_setup(request: HttpRequest) -> HttpResponse:
    return HttpResponseRedirect(_tenant_reverse("siteconfig:onboarding"))


@login_required
def school_studio_redirect_migration(request: HttpRequest) -> HttpResponse:
    return HttpResponseRedirect(_tenant_reverse("school_setup_imports"))


@login_required
def school_studio_redirect_help(request: HttpRequest) -> HttpResponse:
    return HttpResponseRedirect(_tenant_reverse("school_help_ai"))


@login_required
def school_studio_redirect_launch(request: HttpRequest) -> HttpResponse:
    return HttpResponseRedirect(_tenant_reverse("siteconfig:guided_onboarding"))


# ---------------------------------------------------------------------------
# Day-1 Magic — Act 1 / Act 2 / Act 3 / Reset views
# ---------------------------------------------------------------------------


def _require_tenant_operator(request: HttpRequest):
    """Return ``(school, None)`` when allowed, ``(None, HttpResponseForbidden)`` otherwise."""
    return require_tenant_lifecycle_school(request)


class TenantStudioDay1Act1View(LoginRequiredMixin, View):
    """Act 1 — Brand Extraction.

    GET renders the animated brand reveal partial. The brand seed is resolved
    via :meth:`Day1MagicService.resolve_brand_seed` (which is lazy on E1's
    ``services.theme_intelligence`` import and falls back deterministically).
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        school, denied = _require_tenant_operator(request)
        if denied is not None:
            return denied

        seed = Day1MagicService.resolve_brand_seed(school)
        act2_url = _siteconfig_reverse("tenant_studio_day1_act2")
        cockpit_url = _tenant_reverse("school_studio")
        logo_upload_url = _siteconfig_reverse("tenant_studio_day1_act1_logo_upload")

        # Prefer the inline data URI (renders without media serving) so a
        # previously uploaded logo shows on reload even on hosts without object
        # storage. Falls back to the stored URL for served-media deployments.
        _branding_meta = getattr(school, "branding_metadata", None) or {}
        logo_display_url = _branding_meta.get("logo_data_uri") or getattr(
            school, "logo_url", ""
        )

        return render(
            request,
            "siteconfig/partials/tenant_studio_day1_act1_brand.html",
            {
                "school": school,
                "seed_hex": seed["seed_hex"],
                "seed_source": seed["source"],
                "act2_url": act2_url,
                "cockpit_url": cockpit_url,
                "skip_url": f"{cockpit_url}?skip_day1=1",
                "logo_upload_url": logo_upload_url,
                "logo_display_url": logo_display_url,
                "active_act": 1,
            },
        )


class TenantStudioDay1Act2View(LoginRequiredMixin, View):
    """Act 2 — Palette Generation.

    GET returns three variations rendered on simulated tiles. POST accepts a
    fresh ``seed_hex`` (e.g. operator picked a different colour after the
    Act-1 reveal) and re-generates against that seed; the new seed is NOT
    persisted to the School row until Act 3 fires.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request)

    def post(self, request: HttpRequest) -> HttpResponse:
        return self._render(request)

    def _render(self, request: HttpRequest) -> HttpResponse:
        school, denied = _require_tenant_operator(request)
        if denied is not None:
            return denied

        variations = Day1MagicService.generate_variations(school, request=request)
        seed = Day1MagicService.resolve_brand_seed(school)
        act3_url = _siteconfig_reverse("tenant_studio_day1_act3_lock")
        act1_url = _siteconfig_reverse("tenant_studio_day1_act1")
        return render(
            request,
            "siteconfig/partials/tenant_studio_day1_act2_palette.html",
            {
                "school": school,
                "variations": [
                    {
                        "id": v.id,
                        "tone": v.tone,
                        "stops": v.stops,
                        "preview_targets": v.preview_targets,
                        "wcag_grade": v.wcag_grade,
                    }
                    for v in variations
                ],
                "seed_hex": seed["seed_hex"],
                "seed_source": seed["source"],
                "act1_url": act1_url,
                "act3_url": act3_url,
                "active_act": 2,
            },
        )


class TenantStudioDay1Act3LockView(LoginRequiredMixin, View):
    """Act 3 — Lock-In.

    POST ``variation_id`` to commit the operator's pick. The service refuses
    any ``variation_id`` that wasn't minted for the current ``request.school``
    — this is the cross-tenant guard the spec calls out.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        school, denied = _require_tenant_operator(request)
        if denied is not None:
            return denied

        variation_id = (request.POST.get("variation_id") or "").strip()
        if not variation_id:
            return JsonResponse({"ok": False, "error": "variation_id is required"}, status=400)

        try:
            Day1MagicService.lock_palette_choice(
                school,
                variation_id,
                by_user=getattr(request, "user", None),
            )
        except ValueError as exc:
            # Don't echo the variation_id back — it's caller-controlled and a
            # cross-tenant POST attempt should not leak the rejected id.
            return JsonResponse({"ok": False, "error": str(exc)}, status=403)

        cockpit_url = _tenant_reverse("school_studio")
        if request.headers.get("Accept", "").startswith("application/json"):
            return JsonResponse({"ok": True, "redirect": cockpit_url})

        return render(
            request,
            "siteconfig/partials/tenant_studio_day1_act3_lock.html",
            {
                "school": school,
                "cockpit_url": cockpit_url,
                "locked": True,
                "active_act": 3,
            },
        )


class TenantStudioDay1Act1LogoUploadView(LoginRequiredMixin, View):
    """Act 1 — live logo upload.

    POST ``multipart/form-data`` with a single field ``logo``. Returns JSON
    in both the success and validation-failure paths so the JS handler can
    update the DOM without a page reload.

    Guarantees (defense-in-depth):
      * CSRF protected — we deliberately do NOT wrap this view in
        ``@csrf_exempt``; the upload widget posts the CSRF token under
        ``X-CSRFToken`` + the hidden form input.
      * Tenant resolved from ``request.school`` ONLY — never from the POST
        body — so a cross-tenant POST cannot land bytes under a foreign
        tenant's prefix.
      * Size pre-check before reading the full file into memory (chunk
        scan against ``settings.MAX_LOGO_UPLOAD_BYTES`` /
        ``DAY1_DEFAULT_LOGO_MAX_BYTES`` fallback).
      * MIME sniffed by ``LogoUploadValidator`` on magic bytes — the
        operator's declared ``content_type`` and filename extension are
        deliberately ignored.

    # rbac-allow: tenant-admin-or-staff-day1-logo-upload
    """

    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest) -> HttpResponse:
        school, denied = _require_tenant_operator(request)
        if denied is not None:
            return denied

        uploaded = request.FILES.get("logo") if hasattr(request, "FILES") else None
        if uploaded is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "missing_file",
                    "error_message": "logo field is required",
                },
                status=400,
            )

        # Accept large logos up to an absolute ceiling and let the service
        # shrink them (see Day1MagicService.accept_logo_upload). Only a file
        # bigger than the absolute ceiling is rejected outright — everything
        # else is auto-resized rather than refused.
        max_bytes = _resolve_logo_absolute_max_bytes()
        declared_size = int(getattr(uploaded, "size", 0) or 0)
        if declared_size > max_bytes:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "oversize",
                    "error_message": f"logo is too large — keep it under {max_bytes // (1024 * 1024)} MB"  # magic-number-allow: bytes-to-megabytes-display-divisor,
                },
                status=400,
            )

        image_bytes = _read_upload_bounded(uploaded, max_bytes=max_bytes)
        if image_bytes is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error_code": "oversize",
                    "error_message": f"logo is too large — keep it under {max_bytes // (1024 * 1024)} MB"  # magic-number-allow: bytes-to-megabytes-display-divisor,
                },
                status=400,
            )

        original_filename = (getattr(uploaded, "name", "") or "").strip()
        # The filename is never trusted for MIME — it's audit-trail only.
        result = Day1MagicService.accept_logo_upload(
            school,
            image_bytes,
            original_filename,
            by_user=getattr(request, "user", None),
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
                "logo_url": result.logo_url,
                "seed_hex": result.seed_hex,
                "source": result.source,
                "dominant_colors": list(result.dominant_colors),
                "resized": bool(result.resized),
                "notice": (
                    "Your logo was large, so we resized it to fit. "
                    "It's saved and shown above."
                    if result.resized
                    else ""
                ),
            },
            status=200,
        )


def _resolve_logo_max_bytes() -> int:
    """Pull the upload cap from Django settings with a stable fallback."""
    from django.conf import settings as django_settings

    from apps.siteconfig.tenant_studio_day1 import DAY1_DEFAULT_LOGO_MAX_BYTES

    return int(
        getattr(django_settings, "MAX_LOGO_UPLOAD_BYTES", DAY1_DEFAULT_LOGO_MAX_BYTES)
        or DAY1_DEFAULT_LOGO_MAX_BYTES
    )


def _resolve_logo_absolute_max_bytes() -> int:
    """Absolute ceiling for the raw upload before auto-resize kicks in.

    Oversized-but-under-ceiling logos are accepted and shrunk to
    ``DAY1_LOGO_MAX_DIMENSION`` rather than rejected; only a file bigger than
    this ceiling is refused (memory / DoS bound). Settings-overridable via
    ``MAX_LOGO_UPLOAD_ABSOLUTE_BYTES``; defaults to 15 MB.
    """
    from django.conf import settings as django_settings

    default = 15 * 1024 * 1024  # magic-number-allow: settings-driven-logo-cap-fifteen-megabyte-fallback
    return int(
        getattr(django_settings, "MAX_LOGO_UPLOAD_ABSOLUTE_BYTES", default) or default
    )


def _read_upload_bounded(uploaded, *, max_bytes: int) -> bytes | None:
    """Read at most ``max_bytes + 1`` bytes from ``uploaded`` in chunks.

    Returns ``None`` when the read exceeds ``max_bytes`` (so the caller can
    return a clean ``oversize`` error without ever materializing the rest
    of a malicious large upload). Honors both Django's chunked ``chunks()``
    iterator and a plain ``read()`` fallback.
    """
    chunks_iter = getattr(uploaded, "chunks", None)
    buf = bytearray()
    if callable(chunks_iter):
        for chunk in chunks_iter():
            buf.extend(chunk)
            if len(buf) > max_bytes:
                return None
        return bytes(buf)
    raw = uploaded.read()
    if raw is None:
        return b""
    if len(raw) > max_bytes:
        return None
    return raw


class TenantStudioDay1ResetView(LoginRequiredMixin, View):
    """Reset the Day-1 marker so the operator can re-run the brand session.

    Staff and tenant_admin operators are allowed; everyone else is rejected.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        school, denied = _require_tenant_operator(request)
        if denied is not None:
            return denied

        user = getattr(request, "user", None)
        is_allowed = bool(getattr(user, "is_staff", False)) or bool(
            getattr(user, "is_superuser", False)
        )
        if not is_allowed:
            role = (getattr(user, "role", "") or "").strip().upper()
            # role-string-allow: day1-reset-tenant-admin-comparison-against-user.role
            if role in ("ADMIN", "SUPERADMIN", "TENANT_ADMIN"):
                is_allowed = True
        if not is_allowed:
            return HttpResponseForbidden("Day-1 reset requires staff or tenant_admin role.")

        Day1MagicService.reset_day1(school, by_user=user)
        target = _siteconfig_reverse("tenant_studio_day1_act1") or _tenant_reverse("school_studio")
        return HttpResponseRedirect(target)
