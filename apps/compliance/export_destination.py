"""Resolve operator export destination region for cross-border gates."""

from __future__ import annotations

from typing import Any


def _client_country_code(request: Any) -> str:
    """ISO-3166 alpha-2 country of the requesting operator, or ``""`` if unknowable.

    Where a downloaded export physically GOES is the operator's own location — a
    CSV lands wherever the person clicking the download button is. We read that
    from the edge proxy's client-country header first (Cloudflare stamps
    ``CF-IPCountry`` with no GeoIP DB required; an operator on a different proxy
    points us at its header via ``settings.DATA_RESIDENCY_CLIENT_COUNTRY_HEADER``),
    then fall back to a GeoIP lookup on the client IP. Returns ``""`` when nothing
    resolves — an unknown destination stays unknown and the gate decides.
    """
    if request is None:
        return ""
    meta = getattr(request, "META", None) or {}

    # 1. Edge-proxy client-country header (zero-config behind Cloudflare).
    header_keys = ["HTTP_CF_IPCOUNTRY"]
    try:
        from django.conf import settings

        configured = getattr(settings, "DATA_RESIDENCY_CLIENT_COUNTRY_HEADER", None)
    except Exception:  # noqa: BLE001 — settings read must never break the export path
        configured = None
    if configured:
        # "X-Country" -> WSGI "HTTP_X_COUNTRY"; take precedence over the default.
        header_keys.insert(0, "HTTP_" + str(configured).upper().replace("-", "_"))
    for key in header_keys:
        raw = str(meta.get(key) or "").strip().upper()
        # Cloudflare uses "XX" (unknown) / "T1" (Tor) as non-country sentinels.
        if len(raw) == 2 and raw.isalpha() and raw not in ("XX", "T1"):
            return raw

    # 2. GeoIP on the client IP (returns "" on hosts with no GeoIP DB, e.g. Render).
    #    Read from the outermost TRUSTED proxy hop: X-Forwarded-For is
    #    client-controlled to the LEFT, so a leftmost read let the caller pick
    #    the country this residency decision is made against.
    from types import SimpleNamespace

    from apps.api.rate_limit import client_ip as _trusted_client_ip

    ip = _trusted_client_ip(SimpleNamespace(META=meta))
    if ip == "unknown":
        ip = ""
    if ip:
        try:
            from apps.compliance.access_control import get_country_from_ip

            code = str(get_country_from_ip(ip) or "").strip().upper()
            if len(code) == 2 and code.isalpha():
                return code
        except Exception:  # noqa: BLE001 — GeoIP is best-effort; unknown stays unknown
            return ""
    return ""


def _operator_request_region(request: Any) -> str:
    """The data region the requesting operator sits in, or ``""`` when unknowable.

    Maps the operator's client country (:func:`_client_country_code`) to a
    canonical data region via the same country→region table the platform uses to
    derive a school's own region, so both sides of the cross-border comparison
    speak one region vocabulary.
    """
    country = _client_country_code(request)
    if not country:
        return ""
    try:
        from apps.schools.data_residency import derive_default_region

        return str(derive_default_region(country) or "").strip().lower()
    except Exception:  # noqa: BLE001 — region derivation must never break the export
        return ""


def resolve_export_destination_region(
    *,
    request: Any = None,
    params: dict | None = None,
) -> str:
    """Where the export is going, or ``""`` when that is not knowable.

    Precedence:

    1. explicit ``params['destination_region']`` / ``['dest_region']`` — a
       programmatic/API override naming the target region directly;
    2. ``request.tenant_runtime.compliance.export_restrictions`` — a residency
       policy the tenant configured (``destination_region`` / ``active_region``);
    3. ``request.data_region`` / ``request.active_data_region`` — a region an
       upstream layer pinned onto the request;
    4. **the requesting operator's own region** — a downloaded CSV physically
       goes to the operator's machine, so the operator's edge-resolved country
       (Cloudflare / configured proxy header, else GeoIP) mapped to a data region
       IS the export's true destination. This is the arm that fires on the real
       download path, where ``params`` carries only ``academic_year_id``.

    Takes no ``school`` ON PURPOSE. It used to, and fell back to that school's
    own ``data_region`` — answering "the destination is wherever the data
    already is". That made every cross-border check a comparison of a region to
    ITSELF, structurally unable to block, and it simultaneously made the gate's
    ``if not dest`` branch (which exists for exactly this case) unreachable,
    because ``dest`` was never empty. The source region is not evidence about
    the destination, so this resolver cannot see it.

    ``""`` means unknown, and what to do about an unknown destination is the
    gate's decision, not this resolver's: ``cross_border_export_blocked``
    consults ``strict_unknown_regions()``, which defaults to the
    backward-compatible posture of letting it pass.
    """
    params = params or {}
    explicit = (params.get("destination_region") or params.get("dest_region") or "").strip()
    if explicit:
        return explicit.lower()

    if request is not None:
        runtime = getattr(request, "tenant_runtime", None)
        if runtime is not None:
            compliance = getattr(runtime, "compliance", None)
            if compliance is not None:
                restrictions = getattr(compliance, "export_restrictions", None) or {}
                if isinstance(restrictions, dict):
                    dest = (
                        restrictions.get("destination_region")
                        or restrictions.get("active_region")
                        or ""
                    )
                    if dest:
                        return str(dest).strip().lower()

        req_region = getattr(request, "data_region", None) or getattr(
            request, "active_data_region", None
        )
        if req_region:
            return str(req_region).strip().lower()

        # The download lands wherever the operator is: that is the destination.
        operator_region = _operator_request_region(request)
        if operator_region:
            return operator_region

    return ""
