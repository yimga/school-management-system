"""
Marketing landing v2 — editorial redesign preview.

Self-contained view for the /v2 stakeholder-review surface. The template
hardcodes its own copy, but the inherited marketing_header.html and
marketing_footer.html still need the marketing context (nav primary,
footer links, brand mode flags). We reuse _marketing_context from
marketing_views so the editorial-styled inherited chrome renders fully.
"""

from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET


def _safe_url(name: str, default: str = "#") -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return default


def _landing_bento_cells() -> list[dict]:
    """Bento grid cells for marketing landing. Copy lives here (not template)
    so it routes through i18n + can be A/B tested via the configurability
    contract later without template surgery."""
    return [
        {
            "size": "lg",
            "tone": "ink",
            "eyebrow": _("One quiet system"),
            "title": _("The whole school in one calm view."),
            "body": _("Attendance, fees, behaviour, staffing — the front page tells you what changed since you last looked, and nothing else."),
            "metric": {"value": "4 min", "label": _("morning brief instead of forty")},
            "href": _safe_url("marketing_platform"),
            "cta": _("See the leader's view"),
            "data_cta": "secondary",
            "data_page": "home-bento",
        },
        {
            "size": "sm",
            "tone": "warm",
            "eyebrow": _("Teachers"),
            "title": _("Roll in 9 seconds."),
            "metric": {"value": "32 hrs", "label": _("per teacher per term")},
        },
        {
            "size": "sm",
            "tone": "sand",
            "eyebrow": _("Finance"),
            "title": _("Reconciled by lunch."),
            "metric": {"value": "94%", "label": _("fees collected by week 3")},
        },
        {
            "size": "md",
            "eyebrow": _("Parents"),
            "title": _("Close without another app."),
            "body": _("Permission slips, fees, attendance, and pickup time in the place a parent already looks — no install, no password rescue."),
            "metric": {"value": "0 apps", "label": _("added to a parent's phone")},
        },
        {
            "size": "md",
            "eyebrow": _("IT & operations"),
            "title": _("Nothing to babysit."),
            "body": _("Multi-tenant, region-aware, offline-tolerant. One platform across every campus — no shadow spreadsheets, no patch parties."),
            "metric": {"value": "8 wks", "label": _("to fully switch from legacy SIS")},
        },
        {
            "size": "wide",
            "tone": "sand",
            "eyebrow": _("Built for the way schools actually run"),
            "title": _("Region-aware. Low-connectivity tolerant. Audit-ready by default."),
            "body": _("Operates across K–12, international networks, faith-based and day schools. Currencies, calendars, grading scales, and reporting lines bend to your operating model — not the other way around."),
            "href": _safe_url("marketing_compare"),
            "cta": _("Compare against your current SIS"),
            "data_cta": "secondary",
            "data_page": "home-bento",
        },
    ]


@require_GET
def marketing_landing_v2(request):
    """Editorial redesign preview at /v2 — noindex, unlinked from nav."""
    from apps.schools.marketing_views import (
        _get_country_from_request,
        _marketing_context,
    )

    geo_country = _get_country_from_request(request)
    ctx = _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )
    # /v2/ is the preview URL; the production homepage at / now also renders
    # this template via marketing_landing. Flag the preview path so it carries
    # noindex while / stays indexable.
    ctx["v2_preview"] = True
    ctx["landing_bento"] = {
        "aria_label_id": "landing-bento-headline",
        "eyebrow": _("What you actually get"),
        "headline": _("One platform. Every role. The whole school."),
        "lead": _("Not a feature list — the operating system between admissions, classrooms, fees, and the message you send a parent at 8:14 a.m."),
        "cells": _landing_bento_cells(),
    }
    return render(request, "schools/marketing_landing_v2.html", ctx)
