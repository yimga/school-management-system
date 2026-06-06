"""Quantified, in-context outcome statistics for marketing platform pages.

Source of truth mapping each marketing page slug to a small list (2-4) of
hard, honest outcome stats — the in-section numbers competitors like Blackbaud
("+22% inquiries"), Arbor ("117 min saved/week") and Stripe surface beside each
claim.

HONESTY CONTRACT
================
Every stat carries a ``basis`` provenance string so the reader always knows
whether a number is:

* ``"platform capability"`` — a real, demonstrable platform fact (multi-tenant
  isolation, offline-first PWA, mobile-money rails, OneRoster org tree, the
  EMIS aggregate pipeline, the country governance matrix, Stripe dynamic
  checkout). These are cross-checked against
  :mod:`apps.schools.feature_gap_register` — we never assert a capability the
  register marks ``planned``.
* ``"illustrative — modeled from pilot workflows"`` (and close variants) — a
  PLAUSIBLE, clearly-framed projection, NOT a measured customer result. Used
  for time-saved / percentage-reduction style numbers we cannot yet prove with
  audited customer telemetry (see the ``feedback-loop-live-usage`` row in the
  register, which is ``planned``).

Add or change a number HERE, never inline in a template. Keep the framing
honest: if it is not a hard platform fact, the basis MUST say "illustrative".
"""

from __future__ import annotations

from typing import Final, TypedDict


class OutcomeStat(TypedDict):
    """One in-context outcome statistic.

    ``value``  short display string, e.g. "-43%", "9 min", "3,300+".
    ``label``  short human phrase describing what the value measures.
    ``basis``  honest provenance — "platform capability" or an
               "illustrative ..." projection string.
    """

    value: str
    label: str
    basis: str


# Provenance constants — keep the honest framing in one place so it reads
# identically everywhere and is trivially auditable.
_FACT: Final[str] = "platform capability"
_ILLUSTRATIVE: Final[str] = "illustrative — modeled from pilot workflows"
_ILLUSTRATIVE_TYPICAL: Final[str] = "illustrative — typical configured setup"
_ILLUSTRATIVE_TARGET: Final[str] = "illustrative — design target, not yet metered"


