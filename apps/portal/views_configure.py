"""
Phase U (2026-05-12): tenant Settings IA hub.

`/portal/configure/` now serves a real consolidated settings hub instead of redirecting
into one of many config destinations. Apple Settings-app pattern: left rail of categories
with their entry-point links, plus a search across them.

This view is a thin catalog — no destructive ops. Actual configuration screens live
under siteconfig/, studio_os/, admin/. The hub just unifies discoverability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse


@dataclass
class SettingsEntry:
    label: str
    description: str
    icon: str
    url: Optional[str]
    keywords: str = ""


@dataclass
class SettingsCategory:
    slug: str
    label: str
    icon: str
    description: str
    entries: list[SettingsEntry]


def _try_url(name: str, **kwargs) -> Optional[str]:
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def _build_catalog() -> list[SettingsCategory]:
    return [
        SettingsCategory(
            slug="brand",
            label="Brand & Experience",
            icon="bi-palette",
            description="Logo, colors, fonts, the look and feel students and parents see.",
            entries=[
                SettingsEntry("Brand identity", "Logo, primary color, accent, typography.",
                              "bi-paint-bucket",
                              _try_url("studio_os:experience"),
                              "logo color font theme branding"),
                SettingsEntry("Custom domain", "Connect your own domain (e.g. portal.myschool.edu).",
                              "bi-globe2",
                              _try_url("siteconfig:console_domains_hub"),
                              "dns subdomain domain ssl https"),
                SettingsEntry("Site preview", "See changes before they go live.",
                              "bi-eye",
                              _try_url("siteconfig:preview_from_form"),
                              "preview staging draft"),
            ],
        ),
        SettingsCategory(
            slug="academics",
            label="Academics",
            icon="bi-mortarboard",
            description="Grading scale, terms, classrooms, subjects, assessment weights.",
            entries=[
                SettingsEntry("Grading scale", "0–100, A–F, 0–20 (West Africa), IB, custom.",
                              "bi-list-ol",
                              _try_url("siteconfig:dashboard_hub"),
                              "grades scale waec ib igcse cbse"),
                SettingsEntry("Assessment weights", "Theory vs practical, sequence weights per term.",
                              "bi-sliders2",
                              _try_url("evals:evaluation_admin"),
                              "weight assessment evaluation seq exam mock"),
                SettingsEntry("Academic year & terms", "Calendar, term dates, exam windows.",
                              "bi-calendar3",
                              _try_url("siteconfig:tenant_runtime_configuration_hub"),
                              "year term calendar trimester semester"),
            ],
        ),
        SettingsCategory(
            slug="finance",
            label="Finance",
            icon="bi-cash-coin",
            description="Fee structures, payment providers, currencies, taxes.",
            entries=[
                SettingsEntry("Fee structures", "Per-class, per-term, scholarship & discount rules.",
                              "bi-receipt",
                              _try_url("finance:fee_structures"),
                              "fees tuition invoice billing"),
                SettingsEntry("Payment providers", "Stripe, Flutterwave, Paystack, bank transfer.",
                              "bi-credit-card",
                              _try_url("siteconfig:payment_providers"),
                              "stripe payment gateway flutterwave paystack"),
                SettingsEntry("Currency & taxes", "Default currency, multi-currency, VAT rules.",
                              "bi-currency-exchange",
                              _try_url("siteconfig:tenant_runtime_configuration_hub"),
                              "currency tax vat region"),
            ],
        ),
        SettingsCategory(
            slug="people",
            label="People & Roles",
            icon="bi-people",
            description="Staff, parents, students, custom roles and permissions.",
            entries=[
                SettingsEntry("Roles & permissions", "Custom roles, RBAC scopes.",
                              "bi-shield-lock",
                              _try_url("accounts:rbac_dashboard"),
                              "rbac permission role admin teacher parent"),
                SettingsEntry("Staff directory", "Add, remove, deactivate staff.",
                              "bi-person-badge",
                              _try_url("accounts:staff_list"),
                              "staff teacher director hr"),
                SettingsEntry("Parent / student linking", "Invite parents, link to students.",
                              "bi-link-45deg",
                              _try_url("parent:link_child_wizard"),
                              "parent guardian link child invite"),
            ],
        ),
        SettingsCategory(
            slug="notifications",
            label="Notifications & Comms",
            icon="bi-bell",
            description="Email signoff, SMS providers, message templates, escalation.",
            entries=[
                SettingsEntry("Email & SMS",
                              "Sender identity, signoff, SMS gateway.",
                              "bi-envelope",
                              _try_url("siteconfig:dashboard_hub"),
                              "email smtp sender sms twilio"),
                SettingsEntry("Templates",
                              "Welcome, fee reminder, attendance alert, report-card cover.",
                              "bi-file-earmark-text",
                              _try_url("siteconfig:bulk_letters"),
                              "template letter welcome reminder"),
                SettingsEntry("Notification policy",
                              "Who gets paged, escalation timing.",
                              "bi-clock-history",
                              _try_url("siteconfig:scheduled_reports_delivery_hub"),
                              "escalation page on-call policy"),
            ],
        ),
        SettingsCategory(
            slug="ai",
            label="AI",
            icon="bi-stars",
            description="AI provider, prompt registry, governance, entitlements.",
            entries=[
                SettingsEntry("AI Center", "One place to chat with every governed assistant. Pick a domain, ask, get audited answers.",
                              "bi-stars",
                              _try_url("siteconfig:ai_center"),
                              "ai assistant chat center copilot help"),
                SettingsEntry("AI provider", "Ollama, local-first, fallback rules.",
                              "bi-cpu",
                              _try_url("siteconfig:ai_governance"),
                              "ai ollama provider llm rules"),
                SettingsEntry("Prompt registry",
                              "Curated prompts for report cards, parent messages.",
                              "bi-pencil-square",
                              _try_url("siteconfig:dashboard_hub"),
                              "prompt template ai"),
                SettingsEntry("Governance & audit",
                              "Who can use AI, audit log, redaction rules.",
                              "bi-shield-check",
                              _try_url("siteconfig:ai_governance"),
                              "audit governance ai redaction pii"),
            ],
        ),
        SettingsCategory(
            slug="integrations",
            label="Integrations",
            icon="bi-plug",
            description="Connect Zoom / Teams / Meet / Outlook / Slack / Gmail and more. Marketplace apps, webhooks, SSO.",
            entries=[
                SettingsEntry("Connections",
                              "Connect Zoom, Teams, Google Meet, Outlook, Gmail, Slack, transactional email and more (per school and per campus).",
                              "bi-link-45deg",
                              _try_url("integrations_marketplace:hub"),
                              "zoom teams meet outlook gmail slack discord webex sendgrid mailgun postmark connect oauth"),
                SettingsEntry("Marketplace apps", "Install or remove third-party apps.",
                              "bi-grid-3x3-gap",
                              _try_url("marketplace:tenant_app_catalog"),
                              "marketplace app install plugin"),
                SettingsEntry("SSO", "SAML / OAuth single sign-on.",
                              "bi-key",
                              _try_url("siteconfig:tenant_runtime_configuration_hub"),
                              "sso saml oauth google microsoft"),
                SettingsEntry("Webhooks & API",
                              "Event subscriptions, API keys, audit.",
                              "bi-arrow-repeat",
                              _try_url("siteconfig:tenant_runtime_configuration_hub"),
                              "api webhook integration event"),
            ],
        ),
        SettingsCategory(
            slug="compliance",
            label="Compliance & Privacy",
            icon="bi-shield-check",
            description="Region, data residency, FERPA/GDPR, retention, audit logs.",
            entries=[
                SettingsEntry("Region & residency",
                              "Where your data lives; regional policy snapshot.",
                              "bi-geo-alt",
                              _try_url("siteconfig:tenant_runtime_configuration_hub"),
                              "region residency policy waec kcse cbse ferpa"),
                SettingsEntry("Audit & access log",
                              "PII view audit, export & erase requests.",
                              "bi-clipboard-data",
                              _try_url("compliance:dashboard"),
                              "audit log pii ferpa gdpr access"),
                SettingsEntry("Tenant diagnostics",
                              "Health checks, permission simulator, live self-service fixes.",
                              "bi-heart-pulse",
                              _try_url("siteconfig:zero_ticket_hub"),
                              "diagnostic health permission roster support"),
                SettingsEntry("Retention",
                              "Per-record retention windows.",
                              "bi-archive",
                              _try_url("siteconfig:tenant_runtime_configuration_hub"),
                              "retention archive purge"),
            ],
        ),
    ]


@login_required
def portal_configure_hub(request: HttpRequest) -> HttpResponse:
    catalog = _build_catalog()
    visible = [
        SettingsCategory(
            slug=c.slug,
            label=c.label,
            icon=c.icon,
            description=c.description,
            entries=[e for e in c.entries if e.url],
        )
        for c in catalog
    ]
    visible = [c for c in visible if c.entries]
    return render(
        request,
        "portal/configure_hub.html",
        {
            "categories": visible,
            "active_category": request.GET.get("category", visible[0].slug if visible else ""),
            "search_q": request.GET.get("q", ""),
        },
    )
