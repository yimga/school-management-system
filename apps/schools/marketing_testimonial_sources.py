"""Multi-source testimonial registry + provider framework for the marketing platform.

This module is the SOURCE-OF-TRUTH registry and provider layer that sits behind
``apps.siteconfig.models_marketing_testimonial.MarketingTestimonial``. It answers
two questions honestly:

1. *Which sources of social proof is the platform allowed to surface?*
   (the :class:`TestimonialSource` registry + :func:`configured_sources`)
2. *Where does the testimonial content actually come from at render time?*
   (the :class:`TestimonialProvider` protocol + the concrete providers)

HONESTY CONTRACT — read before editing
=======================================
- The ONLY live, display-ready provider is :class:`ManualDBProvider`. It reads
  rows that an operator has DELIBERATELY approved (``is_approved=True`` +
  ``is_active=True``). Nothing else ever reaches a public surface directly.
- The external connectors (G2 / Capterra / Trustpilot / Google Business /
  LinkedIn) are CREDENTIAL-GATED and APPROVAL-GATED. When enabled AND supplied
  with real API credentials, they fetch reviews from the respective platform's
  API, NORMALIZE them to the model shape, and are designed to CREATE UNAPPROVED
  rows (``ingested_from_source=True``, ``is_approved=False``) so they land in an
  operator approval queue. They NEVER auto-approve and NEVER render directly.
- Because we do not ship third-party API credentials, every external connector's
  :meth:`fetch` is written with the REAL request shape but guarded so it cleanly
  no-ops (returns ``[]``, logs at DEBUG) until credentials are configured. They
  NEVER fabricate content. The exact ``ServiceIntegration`` config key + API
  endpoint each connector expects is documented on the class.
- External review-platform Terms of Service vary on display/scraping rights.
  Enabling a connector is a deliberate operator action that asserts ToS review
  has happened. Defaults keep all external platforms OFF.

Credential resolution convention
=================================
``ServiceIntegration`` (``apps.siteconfig.models_platform_catalog``) is per-school
(tenant) and marketing is platform-global, so the primary credential path for
these connectors is ENVIRONMENT settings, read via ``getattr(settings, ...)``,
mirroring the rest of the platform's connector configuration. Each connector
documents the env keys it reads. An operator MAY also stash credentials in a
``ServiceIntegration`` row whose ``connector_slug`` matches the documented slug;
:func:`service_integration_config` is the (lazy, best-effort) helper for that.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TestimonialSource:
    """One registered provenance source for marketing testimonials.

    Mirrors a member of
    ``apps.siteconfig.models_marketing_testimonial.MarketingTestimonial.Source``.

    Attributes:
        key:               stable source key (matches the model ``Source`` value).
        display_label:     human label for operator UIs.
        badge_label:       short attribution badge for the public surface
                           (e.g. ``"via G2"``).
        default_enabled:   whether this source is surfaced by default. Only the
                           first-party sources we control end-to-end
                           (DIRECT / CASE_STUDY / PRESS) default ON; every
                           external review platform defaults OFF.
        requires_credentials: whether an external API credential is required to
                           INGEST from this source. First-party sources are
                           operator-entered (no credential).
    """

    key: str
    display_label: str
    badge_label: str
    default_enabled: bool
    requires_credentials: bool


# Keyed by source key (which equals the model ``Source`` value). Every member of
# the model's ``Source`` TextChoices MUST have an entry here — the test suite
# asserts a badge_label exists for every model source choice.
_SOURCE_REGISTRY: Dict[str, TestimonialSource] = {
    "DIRECT": TestimonialSource(
        key="DIRECT",
        display_label="Direct (collected by RunMyCampus)",
        badge_label="Verified customer",
        default_enabled=True,
        requires_credentials=False,
    ),
    "CASE_STUDY": TestimonialSource(
        key="CASE_STUDY",
        display_label="Case study",
        badge_label="From a case study",
        default_enabled=True,
        requires_credentials=False,
    ),
    "PRESS": TestimonialSource(
        key="PRESS",
        display_label="Press / media",
        badge_label="As featured in the press",
        default_enabled=True,
        requires_credentials=False,
    ),
    "G2": TestimonialSource(
        key="G2",
        display_label="G2",
        badge_label="via G2",
        default_enabled=False,
        requires_credentials=True,
    ),
    "CAPTERRA": TestimonialSource(
        key="CAPTERRA",
        display_label="Capterra",
        badge_label="via Capterra",
        default_enabled=False,
        requires_credentials=True,
    ),
    "GOOGLE": TestimonialSource(
        key="GOOGLE",
        display_label="Google",
        badge_label="via Google",
        default_enabled=False,
        requires_credentials=True,
    ),
    "TRUSTPILOT": TestimonialSource(
        key="TRUSTPILOT",
        display_label="Trustpilot",
        badge_label="via Trustpilot",
        default_enabled=False,
        requires_credentials=True,
    ),
    "LINKEDIN": TestimonialSource(
        key="LINKEDIN",
        display_label="LinkedIn",
        badge_label="via LinkedIn",
        default_enabled=False,
        requires_credentials=True,
    ),
    "OTHER": TestimonialSource(
        key="OTHER",
        display_label="Other",
        badge_label="Customer",
        default_enabled=False,
        requires_credentials=False,
    ),
}


def all_sources() -> List[TestimonialSource]:
    """Return every registered source, registry-declaration order."""

    return list(_SOURCE_REGISTRY.values())


def get_source(key: str) -> Optional[TestimonialSource]:
    """Return the registered :class:`TestimonialSource` for ``key`` or ``None``."""

    if not key:
        return None
    return _SOURCE_REGISTRY.get(key.strip().upper())


def badge_label_for(key: str) -> str:
    """Return the public attribution badge for ``key`` (empty when unknown)."""

    source = get_source(key)
    return source.badge_label if source else ""


def _default_enabled_keys() -> List[str]:
    """Source keys that are enabled when no explicit configuration is present."""

    return [s.key for s in _SOURCE_REGISTRY.values() if s.default_enabled]


def _truthy(value: object) -> bool:
    """Common env-string truthiness used across the platform."""

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_setting(name: str, default: object = None) -> object:
    """Read a Django setting, falling back to ``os.environ`` then ``default``.

    Lazy-imports ``django.conf.settings`` so this module stays importable in
    contexts where Django isn't fully configured (e.g. ``ast`` parse / tooling).
    """

    try:
        from django.conf import settings

        if hasattr(settings, name):
            return getattr(settings, name)
    except Exception:  # noqa: BLE001 — never let settings access break the registry
        logger.debug("settings unavailable while reading %s", name, exc_info=True)
    return os.environ.get(name, default)


def configured_sources() -> List[str]:
    """Return the list of ENABLED source keys.

    Configuration contract (most specific wins):

    1. ``RMC_MARKETING_TESTIMONIAL_SOURCES`` — a CSV of source keys
       (e.g. ``"DIRECT,CASE_STUDY,G2"``). When set (non-empty), it is the
       authoritative allow-list; only the listed, registered keys are enabled.
    2. Otherwise, per-source override ``RMC_TESTIMONIAL_SOURCE_<KEY>_ENABLED``
       (truthy/falsy) flips an individual source on or off relative to its
       registry default.
    3. Otherwise, a source is enabled iff its registry ``default_enabled`` is
       True (DIRECT / CASE_STUDY / PRESS only).

    Unknown keys in the CSV are ignored (logged at DEBUG). Order follows the
    registry declaration order so callers get a stable, deterministic list.
    """

    csv_value = _read_setting("RMC_MARKETING_TESTIMONIAL_SOURCES", "")
    csv_text = str(csv_value or "").strip()

    if csv_text:
        requested = {
            part.strip().upper() for part in csv_text.split(",") if part.strip()
        }
        enabled = []
        for key in _SOURCE_REGISTRY:
            if key in requested:
                enabled.append(key)
        for unknown in requested - set(_SOURCE_REGISTRY):
            logger.debug(
                "ignoring unknown testimonial source key in "
                "RMC_MARKETING_TESTIMONIAL_SOURCES: %s",
                unknown,
            )
        return enabled

    enabled = []
    for source in _SOURCE_REGISTRY.values():
        override = _read_setting(
            f"RMC_TESTIMONIAL_SOURCE_{source.key}_ENABLED", None
        )
        if override is None:
            if source.default_enabled:
                enabled.append(source.key)
        elif _truthy(override):
            enabled.append(source.key)
    return enabled


def is_source_enabled(key: str) -> bool:
    """Return whether ``key`` is currently enabled per :func:`configured_sources`."""

    source = get_source(key)
    if source is None:
        return False
    return source.key in configured_sources()


# ---------------------------------------------------------------------------
# Credential resolution helpers
# ---------------------------------------------------------------------------
def service_integration_config(connector_slug: str) -> Dict[str, Any]:
    """Best-effort fetch of a platform-level ``ServiceIntegration.config`` dict.

    Marketing is platform-global while ``ServiceIntegration`` is per-school, so
    this is a SECONDARY credential path: an operator MAY create a row whose
    ``connector_slug`` matches and stash connector credentials in ``config``.
    Returns ``{}`` when no active row exists or the model can't be queried (the
    connectors then fall back to env settings). Lazy-imports the model.
    """

    if not connector_slug:
        return {}
    try:
        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        row = (
            ServiceIntegration.objects.filter(  # tenant-isolation-allow: platform-global-marketing-connector-credential-lookup-not-tenant-scoped
                connector_slug=connector_slug, is_active=True
            )
            .order_by("-updated_at")
            .first()
        )
    except Exception:  # noqa: BLE001 — DB/app-registry not ready, or no such row
        logger.debug(
            "ServiceIntegration lookup unavailable for connector_slug=%s",
            connector_slug,
            exc_info=True,
        )
        return {}
    if row is None:
        return {}
    config = getattr(row, "config", None)
    return config if isinstance(config, dict) else {}


# ---------------------------------------------------------------------------
# Provider framework
# ---------------------------------------------------------------------------
@runtime_checkable
class TestimonialProvider(Protocol):
    """Protocol every testimonial provider satisfies.

    ``fetch()`` returns a list of NORMALIZED testimonial dicts whose keys are a
    subset of the ``MarketingTestimonial`` model fields. For the live
    :class:`ManualDBProvider` these are display-ready, already-approved rows. For
    the external connectors these are candidate rows destined for the operator
    approval queue (``is_approved`` is always False in the normalized dict).
    """

    #: Stable source key this provider represents (matches the model Source).
    source_key: str

    def fetch(self) -> List[Dict[str, Any]]:
        """Return normalized testimonial dicts (possibly empty)."""
        ...


class BaseExternalConnector(ABC):
    """Shared behaviour for credential-gated external review-platform connectors.

    Subclasses declare:
        * ``source_key`` — the model ``Source`` value (e.g. ``"G2"``).
        * ``connector_slug`` — the ``ServiceIntegration.connector_slug`` an
          operator may use to stash credentials.
        * ``api_endpoint`` — the documented REST endpoint the live ``fetch``
          would call.
        * ``_credentials()`` — read + return the connector's credential dict
          from env / ServiceIntegration, or ``{}`` when not configured.
        * ``_fetch_live(credentials)`` — perform the real request + normalize.

    The template-method :meth:`fetch` guarantees the honesty contract: it returns
    ``[]`` (logging at DEBUG) unless the source is BOTH enabled AND credentialed,
    and every normalized row it does emit is unapproved + ingested-from-source.
    """

    source_key: str = ""
    connector_slug: str = ""
    api_endpoint: str = ""

    def fetch(self) -> List[Dict[str, Any]]:
        if not is_source_enabled(self.source_key):
            logger.debug(
                "%s skipped: source %s not enabled",
                type(self).__name__,
                self.source_key,
            )
            return []
        credentials = self._credentials()
        if not credentials:
            logger.debug(
                "%s skipped: no credentials configured (env or ServiceIntegration "
                "connector_slug=%s)",
                type(self).__name__,
                self.connector_slug,
            )
            return []
        try:
            rows = self._fetch_live(credentials)
        except Exception:  # noqa: BLE001 — a flaky external API must never break ingest
            logger.warning(
                "%s live fetch failed; returning no rows",
                type(self).__name__,
                exc_info=True,
            )
            return []
        return [self._stamp_unapproved(row) for row in rows]

    def _stamp_unapproved(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Force the honesty invariants onto a normalized row."""

        row = dict(row)
        row["source"] = self.source_key
        row["ingested_from_source"] = True
        row["is_approved"] = False
        return row

    @abstractmethod
    def _credentials(self) -> Dict[str, Any]:
        """Return the connector credential dict, or ``{}`` when not configured."""

    @abstractmethod
    def _fetch_live(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Call the real API + return normalized (pre-stamp) testimonial dicts."""


# ---- Live provider --------------------------------------------------------
class ManualDBProvider:
    """The LIVE provider: reads APPROVED, active testimonial rows from the model.

    This is the only provider whose output is display-ready. Every row is already
    operator-approved (``is_approved=True``) and active (``is_active=True``).
    The model is lazy-imported inside the method to avoid app-loading issues.
    """

    source_key = "DIRECT"

    def fetch(self) -> List[Dict[str, Any]]:
        try:
            from apps.siteconfig.models_marketing_testimonial import (
                MarketingTestimonial,
            )
        except Exception:  # noqa: BLE001 — app registry not ready
            logger.debug("MarketingTestimonial model unavailable", exc_info=True)
            return []

        rows: List[Dict[str, Any]] = []
        try:
            queryset = MarketingTestimonial.objects.filter(
                is_approved=True, is_active=True
            ).order_by("display_order", "-created_at")
            for obj in queryset:
                rows.append(self._serialize(obj))
        except Exception:  # noqa: BLE001 — DB not migrated / unavailable
            logger.debug("MarketingTestimonial query failed", exc_info=True)
            return []
        return rows

    @staticmethod
    def _serialize(obj: Any) -> Dict[str, Any]:
        return {
            "id": obj.pk,
            "quote": obj.quote,
            "attribution_name": obj.attribution_name,
            "attribution_role": obj.attribution_role,
            "organization_name": obj.organization_name,
            "source": obj.source,
            "source_url": obj.source_url,
            "rating": obj.rating,
            "logo_static_path": obj.logo_static_path,
            "avatar_static_path": obj.avatar_static_path,
            "page_slugs": obj.page_slugs or [],
            "locale": obj.locale,
            "badge_label": badge_label_for(obj.source),
            "is_approved": obj.is_approved,
        }


# ---- External, credential-gated connectors --------------------------------
class G2Connector(BaseExternalConnector):
    """G2 reviews connector.

    Credentials (env, primary):
        ``RMC_TESTIMONIAL_G2_API_TOKEN``    — G2 API bearer token.
        ``RMC_TESTIMONIAL_G2_PRODUCT_ID``   — the RunMyCampus G2 product id.
    Or a ``ServiceIntegration`` row with ``connector_slug="g2_reviews"`` whose
    ``config`` carries ``{"api_token": ..., "product_id": ...}``.

    API endpoint (G2 Data API v1 syndication / reviews):
        ``https://data.g2.com/api/v1/products/{product_id}/survey-responses``
    """

    source_key = "G2"
    connector_slug = "g2_reviews"
    api_endpoint = "https://data.g2.com/api/v1/products/{product_id}/survey-responses"

    def _credentials(self) -> Dict[str, Any]:
        token = str(_read_setting("RMC_TESTIMONIAL_G2_API_TOKEN", "") or "").strip()
        product_id = str(
            _read_setting("RMC_TESTIMONIAL_G2_PRODUCT_ID", "") or ""
        ).strip()
        if not (token and product_id):
            cfg = service_integration_config(self.connector_slug)
            token = token or str(cfg.get("api_token", "") or "").strip()
            product_id = product_id or str(cfg.get("product_id", "") or "").strip()
        if token and product_id:
            return {"api_token": token, "product_id": product_id}
        return {}

    def _fetch_live(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        import requests

        url = self.api_endpoint.format(product_id=credentials["product_id"])
        response = requests.get(
            url,
            headers={
                "Authorization": f"Token token={credentials['api_token']}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        rows: List[Dict[str, Any]] = []
        for item in payload.get("data", []) or []:
            attrs = item.get("attributes", {}) or {}
            rows.append(
                {
                    "quote": attrs.get("comment_answers", {})
                    .get("love", {})
                    .get("value", "")
                    or attrs.get("title", ""),
                    "attribution_name": attrs.get("user_name", ""),
                    "attribution_role": attrs.get("user_title", ""),
                    "organization_name": attrs.get("user_company", ""),
                    "source_url": attrs.get("url", ""),
                    "rating": attrs.get("star_rating"),
                    "external_id": str(item.get("id", "")),
                    "raw_payload": item,
                }
            )
        return rows


class CapterraConnector(BaseExternalConnector):
    """Capterra (Gartner Digital Markets) reviews connector.

    Credentials (env, primary):
        ``RMC_TESTIMONIAL_CAPTERRA_API_KEY``      — Gartner Digital Markets key.
        ``RMC_TESTIMONIAL_CAPTERRA_PRODUCT_ID``   — Capterra product id.
    Or ``ServiceIntegration`` ``connector_slug="capterra_reviews"`` with
    ``config = {"api_key": ..., "product_id": ...}``.

    API endpoint (Gartner Digital Markets reviews API):
        ``https://api.gartnerdigitalmarkets.com/v1/reviews?product_id={product_id}``
    """

    source_key = "CAPTERRA"
    connector_slug = "capterra_reviews"
    api_endpoint = (
        "https://api.gartnerdigitalmarkets.com/v1/reviews?product_id={product_id}"
    )

    def _credentials(self) -> Dict[str, Any]:
        api_key = str(
            _read_setting("RMC_TESTIMONIAL_CAPTERRA_API_KEY", "") or ""
        ).strip()
        product_id = str(
            _read_setting("RMC_TESTIMONIAL_CAPTERRA_PRODUCT_ID", "") or ""
        ).strip()
        if not (api_key and product_id):
            cfg = service_integration_config(self.connector_slug)
            api_key = api_key or str(cfg.get("api_key", "") or "").strip()
            product_id = product_id or str(cfg.get("product_id", "") or "").strip()
        if api_key and product_id:
            return {"api_key": api_key, "product_id": product_id}
        return {}

    def _fetch_live(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        import requests

        url = self.api_endpoint.format(product_id=credentials["product_id"])
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {credentials['api_key']}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        rows: List[Dict[str, Any]] = []
        for item in payload.get("reviews", []) or []:
            rows.append(
                {
                    "quote": item.get("overall_comment", "")
                    or item.get("pros", ""),
                    "attribution_name": item.get("reviewer_name", ""),
                    "attribution_role": item.get("reviewer_title", ""),
                    "organization_name": item.get("reviewer_company", ""),
                    "source_url": item.get("review_url", ""),
                    "rating": item.get("overall_rating"),
                    "external_id": str(item.get("review_id", "")),
                    "raw_payload": item,
                }
            )
        return rows


class TrustpilotConnector(BaseExternalConnector):
    """Trustpilot reviews connector.

    Credentials (env, primary):
        ``RMC_TESTIMONIAL_TRUSTPILOT_API_KEY``       — Trustpilot Business API key.
        ``RMC_TESTIMONIAL_TRUSTPILOT_BUSINESS_ID``   — business unit id.
    Or ``ServiceIntegration`` ``connector_slug="trustpilot_reviews"`` with
    ``config = {"api_key": ..., "business_unit_id": ...}``.

    API endpoint (Trustpilot Business Units reviews API):
        ``https://api.trustpilot.com/v1/business-units/{business_unit_id}/reviews``
    """

    source_key = "TRUSTPILOT"
    connector_slug = "trustpilot_reviews"
    api_endpoint = (
        "https://api.trustpilot.com/v1/business-units/{business_unit_id}/reviews"
    )

    def _credentials(self) -> Dict[str, Any]:
        api_key = str(
            _read_setting("RMC_TESTIMONIAL_TRUSTPILOT_API_KEY", "") or ""
        ).strip()
        business_unit_id = str(
            _read_setting("RMC_TESTIMONIAL_TRUSTPILOT_BUSINESS_ID", "") or ""
        ).strip()
        if not (api_key and business_unit_id):
            cfg = service_integration_config(self.connector_slug)
            api_key = api_key or str(cfg.get("api_key", "") or "").strip()
            business_unit_id = business_unit_id or str(
                cfg.get("business_unit_id", "") or ""
            ).strip()
        if api_key and business_unit_id:
            return {"api_key": api_key, "business_unit_id": business_unit_id}
        return {}

    def _fetch_live(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        import requests

        url = self.api_endpoint.format(
            business_unit_id=credentials["business_unit_id"]
        )
        response = requests.get(
            url,
            headers={"apikey": credentials["api_key"], "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        rows: List[Dict[str, Any]] = []
        for item in payload.get("reviews", []) or []:
            consumer = item.get("consumer", {}) or {}
            rows.append(
                {
                    "quote": item.get("text", "") or item.get("title", ""),
                    "attribution_name": consumer.get("displayName", ""),
                    "attribution_role": "",
                    "organization_name": "",
                    "source_url": item.get("url", ""),
                    "rating": item.get("stars"),
                    "external_id": str(item.get("id", "")),
                    "raw_payload": item,
                }
            )
        return rows


class GoogleBusinessConnector(BaseExternalConnector):
    """Google Business Profile reviews connector.

    Credentials (env, primary):
        ``RMC_TESTIMONIAL_GOOGLE_ACCESS_TOKEN``  — OAuth access token (Business
                                                   Profile API scope).
        ``RMC_TESTIMONIAL_GOOGLE_ACCOUNT_ID``    — GBP account id.
        ``RMC_TESTIMONIAL_GOOGLE_LOCATION_ID``   — GBP location id.
    Or ``ServiceIntegration`` ``connector_slug="google_business_reviews"`` with
    ``config = {"access_token": ..., "account_id": ..., "location_id": ...}``.

    API endpoint (Google Business Profile API v4 reviews):
        ``https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews``
    """

    source_key = "GOOGLE"
    connector_slug = "google_business_reviews"
    api_endpoint = (
        "https://mybusiness.googleapis.com/v4/accounts/{account_id}"
        "/locations/{location_id}/reviews"
    )

    _STAR_WORD_TO_INT = {
        "ONE": 1,
        "TWO": 2,
        "THREE": 3,
        "FOUR": 4,
        "FIVE": 5,
    }

    def _credentials(self) -> Dict[str, Any]:
        token = str(
            _read_setting("RMC_TESTIMONIAL_GOOGLE_ACCESS_TOKEN", "") or ""
        ).strip()
        account_id = str(
            _read_setting("RMC_TESTIMONIAL_GOOGLE_ACCOUNT_ID", "") or ""
        ).strip()
        location_id = str(
            _read_setting("RMC_TESTIMONIAL_GOOGLE_LOCATION_ID", "") or ""
        ).strip()
        if not (token and account_id and location_id):
            cfg = service_integration_config(self.connector_slug)
            token = token or str(cfg.get("access_token", "") or "").strip()
            account_id = account_id or str(cfg.get("account_id", "") or "").strip()
            location_id = location_id or str(
                cfg.get("location_id", "") or ""
            ).strip()
        if token and account_id and location_id:
            return {
                "access_token": token,
                "account_id": account_id,
                "location_id": location_id,
            }
        return {}

    def _fetch_live(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        import requests

        url = self.api_endpoint.format(
            account_id=credentials["account_id"],
            location_id=credentials["location_id"],
        )
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {credentials['access_token']}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        rows: List[Dict[str, Any]] = []
        for item in payload.get("reviews", []) or []:
            reviewer = item.get("reviewer", {}) or {}
            rows.append(
                {
                    "quote": item.get("comment", ""),
                    "attribution_name": reviewer.get("displayName", ""),
                    "attribution_role": "",
                    "organization_name": "",
                    "source_url": "",
                    "rating": self._STAR_WORD_TO_INT.get(
                        str(item.get("starRating", "")).upper()
                    ),
                    "external_id": str(item.get("reviewId", "")),
                    "raw_payload": item,
                }
            )
        return rows


class LinkedInConnector(BaseExternalConnector):
    """LinkedIn recommendations / Page testimonials connector.

    NOTE: LinkedIn's API does not generally expose third-party recommendations;
    a real deployment typically ingests an operator-curated export. This
    connector keeps the credential-gated shape for parity and remains a clean
    no-op without credentials.

    Credentials (env, primary):
        ``RMC_TESTIMONIAL_LINKEDIN_ACCESS_TOKEN`` — OAuth access token.
        ``RMC_TESTIMONIAL_LINKEDIN_ORG_ID``       — LinkedIn organization id.
    Or ``ServiceIntegration`` ``connector_slug="linkedin_recommendations"`` with
    ``config = {"access_token": ..., "org_id": ...}``.

    API endpoint (LinkedIn Marketing / Organizations API, illustrative):
        ``https://api.linkedin.com/v2/organizationalEntityShareStatistics?q=organizationalEntity&organizationalEntity=urn:li:organization:{org_id}``
    """

    source_key = "LINKEDIN"
    connector_slug = "linkedin_recommendations"
    api_endpoint = (
        "https://api.linkedin.com/v2/organizationalEntityShareStatistics"
        "?q=organizationalEntity&organizationalEntity=urn:li:organization:{org_id}"
    )

    def _credentials(self) -> Dict[str, Any]:
        token = str(
            _read_setting("RMC_TESTIMONIAL_LINKEDIN_ACCESS_TOKEN", "") or ""
        ).strip()
        org_id = str(
            _read_setting("RMC_TESTIMONIAL_LINKEDIN_ORG_ID", "") or ""
        ).strip()
        if not (token and org_id):
            cfg = service_integration_config(self.connector_slug)
            token = token or str(cfg.get("access_token", "") or "").strip()
            org_id = org_id or str(cfg.get("org_id", "") or "").strip()
        if token and org_id:
            return {"access_token": token, "org_id": org_id}
        return {}

    def _fetch_live(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        import requests

        url = self.api_endpoint.format(org_id=credentials["org_id"])
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {credentials['access_token']}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        rows: List[Dict[str, Any]] = []
        for item in payload.get("elements", []) or []:
            rows.append(
                {
                    "quote": item.get("comment", ""),
                    "attribution_name": item.get("author_name", ""),
                    "attribution_role": item.get("author_title", ""),
                    "organization_name": item.get("organization_name", ""),
                    "source_url": item.get("permalink", ""),
                    "rating": None,
                    "external_id": str(item.get("id", "")),
                    "raw_payload": item,
                }
            )
        return rows


# ---------------------------------------------------------------------------
# Connector discovery
# ---------------------------------------------------------------------------
#: External connectors keyed by their model Source value.
EXTERNAL_CONNECTORS: Dict[str, type[BaseExternalConnector]] = {
    "G2": G2Connector,
    "CAPTERRA": CapterraConnector,
    "TRUSTPILOT": TrustpilotConnector,
    "GOOGLE": GoogleBusinessConnector,
    "LINKEDIN": LinkedInConnector,
}


def enabled_external_connectors() -> List[BaseExternalConnector]:
    """Instantiate the external connectors whose source is currently enabled."""

    enabled = set(configured_sources())
    return [
        connector_cls()
        for key, connector_cls in EXTERNAL_CONNECTORS.items()
        if key in enabled
    ]


def live_provider() -> ManualDBProvider:
    """Return the single live, display-ready provider."""

    return ManualDBProvider()
