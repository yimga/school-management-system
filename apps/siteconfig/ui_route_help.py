"""
Route-level page explainers for operator + tenant shells.

Resolves copy from workflow registry routes, explicit overrides, and namespace defaults.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

# Hand-tuned overrides (wins over workflow + sovereign 50X when keys collide).
# Curated, locale-neutral "About this page" copy for high-value tenant detail /
# workflow routes that otherwise fall back to the generic namespace blurb. Each
# body is grounded in what the page actually does (verified against its template),
# not a humanised url_name. Keep copy country-agnostic per local-first.
ROUTE_HELP_OVERRIDES: dict[str, dict[str, Any]] = {
    "people:backend_applicant_list": {
        "title": _("Applicants"),
        "body": _("Admissions pipeline from enquiry through enrollment."),
        "surface": "tenant",
        "fields": ("stage", "status"),
    },
    "siteconfig:grading_scale_bands": {
        "title": _("Grading scale bands"),
        "body": _(
            "Read-only view of this school's effective grading scale — band labels, "
            "grade points, and normalized ranges. Conversions between locale scales are "
            "handled automatically; edit the scale itself from Grading & language."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "accounts:substitute_handover_create": {
        "title": _("Substitute handover"),
        "body": _(
            "Generate a redacted, time-boxed handover packet for a covering teacher. "
            "Identifiers are hashed before any audit row, and medical / IEP detail stays "
            "gated unless explicitly authorised."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "accounts:lost_belongings_mint": {
        "title": _("Mint lost-and-found tag"),
        "body": _(
            "Create a tenant-scoped QR tag for an asset. Anonymous finders later return it "
            "using only the short code — no student PII is ever exposed by the loop."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "accounts:lost_belongings_lookup": {
        "title": _("Lost & found lookup"),
        "body": _(
            "Anonymous return page: a finder enters the short code from a sticker to log a "
            "sighting. No personal information is recorded; staff follow up through the "
            "custody loop."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "accounts:lost_belongings_recover": {
        "title": _("Record recovery"),
        "body": _(
            "Log the recovery of a tagged item. The event is written to the custody trail "
            "with redacted notes; guardians are notified when the record is linked to a "
            "student."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "accounts:permission_to_pay_open": {
        "title": _("Permission to pay"),
        "body": _(
            "Bundles event permission and payment authorisation into one workflow. Amounts "
            "at or above this tenant's threshold require guardian approval before payment "
            "can be authorised."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "finance:payment_readiness_dashboard": {
        "title": _("Payment Readiness Center"),
        "body": _(
            "Honest, metadata-only health of this school's payment corridors — no live "
            "charges. Shows the configured rails, gateway status, and the next action "
            "needed to go live."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "finance:payment_readiness_setup": {
        "title": _("Payment setup & readiness"),
        "body": _(
            "Plain-language checklist to make this school ready to collect payments: "
            "country & currency corridor, recommended rails, Stripe Connect for SaaS "
            "billing, and marketplace credentials. A manual receipt fallback stays "
            "available if every gateway is down."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "compliance:ferpa_disclosure_detail": {
        "title": _("FERPA disclosure record"),
        "body": _(
            "A single §99.32 disclosure: who released which records to whom, the legal "
            "basis, and consent status. This view is itself audit-logged — each load adds "
            "a VIEW row to the evidence trail."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "portal:student_passport_detail": {
        "title": _("Student passport"),
        "body": _(
            "Portable, tenant-scoped identity record used to link verified transcripts "
            "across schools. Shows passport ID, school memberships, and consent status; "
            "deeper history lives in Student 360 and the Transcript vault."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "portal:mfa_policy": {
        "title": _("Two-factor enforcement"),
        "body": _(
            "Privileged roles always require 2FA — this page controls HOW it's rolled out: "
            "a hard wall (Strict), a grace window, or a nudge (Optional). Scope it to this "
            "school only or set the platform default. Users who already have 2FA are "
            "unaffected."
        ),
        "surface": "tenant",
        "fields": (),
    },
    "evals:evaluation_drilldown": {
        "title": _("Evaluation drill-down"),
        "body": _(
            "Per-student, per-subject breakdown of a single evaluation — sequence scores, "
            "term, and academic year — for review and correction. Scores are bounded by "
            "this school's operational grade scale."
        ),
        "surface": "tenant",
        "fields": (),
    },
}

# Django app namespace → catalog entity prefix for field manifests
NAMESPACE_ENTITY_PREFIX: dict[str, str] = {
    "accounts": "accounts",
    "academics": "academics",
    "admissions": "admissions",
    "analytics": "analytics",
    "apicenter": "apicenter",
    "assist_dock": "assist_dock",
    "automation": "automation",
    "billing": "billing",
    "brand_experience": "brand_experience",
    "communication": "communication",
    "compliance": "compliance",
    "customersuccess": "customersuccess",
    "emis": "emis",
    "evals": "evals",
    "events": "events",
    "feedback": "feedback",
    "finance": "finance",
    "global_registries": "global_registries",
    "governance": "governance",
    "integrations_marketplace": "integrations_marketplace",
    "lifecycle": "lifecycle",
    "marketplace": "marketplace",
    "metadata": "metadata",
    "migration_cloud": "migration_cloud",
    "observability": "observability",
    "orchestration": "orchestration",
    "packages": "packages",
    "payroll": "payroll",
    "people": "people",
    "plans_entitlements": "plans_entitlements",
    "platform_runtime": "platform_runtime",
    "policies": "policies",
    "portal": "portal",
    "registries": "registries",
    "reports": "reports",
    "requests": "requests",
    "runtime_blueprints": "runtime_blueprints",
    "safeguarding": "safeguarding",
    "sales": "sales",
    "school_events": "school_events",
    "schoolops": "operator",
    "schools": "schools",
    "setup_studio": "setup_studio",
    "siteconfig": "siteconfig",
    "social_media": "social_media",
    "student360": "student360",
    "studio_os": "studio_os",
    "sync_engine": "sync_engine",
    "tenancy": "tenancy",
    "super": "super",
    "authentication": "portal",
}

# Fallback when no workflow or override matches
_NAMESPACE_DEFAULTS: dict[str, dict[str, str]] = {
    "operator": {
        "title": _("Operator workspace"),
        "body": _("Platform-wide tools for provisioning, billing, and migration."),
    },
    "tenant": {
        "title": _("School workspace"),
        "body": _("Day-to-day workflows for staff, teachers, and administrators."),
    },
}


def _workflow_route_help() -> dict[str, dict[str, Any]]:
    from apps.platform_runtime.workflow_registry import (
        AUDIENCE_FOUNDER,
        AUDIENCE_OPERATOR,
        AUDIENCE_PARENT,
        AUDIENCE_STUDENT,
        AUDIENCE_TEACHER,
        AUDIENCE_TENANT_ADMIN,
        WORKFLOWS,
    )

    operator_audiences = {AUDIENCE_OPERATOR, AUDIENCE_FOUNDER}
    tenant_audiences = {
        AUDIENCE_TENANT_ADMIN,
        AUDIENCE_TEACHER,
        AUDIENCE_PARENT,
        AUDIENCE_STUDENT,
    }
    out: dict[str, dict[str, Any]] = {}
    for workflow in WORKFLOWS.values():
        route = getattr(workflow, "route", None)
        if not route or not isinstance(route, str) or route.startswith("/"):
            continue
        if route in out:
            continue
        if workflow.audience in operator_audiences:
            surface = "operator"
        elif workflow.audience in tenant_audiences:
            surface = "tenant"
        else:
            surface = "public"
        out[route] = {
            "title": workflow.title,
            "body": workflow.purpose,
            "surface": surface,
            "workflow_key": workflow.key,
            "fields": (),
        }
    return out


_WORKFLOW_ROUTE_HELP: dict[str, dict[str, Any]] | None = None


def sovereign_route_entry_count() -> int:
    """High-friction route explainers (SOVEREIGN 50X program)."""
    from apps.siteconfig.ui_route_help_sovereign_50x import ROUTE_HELP_SOVEREIGN_50X

    return len(ROUTE_HELP_SOVEREIGN_50X)


def _merged_route_index() -> dict[str, dict[str, Any]]:
    global _WORKFLOW_ROUTE_HELP
    if _WORKFLOW_ROUTE_HELP is None:
        _WORKFLOW_ROUTE_HELP = _workflow_route_help()
    from apps.siteconfig.ui_route_help_sovereign_50x import ROUTE_HELP_SOVEREIGN_50X

    merged = dict(_WORKFLOW_ROUTE_HELP)
    merged.update(ROUTE_HELP_SOVEREIGN_50X)
    merged.update(ROUTE_HELP_OVERRIDES)
    return merged


def _view_name(request: Any) -> str:
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    namespace = getattr(match, "namespace", None) or ""
    url_name = getattr(match, "url_name", None) or ""
    if namespace and url_name:
        return f"{namespace}:{url_name}"
    return url_name or getattr(match, "view_name", None) or ""


def _host_surface(request: Any) -> str:
    kind = getattr(request, "public_host_kind", None)
    if kind == "manager":
        return "operator"
    return "tenant"


def resolve_route_help(request: Any) -> dict[str, Any]:
    """Return {title, body, surface, workflow_key?, fields} for the current route."""
    view_name = _view_name(request)
    if not view_name:
        surface = _host_surface(request)
        default = _NAMESPACE_DEFAULTS.get(surface, _NAMESPACE_DEFAULTS["tenant"])
        return {"title": default["title"], "body": default["body"], "surface": surface, "fields": ()}

    entry = _merged_route_index().get(view_name)
    if entry:
        return {
            "title": entry.get("title", ""),
            "body": entry.get("body", ""),
            "surface": entry.get("surface") or _host_surface(request),
            "workflow_key": entry.get("workflow_key", ""),
            "fields": tuple(entry.get("fields") or ()),
        }

    match = getattr(request, "resolver_match", None)
    namespace = getattr(match, "namespace", None) if match else None
    surface = _host_surface(request)

    # Page-aware fallback — so "About this page" describes THIS page rather than
    # one flat namespace blurb on every unregistered route. Curated manager
    # pages get hand-written help; everything else gets a page-specific title
    # humanised from its url_name + a section descriptor.
    from apps.platform_runtime.control_plane_page_intel import (
        humanised_page_help,
        resolve_manager_page,
    )

    intel = resolve_manager_page(view_name)
    if intel:
        return {
            "title": intel["title"],
            "body": intel["body"],
            "surface": surface,
            "namespace": namespace or "",
            "fields": (),
        }
    humanised = humanised_page_help(view_name, namespace or "")
    if humanised:
        return {
            "title": humanised[0],
            "body": humanised[1],
            "surface": surface,
            "namespace": namespace or "",
            "fields": (),
        }

    default = _NAMESPACE_DEFAULTS.get(surface, _NAMESPACE_DEFAULTS["tenant"])
    return {
        "title": default["title"],
        "body": default["body"],
        "surface": surface,
        "namespace": namespace or "",
        "fields": (),
    }


def entity_prefix_for_request(request: Any) -> str:
    """Catalog entity prefix used to build auto field manifests."""
    match = getattr(request, "resolver_match", None)
    namespace = getattr(match, "namespace", None) if match else None
    if namespace and namespace in NAMESPACE_ENTITY_PREFIX:
        return NAMESPACE_ENTITY_PREFIX[namespace]
    return "common" if _host_surface(request) == "tenant" else "operator"
