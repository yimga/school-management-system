"""Social-proof source of truth for the marketing platform pages.

Competitors (Blackbaud, Arbor, Stripe, PowerSchool) lean hard on testimonials,
customer logos and case studies on every product page. Ours currently carry
NONE. This module is the single, honest contract that wires those slots up —
testimonial bands, logo walls and per-page case studies — so the *moment* the
owner supplies real, approved customer content it appears on the pages, and
until then every slot renders NOTHING.

HONESTY CONTRACT — read before editing
=======================================
NEVER add unverified, fabricated, aspirational, "placeholder" or "example"
customer proof to the live structures below. A testimonial, a school logo or a
case study is a public claim that a named real customer said/did a real thing.
Populate these structures ONLY with owner-approved, real customer data that the
owner has confirmed we have written permission to display.

Every public helper is therefore EMPTY-BY-DEFAULT:

* :func:`testimonials_for_slug`  -> ``[]``    (no fabricated quotes)
* :func:`logos_for_slug`         -> ``[]``    (no fabricated logos)
* :func:`case_study_for_slug`    -> ``None``  (no fabricated case study)

When the owner is ready, they add a real entry to the (currently empty) maps
near the top of this module, following the commented EXAMPLE shapes. No template,
view or service-worker change is required — the slots are already wired.

DB AGGREGATION (added v4.02.x)
==============================
Testimonials now AGGREGATE two honest, owner-approved sources:

  (a) the in-file ``TESTIMONIALS`` config dict above (a zero-DB fallback that
      works even on a fresh checkout / mid-migration), AND
  (b) ``apps.siteconfig.models_marketing_testimonial.MarketingTestimonial`` rows
      that are BOTH ``is_approved=True`` AND ``is_active=True`` — the model's
      ``is_approved`` flag defaults to ``False`` and must be flipped by a human,
      so the DB path is just as honesty-gated as the config path.

DB access is wrapped defensively: the table may not exist yet (fresh checkout /
before ``migrate``), so any ``DatabaseError`` / ``OperationalError`` falls back
to the config dict ONLY. The aggregate-rating and Review JSON-LD helpers are
built EXCLUSIVELY from real approved rows that carry a numeric rating, so we
NEVER emit a fabricated ``ratingValue`` / ``reviewCount`` to search engines.
"""

from __future__ import annotations

import logging
from typing import Final, Optional, TypedDict

logger = logging.getLogger(__name__)

# Rating is on a 1-5 star scale; schema.org bestRating reflects that ceiling.
_BEST_RATING: Final[int] = 5


# ---------------------------------------------------------------------------
# Typed shapes — these describe the dict the owner populates per slug.
# ---------------------------------------------------------------------------
class Testimonial(TypedDict, total=False):
    """One real, owner-approved customer testimonial.

    Required keys:
        ``quote``             the verbatim words the customer agreed to publish.
        ``attribution_name``  the real person being quoted (e.g. "Ada Okoye").
        ``attribution_role``  their role (e.g. "Head of Admissions").
        ``school_name``       the real school / district they belong to.

    Optional keys:
        ``logo``    a ``static`` path to the school's logo (e.g.
                    "marketing/img/proof/<school>.png"); rendered if present.
        ``metric``  a short hard outcome the customer attributes to RunMyCampus
                    (e.g. "cut fee reconciliation time by half"); rendered if
                    present.

    DB-aggregated keys (populated from MarketingTestimonial rows; all optional):
        ``source``       provenance tag (DIRECT / G2 / CAPTERRA / …).
        ``badge_label``  short human label for a "via {label}" source badge.
        ``rating``       integer 1-5 star rating, when the source carried one.
        ``source_url``   link to the original review / case study / press item.
        ``avatar``       a ``static`` path to the attribution avatar image.
    """

    quote: str
    attribution_name: str
    attribution_role: str
    school_name: str
    logo: str
    metric: str
    source: str
    badge_label: str
    rating: int
    source_url: str
    avatar: str


class Logo(TypedDict, total=False):
    """One real, owner-approved customer logo for a logo wall.

    Required keys:
        ``school_name``  the real school / district (also used as the alt text).
        ``static_path``  a ``static`` path to the logo asset
                         (e.g. "marketing/img/proof/<school>.svg").
    """

    school_name: str
    static_path: str


class CaseStudy(TypedDict, total=False):
    """One real, owner-approved customer case study for a single page.

    Required keys:
        ``school_name``  the real school / district.
        ``headline``     a short outcome headline the customer approved.
        ``body``         a paragraph of approved narrative.

    Optional keys:
        ``attribution_name``  the named person who can be quoted/credited.
        ``attribution_role``  their role.
        ``metric``            a short hard outcome string.
        ``logo``              a ``static`` path to the school's logo.
    """

    school_name: str
    headline: str
    body: str
    attribution_name: str
    attribution_role: str
    metric: str
    logo: str


