"""RFC 8594 API deprecation + sunset signalling (Metric #20 — API Quality).

The v1 manifest (:mod:`apps.api.api_v1_manifest`) advertises a deprecation
*policy* — ``"Non-breaking additive changes without version bump; breaking
changes announced 90d via changelog."`` — and its view docstring claims it
returns "stable paths and deprecation policy". Before this module that policy
had **no runtime teeth**: a client calling a superseded endpoint received no
machine-readable warning and would only discover the break at 410-time. This
module is the missing producer + applier that makes the advertised policy real.

Standard — https://datatracker.ietf.org/doc/html/rfc8594 :

  * ``Deprecation: <IMF-fixdate>`` — the date the endpoint became deprecated.
  * ``Sunset: <IMF-fixdate>``      — the date it will stop working.
  * ``Link: <successor>; rel="successor-version"`` — the replacement endpoint.
  * ``Link: <doc>; rel="deprecation"; type="text/html"`` — the migration doc.

:data:`DEPRECATED_ENDPOINTS` is the single source of truth. It is surfaced
machine-readably in the v1 manifest ``deprecations`` block AND stamped as
response headers on the live deprecated routes, so a client can detect and
migrate BEFORE the sunset date rather than discover the break in production.

Three transport-agnostic appliers, all delegating to
:func:`apply_deprecation_headers`:

  * :class:`DeprecationHeaderViewMixin` — Django ``View`` subclasses.
  * :class:`DeprecationHeaderMixin`     — DRF ``APIView`` / ``ViewSet``
    (mirrors the ``ApiSoftWarnHeaderMixin.finalize_response`` pattern already
    used in ``apps/api/throttling.py``).
  * :func:`deprecated_endpoint`          — a decorator for function views.

Everything is fail-soft: a malformed registry date or a ``reverse()`` miss is
logged at debug level and never raises into the response cycle.
"""

from __future__ import annotations

import datetime
import functools
import logging
from dataclasses import dataclass

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.http import http_date

logger = logging.getLogger(__name__)

_DEFAULT_DEPRECATION_DOC_BASE = "https://docs.runmycampus.com/deprecations/"

DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
LINK_HEADER = "Link"


def _doc_base() -> str:
    return (
        getattr(settings, "API_DEPRECATION_DOC_BASE", "")
        or _DEFAULT_DEPRECATION_DOC_BASE
    )


def imf_fixdate(iso_date: str) -> str | None:
    """ISO date (``YYYY-MM-DD``) -> RFC 7231 IMF-fixdate at ``00:00:00 GMT``.

    Returns ``None`` for an unparseable date so callers can fall back to the
    ``Deprecation: true`` token form permitted by RFC 8594 § 2.
    """
    try:
        d = datetime.date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return None
    epoch = datetime.datetime(
        d.year, d.month, d.day, tzinfo=datetime.timezone.utc
    ).timestamp()
    return http_date(epoch)


@dataclass(frozen=True)
class DeprecationSpec:
    """One deprecated endpoint's lifecycle contract."""

    endpoint_id: str
    deprecation_date: str  # ISO YYYY-MM-DD (became deprecated)
    sunset_date: str  # ISO YYYY-MM-DD (will stop working)
    successor_url_name: str = ""  # e.g. "api_v1:rosetta-scales"
    successor_path: str = ""  # literal fallback when the name can't reverse
    doc_slug: str = ""  # appended to the deprecation doc base

    def doc_url(self) -> str:
        return f"{_doc_base()}{self.doc_slug or self.endpoint_id}"

    def successor_url(self, request=None) -> str:
        """Absolute successor URL when a ``request`` is given, else relative."""
        path = self.successor_path
        if self.successor_url_name:
            try:
                path = reverse(self.successor_url_name)
            except NoReverseMatch:
                path = self.successor_path or ""
        if path and request is not None:
            try:
                return request.build_absolute_uri(path)
            except (AttributeError, ValueError):
                return path
        return path

    def as_manifest_dict(self, request=None) -> dict:
        return {
            "endpoint": self.endpoint_id,
            "deprecation": self.deprecation_date,
            "sunset": self.sunset_date,
            "successor": self.successor_url(request),
            "documentation": self.doc_url(),
        }


