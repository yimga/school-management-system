"""Page-personality resolver — v3.59.x Wave 11 Agent U (2026-05-22).

Maps the current request to a `data-rmc-page-personality` slug that
selects the accent palette in
`static/css/design-tokens-personality.css`. The companion context
processor (`personality_context_processor` in this module) exposes the
resolved slug as `rmc_page_personality` to every template, so any shell
template can render::

    <body data-rmc-page-personality="{{ rmc_page_personality|default:'default' }}">

Architecture:
    1. Per-view explicit override (`request.rmc_page_personality`) wins.
    2. URL-path prefix mapping — declarative table at module top.
    3. Host-kind fallback — manager => "control-plane", marketing host
       => "marketing", tenant => "tenant-admin".
    4. Hard fallback => "default".

Operator-configurable surface (Agent W wires the cockpit form):
    `SiteSettings.theme_personality` JSONField; the resolver itself
    stays read-only and side-effect-free. The cockpit form authors
    the JSON; the CSS layer consumes the keys via custom-property
    overrides composed at runtime. Resolver is unaffected — it only
    picks the SLUG; the SiteSettings JSON picks the COLORS bound to
    each slug.

This module deliberately has NO Django ORM imports — it must run
inside the template-rendering pipeline (context processor) without
triggering migrations or model loads at import time, and must
degrade gracefully when called from a test request without any
middleware state.
"""

from __future__ import annotations

import logging
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Canonical personality slugs. The set is the SOT for both the CSS file's
# `[data-rmc-page-personality="X"]` selectors and the cockpit form's
# `SiteSettings.theme_personality["personality_overrides"]` keys.
# Any addition here MUST also land in:
#   - static/css/design-tokens-personality.css   (new selector block)
#   - apps/siteconfig/forms_cockpit.py            (Agent W — form fieldset)
# =============================================================================
PERSONALITY_SLUGS: Tuple[str, ...] = (
    "control-plane",
    "tenant-admin",
    "parent",
    "student",
    "teacher",
    "marketing",
    "finance",
    "reports",
    "settings",
    "auth",
    # v4.01.35 — tenant functional-area personalities. Previously these
    # surfaces fell through to the generic "tenant-admin" indigo (or, for
    # the accounts-mounted backend, were mis-bucketed as "auth"). Each now
    # carries its own accent so a destination page signals its area.
    "academic",
    "people",
    "communication",
    "admissions",
    "default",
)

# =============================================================================
# URL-path prefix => personality slug. First match wins; ORDER MATTERS.
# Specific prefixes MUST precede generic ones (e.g. `/portal/parent/` before
# `/portal/`). Bare `/` is the catch-all marketing fallback and lives last.
# =============================================================================
_PATH_PREFIX_RULES: Tuple[Tuple[str, str], ...] = (
    # --- Operator surfaces (manager + Django admin) -------------------------
    ("/super/", "control-plane"),
    ("/admin/", "control-plane"),
    ("/manager/", "control-plane"),
    # --- Tenant per-role portals ------------------------------------------
    ("/portal/parent/", "parent"),
    ("/portal/student/", "student"),
    ("/portal/teacher/", "teacher"),
    ("/portal/backend/", "tenant-admin"),
    ("/portal/admin/", "tenant-admin"),
    ("/accounts/backend/", "tenant-admin"),
    ("/dashboard/parent/", "parent"),
    ("/dashboard/student/", "student"),
    ("/dashboard/teacher/", "teacher"),
    ("/dashboard/backend/", "tenant-admin"),
    # --- Tenant functional areas ------------------------------------------
    # The accounts app is mounted at /authentication/, so the entire tenant
    # backend (dashboard, roster, applicants) lives under /authentication/backend/.
    # These specific rules MUST precede the generic ("/authentication/", "auth")
    # rule below — otherwise the whole backend mis-resolves to the auth personality.
    ("/authentication/backend/students/", "people"),
    ("/authentication/backend/teachers/", "people"),
    ("/authentication/backend/classrooms/", "people"),
    ("/authentication/backend/alumni/", "people"),
    ("/authentication/backend/applicants/", "admissions"),
    ("/authentication/backend/", "tenant-admin"),
    ("/academics/", "academic"),
    ("/evals/", "academic"),
    ("/communication/", "communication"),
    # --- Finance / billing ------------------------------------------------
    ("/finance/", "finance"),
    ("/billing/", "finance"),
    ("/payment/", "finance"),
    ("/payments/", "finance"),
    ("/fees/", "finance"),
    # --- Reports / analytics ----------------------------------------------
    ("/reports/", "reports"),
    ("/analytics/", "reports"),
    ("/insights/", "reports"),
    # --- Settings / config ------------------------------------------------
    ("/siteconfig/", "settings"),
    ("/settings/", "settings"),
    ("/preferences/", "settings"),
    # --- Auth -------------------------------------------------------------
    ("/authentication/", "auth"),
    ("/accounts/login/", "auth"),
    ("/accounts/signup/", "auth"),
    ("/signup/", "auth"),
    ("/login/", "auth"),
    ("/logout/", "auth"),
    ("/password/", "auth"),
    # --- Marketing (public site) -----------------------------------------
    ("/marketing/", "marketing"),
    ("/public/", "marketing"),
    ("/blog/", "marketing"),
    ("/pricing/", "marketing"),
    ("/about/", "marketing"),
    ("/contact/", "marketing"),
    ("/features/", "marketing"),
)