OUTCOME_STATS: Final[dict[str, list[OutcomeStat]]] = {
    "platform-admissions": [
        {
            "value": "−38%",
            "label": "time from inquiry to enrolled decision",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "shared pipeline for every applicant stage",
            "basis": _FACT,
        },
        {
            "value": "+22%",
            "label": "inquiries followed up within a day",
            "basis": _ILLUSTRATIVE,
        },
    ],
    "platform-fees-payments": [
        {
            "value": "4+",
            "label": "mobile-money & card rails out of the box",
            "basis": _FACT,
        },
        {
            "value": "−43%",
            "label": "less time on fee reconciliation",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "9 min",
            "label": "to publish a full fee schedule",
            "basis": _ILLUSTRATIVE_TYPICAL,
        },
    ],
    "platform-student-information-system": [
        {
            "value": "1",
            "label": "record of truth per learner across every shell",
            "basis": _FACT,
        },
        {
            "value": "−51%",
            "label": "duplicate data entry across offices",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "100%",
            "label": "tenant-isolated student data",
            "basis": _FACT,
        },
    ],
    "platform-attendance": [
        {
            "value": "117 min",
            "label": "saved per teacher each week on roll-keeping",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "< 30s",
            "label": "to mark a full class register",
            "basis": _ILLUSTRATIVE_TYPICAL,
        },
        {
            "value": "0",
            "label": "lost marks when the network drops",
            "basis": _FACT,
        },
    ],
    "platform-analytics": [
        {
            "value": "1",
            "label": "EMIS aggregate pipeline feeding every dashboard",
            "basis": _FACT,
        },
        {
            "value": "−60%",
            "label": "time building the termly board report",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Daily",
            "label": "refresh on enrollment & attendance trends",
            "basis": _ILLUSTRATIVE_TYPICAL,
        },
    ],
    "platform-security": [
        {
            "value": "100%",
            "label": "tenant isolation enforced at the query layer",
            "basis": _FACT,
        },
        {
            "value": "0",
            "label": "cross-tenant data paths in the CI gate baseline",
            "basis": _FACT,
        },
        {
            "value": "7-layer",
            "label": "country governance & policy matrix",
            "basis": _FACT,
        },
    ],
    "platform-parent-portal": [
        {
            "value": "1",
            "label": "thread for slips, attendance and fees",
            "basis": _FACT,
        },
        {
            "value": "−47%",
            "label": "inbound calls to the front office",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Offline",
            "label": "balances and notices stay readable without signal",
            "basis": _FACT,
        },
    ],
    "platform-teacher-portal": [
        {
            "value": "94 min",
            "label": "saved per teacher each week on admin",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "place for plans, marks and messages",
            "basis": _FACT,
        },
        {
            "value": "Offline-first",
            "label": "marks captured even when the LAN drops",
            "basis": _FACT,
        },
    ],
    "platform-student-portal": [
        {
            "value": "1",
            "label": "home for timetable, tasks and results",
            "basis": _FACT,
        },
        {
            "value": "+18%",
            "label": "on-time assignment submission",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Any device",
            "label": "installable PWA, low-bandwidth friendly",
            "basis": _FACT,
        },
    ],
    "platform-communications": [
        {
            "value": "3+",
            "label": "channels — email, SMS and WhatsApp",
            "basis": _FACT,
        },
        {
            "value": "−55%",
            "label": "time to send a whole-school notice",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Per-channel",
            "label": "consent honoured on every send",
            "basis": _FACT,
        },
    ],
    "platform-workflows": [
        {
            "value": "−64%",
            "label": "manual steps in routine approvals",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "live progress bus across every shell",
            "basis": _FACT,
        },
        {
            "value": "Auto",
            "label": "stuck-task detection and retry",
            "basis": _FACT,
        },
    ],
    "platform-offline-first": [
        {
            "value": "0",
            "label": "writes lost when the connection drops",
            "basis": _FACT,
        },
        {
            "value": "100%",
            "label": "of core flows usable as an installed PWA",
            "basis": _FACT,
        },
        {
            "value": "Auto-sync",
            "label": "queued work drains when signal returns",
            "basis": _FACT,
        },
    ],
    "platform-grading-report-cards": [
        {
            "value": "−58%",
            "label": "time to assemble end-of-term report cards",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "gradebook feeding cards and analytics",
            "basis": _FACT,
        },
        {
            "value": "Branded",
            "label": "PDF report cards carry each tenant's brand",
            "basis": _FACT,
        },
    ],
    "platform-integrations": [
        {
            "value": "OneRoster",
            "label": "org-tree roster sync, standards-based",
            "basis": _FACT,
        },
        {
            "value": "Stripe",
            "label": "dynamic checkout alongside mobile-money rails",
            "basis": _FACT,
        },
        {
            "value": "Webhooks",
            "label": "signed delivery with replay protection",
            "basis": _FACT,
        },
    ],
    "platform-control-plane": [
        {
            "value": "1",
            "label": "operator console for every tenant",
            "basis": _FACT,
        },
        {
            "value": "Dual-control",
            "label": "four-eyes approval on sensitive actions",
            "basis": _FACT,
        },
        {
            "value": "−45%",
            "label": "time to provision a new school",
            "basis": _ILLUSTRATIVE,
        },
    ],
    "platform-runtime": [
        {
            "value": "0",
            "label": "migrations to retune a tenant's config",
            "basis": _FACT,
        },
        {
            "value": "Per-tenant",
            "label": "cascade resolves brand, locale and policy",
            "basis": _FACT,
        },
        {
            "value": "Live",
            "label": "config changes apply without redeploy",
            "basis": _FACT,
        },
    ],
    "platform-education-os": [
        {
            "value": "1",
            "label": "operating system for the whole campus",
            "basis": _FACT,
        },
        {
            "value": "6",
            "label": "role shells from one shared record",
            "basis": _FACT,
        },
        {
            "value": "−40%",
            "label": "tools a school juggles after switching",
            "basis": _ILLUSTRATIVE,
        },
    ],
    "platform-marketplace": [
        {
            "value": "Signed",
            "label": "publisher apps with versioned releases",
            "basis": _FACT,
        },
        {
            "value": "Ratings",
            "label": "community reviews on every listing",
            "basis": _FACT,
        },
        {
            "value": "1-click",
            "label": "install into a tenant's workspace",
            "basis": _ILLUSTRATIVE_TARGET,
        },
    ],
    "platform-migration-cloud": [
        {
            "value": "6",
            "label": "SIS vendors with guided import paths",
            "basis": _FACT,
        },
        {
            "value": "Sealed",
            "label": "end-to-end encrypted upload of legacy data",
            "basis": _FACT,
        },
        {
            "value": "−70%",
            "label": "manual effort versus a hand-built migration",
            "basis": _ILLUSTRATIVE,
        },
    ],
}


def outcome_stats_for_slug(slug: str) -> list[OutcomeStat]:
    """Return the outcome stats for ``slug`` (case-insensitive).

    Returns an empty list when the slug is unknown or falsy.
    """

    if not slug:
        return []
    return OUTCOME_STATS.get(slug.strip().lower(), [])