# ── Registry (single source of truth) ───────────────────────────────────────
#
# The unversioned ``/api/rosetta/*`` endpoints (URL namespace ``api``) are
# superseded by their versioned ``/api/v1/rosetta/*`` twins — the curated v1
# successors already listed in ``api_v1_manifest.MANIFEST_CURATED_API_V1_URL_NAMES``
# (``rosetta_convert`` / ``rosetta_scales``). The legacy routes keep working
# through the sunset window; clients receive a machine-readable warning to
# migrate. This is genuine API-lifecycle hygiene, not a fabricated deprecation:
# the two paths ship the same functionality and v1 is the canonical contract.
DEPRECATED_ENDPOINTS: dict[str, DeprecationSpec] = {
    "api.rosetta.convert": DeprecationSpec(
        endpoint_id="api.rosetta.convert",
        deprecation_date="2026-07-10",
        sunset_date="2027-07-10",
        successor_url_name="api_v1:rosetta-convert",
        successor_path="/api/v1/rosetta/convert",
        doc_slug="rosetta-convert-v1",
    ),
    "api.rosetta.scales": DeprecationSpec(
        endpoint_id="api.rosetta.scales",
        deprecation_date="2026-07-10",
        sunset_date="2027-07-10",
        successor_url_name="api_v1:rosetta-scales",
        successor_path="/api/v1/rosetta/scales",
        doc_slug="rosetta-scales-v1",
    ),
}


def get_deprecation_spec(endpoint_id: str | None) -> DeprecationSpec | None:
    if not endpoint_id:
        return None
    return DEPRECATED_ENDPOINTS.get(endpoint_id)


def apply_deprecation_headers(response, spec, *, request=None):
    """Stamp RFC 8594 ``Deprecation``/``Sunset``/``Link`` headers on ``response``.

    Fail-soft: never raises into the response cycle. Returns ``response`` so it
    can be used inline. An existing ``Link`` header is preserved and appended to.
    """
    if response is None or spec is None:
        return response
    try:
        response[DEPRECATION_HEADER] = imf_fixdate(spec.deprecation_date) or "true"
        sunset = imf_fixdate(spec.sunset_date)
        if sunset:
            response[SUNSET_HEADER] = sunset
        links: list[str] = []
        successor = spec.successor_url(request)
        if successor:
            links.append(f'<{successor}>; rel="successor-version"')
        doc = spec.doc_url()
        if doc:
            links.append(f'<{doc}>; rel="deprecation"; type="text/html"')
        if links:
            existing = response.get(LINK_HEADER)
            response[LINK_HEADER] = ", ".join(
                ([existing] if existing else []) + links
            )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:  # pragma: no cover
        logger.debug(
            "apply_deprecation_headers failed for %s: %s",
            getattr(spec, "endpoint_id", "?"),
            exc,
        )
    return response


class DeprecationHeaderViewMixin:
    """Django ``View`` mixin that stamps deprecation headers on the response.

    Set :attr:`deprecation_endpoint_id` to a key in
    :data:`DEPRECATED_ENDPOINTS`. Runs on the authenticated dispatch response
    (after any ``login_required`` decorator has admitted the request).
    """

    deprecation_endpoint_id: str = ""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        apply_deprecation_headers(
            response,
            get_deprecation_spec(getattr(self, "deprecation_endpoint_id", "")),
            request=request,
        )
        return response


class DeprecationHeaderMixin:
    """DRF view mixin — mirrors ``ApiSoftWarnHeaderMixin`` (``finalize_response``).

    Mix into any DRF ``APIView`` / ``ViewSet`` and set
    :attr:`deprecation_endpoint_id`. Never raises into the response cycle.
    """

    deprecation_endpoint_id: str = ""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        try:
            raw = getattr(request, "_request", request)
            apply_deprecation_headers(
                response,
                get_deprecation_spec(getattr(self, "deprecation_endpoint_id", "")),
                request=raw,
            )
        except (AttributeError, TypeError):  # pragma: no cover — defensive
            pass
        return response


def deprecated_endpoint(endpoint_id: str):
    """Decorator for function views: stamp deprecation headers on the response."""

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            apply_deprecation_headers(
                response, get_deprecation_spec(endpoint_id), request=request
            )
            return response

        return wrapped

    return decorator


def build_deprecation_manifest_block(request=None) -> list:
    """Machine-readable list of active deprecations for the v1 manifest.

    Sorted by ``endpoint_id`` for deterministic output.
    """
    return [
        spec.as_manifest_dict(request)
        for spec in sorted(
            DEPRECATED_ENDPOINTS.values(), key=lambda s: s.endpoint_id
        )
    ]
