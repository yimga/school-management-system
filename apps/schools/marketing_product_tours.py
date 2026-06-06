"""Single source of truth for marketing product tours.

A product tour is an ordered list of "frames" that, played back in the
``_product_tour.html`` component, walk a marketing visitor through a faithful
mock of the real RunMyCampus workspace for a given platform feature. Each frame
declares a stable ``key``, a human ``caption``, a focusing ``tooltip`` callout,
and a ``ui_kind`` enum string that the template switches on to render the
matching faithful ``.rmc-*`` UI block (a roster data-table, an attendance grid,
a fee ledger, a message composer, an admissions pipeline, a gradebook).

This module is pure data + a single lookup helper — no Django imports — so it is
trivially unit-testable with ``SimpleTestCase`` and importable from the
marketing view without side effects.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class TourFrame(TypedDict):
    """One step in a guided product tour."""

    key: str
    caption: str
    tooltip: str
    ui_kind: str


class ProductTour(TypedDict):
    """A resolved tour: the slug plus its ordered frames."""

    slug: str
    frames: list[TourFrame]


# Stable ``ui_kind`` enum values the template partial switches on. Keeping them
# centralised means the SOT and the renderer can never drift on a typo.
UI_KIND_ROSTER_TABLE = "roster_table"
UI_KIND_ATTENDANCE_GRID = "attendance_grid"
UI_KIND_FEE_LEDGER = "fee_ledger"
UI_KIND_MESSAGE_COMPOSER = "message_composer"
UI_KIND_ADMISSIONS_PIPELINE = "admissions_pipeline"
UI_KIND_GRADEBOOK = "gradebook"
UI_KIND_METRIC_OVERVIEW = "metric_overview"


# Flagship platform slugs → ordered tour frames. 3–5 frames each.
_PRODUCT_TOURS: dict[str, list[TourFrame]] = {
    "platform-student-information-system": [
        {
            "key": "sis-overview",
            "caption": "The student information dashboard the moment you sign in.",
            "tooltip": "Live enrolment, attendance and standing — one glance.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
        {
            "key": "sis-roster",
            "caption": "Every learner in a sortable, filterable roster.",
            "tooltip": "Click any row to open the full student record.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "sis-attendance",
            "caption": "Daily attendance captured against the same roster.",
            "tooltip": "Mark a whole class present in two taps.",
            "ui_kind": UI_KIND_ATTENDANCE_GRID,
        },
        {
            "key": "sis-grades",
            "caption": "Academic standing rolls up into report cards.",
            "tooltip": "Grades flow straight to guardians.",
            "ui_kind": UI_KIND_GRADEBOOK,
        },
    ],
    "platform-attendance": [
        {
            "key": "att-grid",
            "caption": "The class attendance grid for today's register.",
            "tooltip": "Tap a cell to cycle present, absent or late.",
            "ui_kind": UI_KIND_ATTENDANCE_GRID,
        },
        {
            "key": "att-roster",
            "caption": "Attendance is anchored to the live class roster.",
            "tooltip": "No re-keying — the roster is the source of truth.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "att-summary",
            "caption": "Attendance rates summarise into a daily snapshot.",
            "tooltip": "Spot at-risk learners before they fall behind.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
    "platform-fees-payments": [
        {
            "key": "fees-overview",
            "caption": "Collections and outstanding balances at a glance.",
            "tooltip": "Know exactly what's billed, paid and overdue.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
        {
            "key": "fees-ledger",
            "caption": "A per-student fee ledger with every line item.",
            "tooltip": "Decimal-accurate — no rounding surprises.",
            "ui_kind": UI_KIND_FEE_LEDGER,
        },
        {
            "key": "fees-reminder",
            "caption": "Send a payment reminder without leaving the ledger.",
            "tooltip": "Reminders go by the family's preferred channel.",
            "ui_kind": UI_KIND_MESSAGE_COMPOSER,
        },
    ],
    "platform-communications": [
        {
            "key": "comms-composer",
            "caption": "Compose a message to a class, year group or whole school.",
            "tooltip": "One composer, every channel — email, SMS, push.",
            "ui_kind": UI_KIND_MESSAGE_COMPOSER,
        },
        {
            "key": "comms-audience",
            "caption": "Pick the audience straight from the live roster.",
            "tooltip": "Target by class, role or custom segment.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "comms-delivery",
            "caption": "Track delivery and open rates after you send.",
            "tooltip": "See who received and read each message.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
    "platform-admissions": [
        {
            "key": "adm-pipeline",
            "caption": "The admissions pipeline from enquiry to enrolled.",
            "tooltip": "Drag an applicant to advance their stage.",
            "ui_kind": UI_KIND_ADMISSIONS_PIPELINE,
        },
        {
            "key": "adm-applicants",
            "caption": "Every applicant in a reviewable list.",
            "tooltip": "Open a record to see documents and decisions.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "adm-offer",
            "caption": "Send an offer or decision email in one click.",
            "tooltip": "Templated, branded, and logged automatically.",
            "ui_kind": UI_KIND_MESSAGE_COMPOSER,
        },
        {
            "key": "adm-funnel",
            "caption": "Conversion across the funnel, stage by stage.",
            "tooltip": "See where applicants drop off.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
    "platform-grading-report-cards": [
        {
            "key": "grade-book",
            "caption": "The gradebook for a class and assessment.",
            "tooltip": "Enter marks; weighted totals compute live.",
            "ui_kind": UI_KIND_GRADEBOOK,
        },
        {
            "key": "grade-roster",
            "caption": "Grades sit against the same enrolled roster.",
            "tooltip": "One learner, one continuous academic record.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "grade-distribution",
            "caption": "Grade distribution and cohort averages.",
            "tooltip": "Spot the assessment that needs a re-teach.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
}


def product_tour_for_slug(slug: str) -> Optional[ProductTour]:
    """Return the tour for ``slug`` (case-insensitive) or ``None``.

    The result is a fresh dict shaped ``{"slug": <canonical-slug>, "frames":
    [...]}`` suitable for handing straight to the ``_product_tour.html``
    component as the ``product_tour`` context variable.
    """

    if not slug:
        return None
    key = slug.strip().lower()
    frames = _PRODUCT_TOURS.get(key)
    if not frames:
        return None
    return {"slug": key, "frames": list(frames)}


def flagship_tour_slugs() -> list[str]:
    """Return the list of slugs that have a defined product tour."""

    return list(_PRODUCT_TOURS.keys())