# =============================================================================
# Host-kind fallback (consulted only when path-prefix rules don't match).
# `request.public_host_kind` is set by the host-routing middleware; we read it
# defensively (default to None) so unit-test requests without the attribute
# don't blow up.
# =============================================================================
_HOST_KIND_FALLBACKS = {
    "manager": "control-plane",
    "marketing": "marketing",
    "tenant": "tenant-admin",
}

_FALLBACK = "default"


def _normalize_slug(value: object) -> str:
    """Validate that `value` is a recognized slug; fall through otherwise."""
    if not value:
        return _FALLBACK
    slug = str(value).strip().lower()
    if slug in PERSONALITY_SLUGS:
        return slug
    return _FALLBACK


def _match_path_prefix(path: str, rules: Iterable[Tuple[str, str]] = _PATH_PREFIX_RULES) -> str:
    """Return the first slug whose prefix matches `path`, else _FALLBACK."""
    if not path:
        return _FALLBACK
    # Defensive lowercasing — operators do sometimes typo a uppercase URL.
    needle = path.lower()
    for prefix, slug in rules:
        if needle.startswith(prefix):
            return slug
    # Root path "/" is marketing (the public landing). Treat both bare-root
    # and empty as marketing so the public face always has the right accent.
    if needle in ("/", ""):
        return "marketing"
    return _FALLBACK


def resolve_page_personality(request) -> str:
    """Return the `data-rmc-page-personality` slug for this request.

    Resolution order (first match wins):
        1. Per-view explicit attribute `request.rmc_page_personality`.
        2. URL-path prefix mapping (see `_PATH_PREFIX_RULES`).
        3. Host-kind fallback (`request.public_host_kind`).
        4. Hard fallback `"default"`.

    All branches are wrapped in defensive guards because this resolver
    runs in the context-processor pipeline on every request — including
    error-page requests where `request` may be a partially-constructed
    object.
    """
    # 1. Per-view explicit override.
    try:
        explicit = getattr(request, "rmc_page_personality", None)
    except (AttributeError, RuntimeError, TypeError):
        explicit = None
    if explicit:
        normalized = _normalize_slug(explicit)
        if normalized != _FALLBACK:
            return normalized

    # 2. URL-path prefix.
    try:
        path = getattr(request, "path", "") or ""
    except (AttributeError, RuntimeError, TypeError):
        path = ""
    if path:
        prefix_slug = _match_path_prefix(path)
        if prefix_slug != _FALLBACK:
            return prefix_slug

    # 3. Host-kind fallback.
    try:
        host_kind = getattr(request, "public_host_kind", None)
    except (AttributeError, RuntimeError, TypeError):
        host_kind = None
    if host_kind:
        host_slug = _HOST_KIND_FALLBACKS.get(str(host_kind).lower())
        if host_slug:
            return host_slug

    # 4. Hard fallback.
    return _FALLBACK


def personality_context_processor(request):
    """Expose `rmc_page_personality` to every template.

    Wire into `TEMPLATES[0]["OPTIONS"]["context_processors"]` as
    `"apps.siteconfig.page_personality.personality_context_processor"`.
    """
    try:
        slug = resolve_page_personality(request)
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        # Belt-and-braces: a context-processor MUST NEVER raise. Log and
        # fall through with the safe default.
        logger.warning("page-personality resolver failed: %s", exc)
        slug = _FALLBACK
    return {
        "rmc_page_personality": slug,
        # Expose the full slug list too, so the cockpit form template
        # can iterate it without re-importing the module.
        "rmc_page_personality_slugs": PERSONALITY_SLUGS,
    }


# =============================================================================
# v3.59.x Wave 11 Agent W — operator-overridable theme personality.
# Reads ``SiteSettings.theme_personality`` (a JSONField wired by the cockpit
# form ``apps.siteconfig.forms_theme_personality.ThemePersonalityForm``) and
# emits a `<style data-rmc-personality-override>` block declaring CSS custom
# properties that override the defaults shipped in
# ``static/css/design-tokens-personality.css``.
#
# The cascade (platform default first, most-specific last):
#   1. design-tokens-personality.css                  (platform default)
#   2. platform-host SiteSettings.theme_personality   (operator override)
#   3. tenant-host  SiteSettings.theme_personality   (per-tenant override)
#
# (2) and (3) collapse to the SAME SiteSettings row in the singleton model.
# When the multi-tenant deployment fragments SiteSettings per-schema (already
# the case in this codebase via ``get_effective_site_settings``), the tenant
# branch naturally reads the tenant row and the platform branch reads the
# public-schema row — no extra cascade logic needed here.
# =============================================================================