# ---------------------------------------------------------------------------
# OWNER-POPULATED DATA — EMPTY BY DEFAULT.
#
# These maps are intentionally empty. Every helper below returns nothing while
# they stay empty, so the testimonial band / logo wall / case-study block on
# the platform pages render NOTHING (no fabricated content) until the owner
# adds real, approved entries here.
#
# ---- HOW TO ADD A REAL TESTIMONIAL (example shape, keep commented) ----------
# TESTIMONIALS = {
#     "platform-admissions": [
#         {
#             "quote": "We went from a shared inbox to one pipeline every "
#                      "office can see — inquiries stopped slipping through.",
#             "attribution_name": "Ada Okoye",
#             "attribution_role": "Head of Admissions",
#             "school_name": "Bright Future Academy",
#             # optional:
#             "logo": "marketing/img/proof/bright-future-academy.png",
#             "metric": "+22% inquiries followed up within a day",
#         },
#     ],
# }
#
# ---- HOW TO ADD A REAL LOGO (example shape, keep commented) -----------------
# LOGOS = {
#     "platform-admissions": [
#         {
#             "school_name": "Bright Future Academy",
#             "static_path": "marketing/img/proof/bright-future-academy.svg",
#         },
#     ],
# }
#
# ---- HOW TO ADD A REAL CASE STUDY (example shape, keep commented) -----------
# CASE_STUDIES = {
#     "platform-fees-payments": {
#         "school_name": "Bright Future Academy",
#         "headline": "Half the time on fee reconciliation, zero spreadsheets.",
#         "body": "Switching to RunMyCampus put every mobile-money and card "
#                 "rail in one ledger the bursar reconciles each morning.",
#         # optional:
#         "attribution_name": "Tunde Bello",
#         "attribution_role": "Bursar",
#         "metric": "−43% time on reconciliation",
#         "logo": "marketing/img/proof/bright-future-academy.svg",
#     },
# }
# ---------------------------------------------------------------------------
TESTIMONIALS: Final[dict[str, list[Testimonial]]] = {}
LOGOS: Final[dict[str, list[Logo]]] = {}
CASE_STUDIES: Final[dict[str, CaseStudy]] = {}


def _normalize(slug: str) -> str:
    """Lower-case and trim a slug for case-insensitive lookups."""

    return slug.strip().lower() if slug else ""


def _normalize_lang(lang: str) -> str:
    """Lower-case + trim a locale code; empty falls back to ``en``."""

    return (lang or "").strip().lower() or "en"


def _config_testimonials(key: str) -> list[Testimonial]:
    """Owner-populated config-dict testimonials for ``key`` (zero-DB fallback)."""

    return list(TESTIMONIALS.get(key, []))


# Map a MarketingTestimonial.Source value to a short human badge label.
_SOURCE_BADGE_LABELS: Final[dict[str, str]] = {
    "DIRECT": "",
    "G2": "G2",
    "CAPTERRA": "Capterra",
    "GOOGLE": "Google",
    "TRUSTPILOT": "Trustpilot",
    "LINKEDIN": "LinkedIn",
    "CASE_STUDY": "Case study",
    "PRESS": "Press",
    "OTHER": "",
}


def _db_testimonials(key: str, lang: str) -> list[Testimonial]:
    """Approved + active testimonials from the DB model for ``key``/``lang``.

    Returns ``[]`` (never raises) when the table is missing or any DB error
    occurs, so a fresh checkout / mid-migration page still renders the config
    fallback rather than 500-ing. Rows match when ``page_slugs`` is empty (band
    is eligible for any page) OR contains the slug, and ``locale`` equals the
    requested language (falling back to ``en`` rows when the requested locale
    has none). Ordered by ``display_order`` (model Meta default).
    """

    try:
        from django.db import DatabaseError, OperationalError
    except Exception:  # pragma: no cover - Django always present at runtime
        return []

    try:
        from apps.siteconfig.models_marketing_testimonial import MarketingTestimonial

        rows = list(
            MarketingTestimonial.objects.filter(  # tenant-isolation-allow: platform-global-marketing-content-no-school-fk
                is_approved=True, is_active=True
            ).order_by("display_order", "-created_at")
        )
    except (DatabaseError, OperationalError):
        # Table not migrated yet / transient DB error -> config-only fallback.
        return []
    except Exception:  # pragma: no cover - import/runtime guard, never 500 marketing
        logger.warning("MarketingTestimonial DB lookup failed", exc_info=True)
        return []

    def _slug_match(row) -> bool:
        slugs = row.page_slugs if isinstance(row.page_slugs, list) else []
        normalized = {_normalize(str(s)) for s in slugs}
        return not normalized or key in normalized

    eligible = [r for r in rows if _slug_match(r)]
    in_lang = [r for r in eligible if _normalize_lang(r.locale) == lang]
    if not in_lang and lang != "en":
        in_lang = [r for r in eligible if _normalize_lang(r.locale) == "en"]

    out: list[Testimonial] = []
    for r in in_lang:
        entry: Testimonial = {
            "quote": r.quote,
            "attribution_name": r.attribution_name,
            "attribution_role": r.attribution_role,
            "school_name": r.organization_name,
        }
        if r.logo_static_path:
            entry["logo"] = r.logo_static_path
        if r.avatar_static_path:
            entry["avatar"] = r.avatar_static_path
        entry["source"] = r.source
        badge = _SOURCE_BADGE_LABELS.get(r.source, "")
        if badge:
            entry["badge_label"] = badge
        if r.rating is not None:
            entry["rating"] = int(r.rating)
        if r.source_url:
            entry["source_url"] = r.source_url
        out.append(entry)
    return out


