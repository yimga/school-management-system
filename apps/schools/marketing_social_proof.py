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
"""

from __future__ import annotations

from typing import Final, Optional, TypedDict


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
    """

    quote: str
    attribution_name: str
    attribution_role: str
    school_name: str
    logo: str
    metric: str


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


def testimonials_for_slug(slug: str) -> list[Testimonial]:
    """Return owner-approved testimonials for ``slug`` (case-insensitive).

    Empty list when the slug is unknown/falsy or no real testimonials have been
    added yet — the testimonial band then renders nothing.
    """

    key = _normalize(slug)
    if not key:
        return []
    return TESTIMONIALS.get(key, [])


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