# Hex regex copied verbatim from forms_theme_personality so this module has
# no cross-import (forms_theme_personality imports Django forms; we want the
# resolver to stay import-cheap).
_HEX_OK = __import__("re").compile(
    r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
)


def _is_valid_hex(value: object) -> bool:
    """True iff ``value`` is a string matching the hex-color contract."""
    return isinstance(value, str) and bool(_HEX_OK.match(value.strip()))


def _resolve_site_settings(request):
    """Return the per-tenant SiteSettings row, or None if unavailable.

    Mirrors the access pattern used by ``views_cockpit_admin``: try the
    tenant-aware resolver first, fall back to the singleton. All failures
    swallowed — a context processor MUST NEVER raise.
    """
    try:
        from .config_service import get_effective_site_settings

        site = get_effective_site_settings(request=request)
        if site is not None and getattr(site, "pk", None) is not None:
            return site
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass
    try:
        from .models import SiteSettings

        return SiteSettings.get_solo()
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        return None


def _build_override_css(payload: dict) -> str:
    """Render the validated JSON payload into a CSS rule string.

    The output is a sequence of `--<token>: <hex>;` declarations grouped
    by selector. NO other CSS syntax is emitted — this is the rule the
    `scan_inline_style_off_token` exemption relies on.

    Each emitted hex is re-validated here defensively; bogus values are
    silently dropped (an operator who saved before the validator landed,
    or a hand-edited JSON column, must not crash the page render).
    """
    if not isinstance(payload, dict):
        return ""

    lines: list[str] = []

    # Per-archetype accent overrides.
    overrides = payload.get("personality_overrides")
    if isinstance(overrides, dict):
        for slug, bucket in overrides.items():
            if not isinstance(bucket, dict):
                continue
            if slug not in PERSONALITY_SLUGS:
                continue
            accent = bucket.get("accent")
            if not _is_valid_hex(accent):
                continue
            lines.append(
                f'[data-rmc-page-personality="{slug}"] '
                f"{{ --personality-accent: {accent.strip()}; }}"
            )

    # Status palette — emitted at :root so every page gets the override.
    status = payload.get("status_palette")
    if isinstance(status, dict):
        status_lines: list[str] = []
        for key in ("success", "warning", "danger", "info"):
            val = status.get(key)
            if _is_valid_hex(val):
                status_lines.append(f"--status-{key}: {val.strip()};")
        if status_lines:
            lines.append(":root { " + " ".join(status_lines) + " }")

    # Heatmap palette — :root scoped.
    heatmap = payload.get("heatmap_palette")
    if isinstance(heatmap, dict):
        hm_lines: list[str] = []
        for key in ("healthy", "okay", "watch", "critical", "idle"):
            val = heatmap.get(key)
            if _is_valid_hex(val):
                hm_lines.append(f"--heatmap-{key}: {val.strip()};")
        if hm_lines:
            lines.append(":root { " + " ".join(hm_lines) + " }")

    # Chart series — :root scoped, 1-indexed token names.
    series = payload.get("chart_series")
    if isinstance(series, list):
        cs_lines: list[str] = []
        for idx, val in enumerate(series[:8], start=1):
            if _is_valid_hex(val):
                cs_lines.append(f"--chart-series-{idx}: {val.strip()};")
        if cs_lines:
            lines.append(":root { " + " ".join(cs_lines) + " }")

    return "\n".join(lines)


def resolve_personality_overrides(request) -> str:
    """Return the rendered CSS override string for the current request.

    Empty string => no overrides (template should skip rendering the
    `<style data-rmc-personality-override>` block).

    Side-effect-free; safe to call from a context processor on every
    request.
    """
    site = _resolve_site_settings(request)
    if site is None:
        return ""
    payload = getattr(site, "theme_personality", None)
    if not isinstance(payload, dict) or not payload:
        return ""
    try:
        return _build_override_css(payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("personality override CSS build failed: %s", exc)
        return ""


def personality_overrides_context_processor(request):
    """Expose ``rmc_theme_personality_overrides`` to every template.

    Wire into ``TEMPLATES[0]["OPTIONS"]["context_processors"]`` as
    ``"apps.siteconfig.page_personality.personality_overrides_context_processor"``.

    The companion partial ``templates/partials/rmc_theme_personality_overrides.html``
    consumes the value and emits the `<style>` block in the page head.
    """
    try:
        css = resolve_personality_overrides(request)
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        # A context-processor MUST NEVER raise.
        logger.warning("personality overrides processor failed: %s", exc)
        css = ""
    return {"rmc_theme_personality_overrides": css}