def testimonials_for_slug(slug: str, lang: str = "en") -> list[Testimonial]:
    """Return owner-approved testimonials for ``slug`` (case-insensitive).

    AGGREGATES the in-file config dict (zero-DB fallback) AND approved+active
    ``MarketingTestimonial`` DB rows whose ``page_slugs`` is empty or contains
    the slug and whose ``locale`` matches ``lang`` (falling back to ``en``).
    Config entries render first (owner-curated), then DB entries in
    ``display_order``.

    Still returns ``[]`` when nothing approved exists — the testimonial band
    then renders nothing (honesty preserved). DB access is defensive: a missing
    table / DB error degrades to the config dict only.
    """

    key = _normalize(slug)
    if not key:
        return []
    lang_n = _normalize_lang(lang)
    return _config_testimonials(key) + _db_testimonials(key, lang_n)


def _rated_values_for_slug(slug: str, lang: str) -> list[int]:
    """The numeric 1-5 ratings of approved testimonials for ``slug``/``lang``."""

    values: list[int] = []
    for t in testimonials_for_slug(slug, lang):
        rating = t.get("rating")
        if isinstance(rating, (int, float)) and not isinstance(rating, bool):
            ivalue = int(rating)
            if 1 <= ivalue <= _BEST_RATING:
                values.append(ivalue)
    return values


def aggregate_rating_for_slug(slug: str, lang: str = "en") -> Optional[dict]:
    """Return a schema.org AggregateRating-ready dict, or ``None``.

    Computed ONLY from approved testimonials that carry a numeric 1-5 rating.
    Returns ``None`` when fewer than one rated approved testimonial exists, so
    we never emit a fabricated rating.
    """

    values = _rated_values_for_slug(slug, _normalize_lang(lang))
    if len(values) < 1:
        return None
    avg = round(sum(values) / len(values), 1)
    return {
        "ratingValue": avg,
        "reviewCount": len(values),
        "bestRating": _BEST_RATING,
    }


def review_schema_for_slug(
    slug: str, name: str, lang: str = "en"
) -> Optional[dict]:
    """Return a schema.org Service-with-Review+AggregateRating JSON-LD dict.

    Built ONLY from real approved testimonials that carry a numeric rating, so
    it NEVER emits fake ratings. Returns ``None`` when no rated approved
    testimonial exists for the slug.
    """

    lang_n = _normalize_lang(lang)
    aggregate = aggregate_rating_for_slug(slug, lang_n)
    if aggregate is None:
        return None

    reviews: list[dict] = []
    for t in testimonials_for_slug(slug, lang_n):
        rating = t.get("rating")
        if not isinstance(rating, (int, float)) or isinstance(rating, bool):
            continue
        ivalue = int(rating)
        if not (1 <= ivalue <= _BEST_RATING):
            continue
        review: dict = {
            "@type": "Review",
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": ivalue,
                "bestRating": _BEST_RATING,
            },
            "reviewBody": t.get("quote", ""),
        }
        author = t.get("attribution_name")
        if author:
            review["author"] = {"@type": "Person", "name": author}
        url = t.get("source_url")
        if url:
            review["url"] = url
        reviews.append(review)

    schema: dict = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": name,
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": aggregate["ratingValue"],
            "reviewCount": aggregate["reviewCount"],
            "bestRating": aggregate["bestRating"],
        },
        "review": reviews,
    }
    return schema


def logos_for_slug(slug: str) -> list[Logo]:
    """Return owner-approved customer logos for ``slug`` (case-insensitive).

    Empty list when the slug is unknown/falsy or no real logos have been added
    yet — the logo wall then renders nothing.
    """

    key = _normalize(slug)
    if not key:
        return []
    return LOGOS.get(key, [])


def case_study_for_slug(slug: str) -> Optional[CaseStudy]:
    """Return the owner-approved case study for ``slug`` (case-insensitive).

    ``None`` when the slug is unknown/falsy or no real case study has been added
    yet — the case-study block then renders nothing.
    """

    key = _normalize(slug)
    if not key:
        return None
    return CASE_STUDIES.get(key)
