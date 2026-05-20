"""Public marketing surfaces for trust, pricing clarity, and competitive storytelling."""

from __future__ import annotations

import json
from pathlib import Path

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET


def _pricing_payload():
    path = (
        Path(__file__).resolve().parent
        / "data"
        / "pricing_packages.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@require_GET
def marketing_trust_dedicated(request):
    """Public /trust/ — v3 marketing shell via trust-center page definition."""
    from apps.schools.marketing_views import marketing_page

    return marketing_page(request, "trust-center")


_STORIES = {
    "implementation": {
        "slug": "implementation",
        "seo_title": "Implementation — first 30 days to value",
        "headline": "A disciplined first 30 days",
        "lede": "RunMyCampus is built as a school operating system: tenant-isolated, offline-aware, and workflow-first. This page describes a typical implementation path — not a guarantee of calendar days.",
        "bullets": [
            "Week 1: tenant, academic calendar, roster truth, and finance baselines.",
            "Week 2: teacher workflows, attendance, and marks with pilot classes.",
            "Week 3: parent communications, report pilot, and payment rehearsal (product-side; live PSP is external).",
            "Week 4: go-live checklist, support playbooks, and honest pilot evidence capture.",
        ],
        "ctas": [
            ("marketing_book_demo", "Book a demo"),
            ("marketing_trust_dedicated", "Trust center"),
            ("platform_runtime:implementation_command_center", "Implementation command center (signed-in)"),
        ],
    },
    "offline-first": {
        "slug": "offline-first",
        "seo_title": "Offline-first operations",
        "headline": "Offline-ready, not offline-mythical",
        "lede": "Schools lose connectivity. RunMyCampus encodes offline capture and conflict handling where modules support it — honesty: not every legacy integration is offline-equal.",
        "bullets": [
            "Local-first UX patterns for supported attendance and fee workflows.",
            "Sync queues with operator-visible conflicts — no silent merges.",
            "Tenant isolation preserved when replaying actions server-side.",
        ],
        "ctas": [
            ("marketing_trust_dedicated", "How we talk about trust"),
            ("marketing_story_payments_readiness", "Payments readiness"),
        ],
    },
    "payments-readiness": {
        "slug": "payments-readiness",
        "seo_title": "Payments readiness — product rails and external PSP honesty",
        "headline": "Payments by country, honestly",
        "lede": "The product ships invoicing, receipt capture, orchestration UX, and health snapshots. Live money movement still requires your PSP merchant onboarding, keys, webhooks, and settlement — we do not fake that.",
        "bullets": [
            "Country-aware UX patterns without claiming every rail is live in your corridor until you wire PSPs.",
            "Manual and offline proof paths where policy allows.",
            "No unlimited settlement or chargeback guarantees — contracts define SLAs.",
        ],
        "ctas": [
            ("marketing_pricing_packages_clarity", "Packages"),
            ("marketing_contact", "Talk to sales"),
        ],
    },
    "for-private-schools": {
        "slug": "for-private-schools",
        "seo_title": "For private schools",
        "headline": "Independent school trust",
        "lede": "Private schools need parent trust, financial clarity, and academic credibility. RunMyCampus aligns portals, finance, and academics behind one primary-action philosophy.",
        "bullets": [
            "Parent and teacher experiences that reduce shadow IT.",
            "Implementation factory surfaces for heads of school and bursars.",
            "Pilot evidence capture without fabricated references.",
        ],
        "ctas": [
            ("marketing_story_pilot_program", "Pilot program"),
            ("marketing_trust_dedicated", "Trust center"),
        ],
    },
    "for-school-networks": {
        "slug": "for-school-networks",
        "seo_title": "For school networks",
        "headline": "Multi-campus without multi-chaos",
        "lede": "Networks need per-campus isolation with group-level reporting patterns. The architecture is tenant-first; group rollups depend on your deployment choices and contracts.",
        "bullets": [
            "Campus tenants with policy inheritance patterns.",
            "Marketplace controls for network-approved apps.",
            "Expansion-ready lifecycle signals — not vanity metrics.",
        ],
        "ctas": [
            ("marketing_pricing_packages_clarity", "Network package"),
            ("marketing_contact", "Plan rollout"),
        ],
    },
    "pilot-program": {
        "slug": "pilot-program",
        "seo_title": "Pilot program — evidence, not theater",
        "headline": "Pilot-ready proof",
        "lede": "One sentence: we instrument pilots with in-product scorecards, defect closure tied to tests or documented exceptions, and reference states that stay private until you explicitly approve them — no borrowed logos and no pretend certifications.",
        "bullets": [
            "Pilot scorecard fields track modules and loop completion.",
            "Reference states require explicit approval before public use.",
            "Defect closure loop ties fixes to tests or documented exceptions.",
        ],
        "ctas": [
            ("marketing_trust_dedicated", "Security posture"),
            ("marketing_story_implementation", "Implementation path"),
        ],
    },
}


def _resolve_ctas(pairs: list[tuple[str, str]]):
    out = []
    for name, label in pairs:
        try:
            out.append({"url": reverse(name), "label": label})
        except Exception:
            continue
    return out


@require_GET
def marketing_story_page(request, story_slug: str):
    story = _STORIES.get(story_slug)
    if not story:
        raise Http404("Unknown story")
    ctx = {
        **story,
        "ctas_resolved": _resolve_ctas(story["ctas"]),
    }
    return render(request, "marketing/competitive_story.html", ctx)


@require_GET
def marketing_pricing_packages_clarity(request):
    data = _pricing_payload()
    packages = data.get("packages") or []
    rows = []
    for p in packages:
        cta_route = p.get("cta_route") or "marketing_contact"
        try:
            cta_url = reverse(cta_route)
        except Exception:
            cta_url = reverse("marketing_contact")
        rows.append({**p, "cta_url": cta_url})
    return render(
        request,
        "marketing/pricing_packages.html",
        {
            "seo_title": "Packages — clarity without fake unlimiteds",
            "live_psp_caveat": data.get("live_psp_caveat", ""),
            "packages": rows,
        },
    )


@require_GET
def marketing_procurement_checklist(request):
    from apps.schools.marketing_personality import marketing_personality_context

    ctx = {
        "seo_title": "Procurement checklist — diligence without vanity claims",
        "trust_url": reverse("marketing_trust_dedicated"),
        "security_packet_url": reverse("marketing_security_packet_request"),
        "implementation_assurance_url": reverse("marketing_implementation_assurance"),
        "contact_url": reverse("marketing_contact"),
        "marketing_page_slug": "procurement-docs",
        **marketing_personality_context("procurement-docs"),
    }
    return render(request, "marketing/procurement_checklist.html", ctx)


@require_GET
def marketing_implementation_assurance(request):
    from apps.schools.marketing_personality import marketing_personality_context

    ctx = {
        "seo_title": "Implementation assurance — in-product factory depth",
        "trust_url": reverse("marketing_trust_dedicated"),
        "procurement_url": reverse("marketing_procurement_checklist"),
        "security_packet_url": reverse("marketing_security_packet_request"),
        "marketing_page_slug": "implementation-timelines",
        **marketing_personality_context("implementation-timelines"),
    }
    return render(request, "marketing/implementation_assurance.html", ctx)


@require_GET
def marketing_security_packet_request(request):
    from apps.schools.marketing_views import _get_country_from_request
    from apps.schools.security_packet_country_annex import (
        build_country_annex,
        country_code_for_jurisdiction,
        jurisdiction_choices,
    )

    jurisdiction_value = (request.GET.get("jurisdiction") or "").strip().lower()
    geo_country = _get_country_from_request(request)
    country_code = country_code_for_jurisdiction(jurisdiction_value) or geo_country
    profile_id = (request.GET.get("compliance_profile_id") or "").strip()
    security_country_annex = build_country_annex(
        country_code=country_code,
        compliance_profile_id=profile_id,
    )
    annex_by_jurisdiction: dict[str, dict] = {
        "": build_country_annex(country_code=country_code),
    }
    for row in jurisdiction_choices():
        code = (row.get("country_code") or "").upper()[:2]
        annex_by_jurisdiction[row["value"]] = build_country_annex(country_code=code)

    ctx = {
        "seo_title": "Request security packet — procurement artefacts",
        "submitted": request.GET.get("submitted") == "1",
        "error": request.GET.get("error") == "1",
        "trust_url": reverse("marketing_trust_dedicated"),
        "submit_url": reverse("marketing_security_packet_submit"),
        "procurement_url": reverse("marketing_procurement_checklist"),
        "jurisdiction_choices": jurisdiction_choices(),
        "selected_jurisdiction": jurisdiction_value,
        "security_country_annex": security_country_annex,
        "annex_by_jurisdiction_json": json.dumps(annex_by_jurisdiction),
    }
    return render(request, "marketing/security_packet_request.html", ctx)
