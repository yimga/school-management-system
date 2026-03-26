"""
Phase 3 — Control-plane outcome registry (operator UX, not model walls).

Nine outcome groups map ZIP Phase 3 to resolvable URLs. Each link may carry:
- stability: stable | beta | danger (operator risk signal)
- sources: which layers can explain “why enabled” (runtime, pack, policy, entitlement, override)

The six-step ``build_operator_control_model_for_request()`` path ships the full operator journey
(capability families → grouped controls → impact → source tracing → staged changes → publish/rollback).
Step ``related`` URLs support ``LinkTarget`` (e.g. ``super:admin_bridge`` kwargs), same as the nine-group registry.
"""

from __future__ import annotations

import logging
from typing import Any

from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

# Outcome link target: plain URL name, or (viewname, reverse kwargs) for admin bridges, etc.
LinkTarget = str | tuple[str, dict[str, Any]]


def _rev(url_name: str, request=None) -> str | None:
    """
    Resolve URLs for operator surfaces. Prefer the active resolver, then manager
    urlconf (many ``super:`` names exist only on ``config.manager_urls``).
    """
    primary = getattr(request, "urlconf", None) if request is not None else None
    fallbacks: list[str] = []
    if primary:
        fallbacks.append(primary)
    if "config.manager_urls" not in fallbacks:
        fallbacks.append("config.manager_urls")
    last_exc: Exception | None = None
    for urlconf in fallbacks:
        try:
            return reverse(url_name, urlconf=urlconf)
        except NoReverseMatch as e:
            last_exc = e
            continue
    logger.debug("control_outcome_center: %r: %s", url_name, last_exc)
    return None


def _rev_with_kwargs(
    url_name: str, kwargs: dict[str, Any], request=None
) -> str | None:
    """Like ``_rev`` but passes ``kwargs`` to ``reverse`` (e.g. ``super:admin_bridge``)."""
    primary = getattr(request, "urlconf", None) if request is not None else None
    fallbacks: list[str] = []
    if primary:
        fallbacks.append(primary)
    if "config.manager_urls" not in fallbacks:
        fallbacks.append("config.manager_urls")
    last_exc: Exception | None = None
    for urlconf in fallbacks:
        try:
            return reverse(url_name, kwargs=kwargs, urlconf=urlconf)
        except NoReverseMatch as e:
            last_exc = e
            continue
    logger.debug("control_outcome_center: %r %r: %s", url_name, kwargs, last_exc)
    return None


def _resolve_link_url(url_ref: LinkTarget, request) -> str | None:
    if isinstance(url_ref, str):
        return _rev(url_ref, request)
    viewname, kw = url_ref
    return _rev_with_kwargs(viewname, kw, request)


# Nine outcome groups — Phase 3 ZIP plan (1:1 with operator mental model)
OUTCOME_GROUP_SPECS: list[dict[str, Any]] = [
    {
        "id": "platform_health",
        "title": "Platform Health",
        "subtitle": "Incidents, school health, orchestration posture",
        "links": [
            ("Command center", "super:command_center", "stable", ("runtime", "override")),
            ("School Health", "super:tenant_health", "stable", ("runtime", "tenant override")),
            ("Incidents", "platform_incidents_console", "danger", ("runtime", "policy")),
            ("Pulse", "super:pulse", "beta", ("runtime", "observability")),
        ],
    },
    {
        "id": "tenants_schools",
        "title": "Tenants & Schools",
        "subtitle": "Provision, curriculum, geography",
        "links": [
            ("Schools list", "super:schools_list", "stable", ("runtime", "entitlement")),
            ("Setup Studio", "super:create_school_wizard", "stable", ("runtime", "blueprint")),
            ("Curriculum packs", "super:curriculum_packs", "stable", ("pack", "policy")),
            ("Geography", "super:geography", "stable", ("registry",)),
        ],
    },
    {
        "id": "runtime_policies",
        "title": "Runtime & Policies",
        "subtitle": "Blueprints, policies, feature state, simulation",
        "links": [
            ("Runtime inspector", "super:runtime_inspector", "stable", ("runtime",)),
            ("Blueprints catalog", "super:blueprints_catalog", "stable", ("pack", "policy")),
            ("Policies catalog", "super:policies_catalog", "stable", ("policy",)),
            ("Workflow simulator", "super:workflow_simulator", "beta", ("runtime", "policy")),
            ("Diff / impact summary", "studio_os:control_impact", "stable", ("policy", "runtime")),
            ("Feature control", "siteconfig:feature_control_panel", "danger", ("policy", "tenant override")),
            ("Feature audit", "siteconfig:feature_control_audit", "stable", ("policy",)),
            (
                "Runtime defaults (platform admin)",
                ("super:admin_bridge", {"bridge_key": "runtime_defaults"}),
                "stable",
                ("runtime",),
            ),
            (
                "Phase B domain snapshots (admin)",
                ("super:admin_bridge", {"bridge_key": "phase_b_domain_snapshots"}),
                "stable",
                ("runtime", "policy", "metadata"),
            ),
            (
                "Policy compatibility rules (admin)",
                ("super:admin_bridge", {"bridge_key": "policies_policycompatibilityrule"}),
                "stable",
                ("policy",),
            ),
            ("Rollback (Control)", "studio_os:rollback", "beta", ("policy", "tenant override")),
        ],
    },
    {
        "id": "packages_marketplace",
        "title": "Packages & Marketplace",
        "subtitle": "Install, rollout, governance",
        "links": [
            ("App catalog", "super:app_catalog", "stable", ("pack", "entitlement")),
            ("Package rollout", "super:package_rollout", "danger", ("pack", "override")),
            ("Staged activation", "studio_os:automation_staged_activation", "beta", ("pack", "policy")),
            ("Marketplace governance", "super:marketplace_governance", "stable", ("policy",)),
            ("Blueprint marketplace", "super:blueprint_marketplace", "stable", ("pack",)),
            (
                "Fleet governed changes",
                ("super:admin_bridge", {"bridge_key": "fleet_governed_changes"}),
                "beta",
                ("runtime", "policy"),
            ),
            (
                "Runtime defaults (preview & integration defaults)",
                ("super:admin_bridge", {"bridge_key": "runtime_defaults"}),
                "stable",
                ("runtime", "pack"),
            ),
            (
                "Fleet governed (super list)",
                "super:fleet_governed_changes",
                "beta",
                ("runtime",),
            ),
        ],
    },
    {
        "id": "brand_experience",
        "title": "Brand & Experience",
        "subtitle": "Themes, Studio Experience, outputs",
        "links": [
            (
                "Platform global branding (admin)",
                ("super:admin_bridge", {"bridge_key": "platform_global_branding"}),
                "stable",
                ("runtime", "pack"),
            ),
            (
                "Global brand registry (admin)",
                ("super:admin_bridge", {"bridge_key": "global_brand_registry"}),
                "stable",
                ("registry",),
            ),
            ("Studio OS", "studio_os:shell", "stable", ("runtime", "pack")),
            ("Studio Experience", "studio_os:experience", "stable", ("pack", "tenant override")),
            ("Theme & colors", "siteconfig:theme_colors", "stable", ("tenant override",)),
            ("Report library", "studio_os:output", "stable", ("runtime", "pack")),
        ],
    },
    {
        "id": "billing_commercial",
        "title": "Billing & Commercial",
        "subtitle": "Plans, accounts, usage signals",
        "links": [
            ("Billing dashboard", "super:billing_dashboard", "stable", ("entitlement",)),
            ("Customer success", "super:customer_success_dashboard", "stable", ("runtime",)),
        ],
    },
    {
        "id": "security_access",
        "title": "Security & Access",
        "subtitle": "Trust, compliance, access posture",
        "links": [
            ("Trust center", "super:trust_center", "stable", ("policy",)),
            ("Compliance overview", "super:compliance_overview", "stable", ("policy",)),
            ("Operator policy", "super:operator_policy", "stable", ("policy",)),
        ],
    },
    {
        "id": "observability",
        "title": "Observability",
        "subtitle": "Usage, analytics, platform signals",
        "links": [
            ("Usage", "super:usage", "stable", ("runtime",)),
            ("Analytics", "super:analytics_overview", "beta", ("runtime",)),
        ],
    },
    {
        "id": "registries_localization",
        "title": "Registries & Localization",
        "subtitle": "Metadata, registries, regional defaults",
        "links": [
            ("Registries overview", "super:registries_overview", "stable", ("registry", "policy")),
            (
                "Country registry (admin)",
                ("super:admin_bridge", {"bridge_key": "registries_countryregistry"}),
                "stable",
                ("registry",),
            ),
            ("Metadata catalog", "super:metadata_catalog", "stable", ("metadata",)),
        ],
    },
]


WHY_ENABLED_SUMMARY = (
    "Effective behavior combines platform defaults, registry, blueprint, policy bundle, "
    "entitlement, and tenant override — in that order. Follow the operator control model "
    "(capability families → grouped controls → impact → source tracing → staged changes → "
    "publish/rollback). Use Runtime inspector and Feature audit for evidence; fleet publish "
    "and rollback in Package rollout and Studio Control."
)

# Canonical “why enabled?” vocabulary (task 5) for operator-facing labels
SOURCE_LABELS: dict[str, str] = {
    "runtime": "Runtime",
    "pack": "Pack",
    "policy": "Policy",
    "entitlement": "Entitlement",
    "tenant override": "Tenant override",
    "tenant_override": "Tenant override",
    "override": "Override",
    "registry": "Registry",
    "metadata": "Metadata",
    "blueprint": "Blueprint",
    "observability": "Observability",
}

# Query strings for links that need mode or embed context (publish/rollback / impact path)
URL_SUFFIX_BY_NAME: dict[str, str] = {
    "studio_os:rollback": "?mode=control",
}


def _format_source_labels(sources: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for raw in sources:
        key = raw.strip().lower()
        out.append(SOURCE_LABELS.get(key, raw.strip()))
    return tuple(out)


def build_outcome_groups_for_request(request) -> list[dict[str, Any]]:
    """
    Resolved outcome groups for Configuration Control Center and Control Studio.
    Omits individual links that do not reverse; uses active ``request.urlconf`` then
    ``config.manager_urls`` so ``super:`` and manager-only names resolve on tenant hosts too.
    """
    out: list[dict[str, Any]] = []
    for spec in OUTCOME_GROUP_SPECS:
        links_out = []
        for label, url_ref, stability, sources in spec["links"]:
            url = _resolve_link_url(url_ref, request)
            if not url:
                continue
            suffix_key = url_ref if isinstance(url_ref, str) else url_ref[0]
            extra = URL_SUFFIX_BY_NAME.get(suffix_key)
            if extra:
                q = extra[1:] if extra.startswith("?") else extra
                url = f"{url}{'&' if '?' in url else '?'}{q}"
            src_display = _format_source_labels(sources)
            links_out.append(
                {
                    "label": label,
                    "url": url,
                    "stability": stability,
                    "sources": src_display,
                }
            )
        if links_out:
            out.append(
                {
                    "id": spec["id"],
                    "title": spec["title"],
                    "subtitle": spec["subtitle"],
                    "links": links_out,
                }
            )
    return out


def build_control_studio_rail_sections(request) -> list[dict[str, Any]]:
    """
    Full nine-group outcome registry for Control Studio (same data as CCC; different chrome).
    """
    return build_outcome_groups_for_request(request)


# Horizontal strip on Feature Control + super fleet config pages (impact / audit / rollout).
# Second element: URL name or (name, reverse kwargs) for admin bridges.
FEATURE_CONTROL_OPERATOR_QUICK_LINKS: tuple[tuple[str, LinkTarget, str], ...] = (
    ("Control Studio", "studio_os:control", "stable"),
    ("Configuration Control Center", "siteconfig:console_domains_hub", "stable"),
    ("Diff / impact summary", "studio_os:control_impact", "stable"),
    ("Runtime inspector", "super:runtime_inspector", "stable"),
    (
        "Runtime defaults (admin)",
        ("super:admin_bridge", {"bridge_key": "runtime_defaults"}),
        "stable",
    ),
    (
        "Platform global branding (admin)",
        ("super:admin_bridge", {"bridge_key": "platform_global_branding"}),
        "stable",
    ),
    (
        "Phase B domain snapshots (admin)",
        ("super:admin_bridge", {"bridge_key": "phase_b_domain_snapshots"}),
        "stable",
    ),
    ("Staged activation", "studio_os:automation_staged_activation", "beta"),
    ("Package rollout", "super:package_rollout", "danger"),
    ("Rollback (Control)", "studio_os:rollback", "beta"),
    ("Feature audit", "siteconfig:feature_control_audit", "stable"),
)


def build_feature_control_operator_quick_links(request) -> list[dict[str, Any]]:
    """
    Resolved tool strip for Feature Control and manager config grids.
    Omits ``super:`` targets on non-manager hosts so links are not dead on tenant subdomains.
    """
    host = getattr(request, "public_host_kind", None)
    out: list[dict[str, Any]] = []
    for label, url_ref, stability in FEATURE_CONTROL_OPERATOR_QUICK_LINKS:
        super_ref = (
            url_ref.startswith("super:")
            if isinstance(url_ref, str)
            else str(url_ref[0]).startswith("super:")
        )
        if host not in (None, "manager") and super_ref:
            continue
        if isinstance(url_ref, str):
            url = _rev(url_ref, request)
            suffix_key = url_ref
        else:
            viewname, kw = url_ref
            url = _rev_with_kwargs(viewname, kw, request)
            suffix_key = viewname
        if not url:
            continue
        url = _apply_url_suffix(url, suffix_key)
        out.append({"label": label, "url": url, "stability": stability})
    return out


def _apply_url_suffix(url: str, url_name: str) -> str:
    extra = URL_SUFFIX_BY_NAME.get(url_name)
    if not extra:
        return url
    q = extra[1:] if extra.startswith("?") else extra
    return f"{url}{'&' if '?' in url else '?'}{q}"


def build_operator_control_model_for_request(request) -> list[dict[str, Any]]:
    """
    Phase 3 — full operator control model (no partials): replaces “toggle cemeteries” with a
    six-step decision-console path. Each step has a primary surface plus optional related tools.

    1. Capability families — feature control (what is allowed).
    2. Grouped controls — catalogued toggles / platform registry (how flags are grouped).
    3. Impact summaries — diff / impact before change.
    4. Source tracing — runtime + audit (why enabled).
    5. Staged changes — staged activation lane.
    6. Publish / rollback — fleet rollout + control rollback + Experience publish.
    """
    from django.utils.translation import gettext as _

    step_defs: list[dict[str, Any]] = [
        {
            "id": "capability_families",
            "title": _("Capability families"),
            "description": _(
                "See capabilities as families (domains and flags), not raw model walls. "
                "This is the primary surface for understanding what is on or off for the tenant."
            ),
            "primary": (
                _("Feature control"),
                "siteconfig:feature_control_panel",
                "danger",
            ),
            "related": (
                (_("Plans & entitlements"), "super:billing_dashboard", "stable"),
                (
                    _("Integrations registry (admin)"),
                    ("super:admin_bridge", {"bridge_key": "integrations"}),
                    "stable",
                ),
            ),
        },
        {
            "id": "grouped_controls",
            "title": _("Grouped controls"),
            "description": _(
                "Platform feature toggles and catalogued controls — grouped, searchable "
                "maintenance surfaces instead of long undifferentiated walls."
            ),
            "primary": (
                _("Feature toggles catalog"),
                "super:feature_toggles_list",
                "stable",
            ),
            "related": (
                (_("Grading catalog"), "super:grading_list", "stable"),
            ),
        },
        {
            "id": "impact_summaries",
            "title": _("Impact summaries"),
            "description": _(
                "Review diff and impact summaries before you commit to a change — decision-console "
                "style, not blind saves."
            ),
            "primary": (
                _("Diff / impact summary"),
                "studio_os:control_impact",
                "stable",
            ),
            "related": (
                (_("Policy diff"), "super:policy_diff", "beta"),
            ),
        },
        {
            "id": "source_tracing",
            "title": _("Source tracing"),
            "description": _(
                "Trace why behavior is enabled: runtime resolution, policy, pack, entitlement, "
                "and tenant override — with inspector and audit evidence."
            ),
            "primary": (
                _("Runtime inspector"),
                "super:runtime_inspector",
                "stable",
            ),
            "related": (
                (_("Feature audit"), "siteconfig:feature_control_audit", "stable"),
                (
                    _("Runtime defaults"),
                    ("super:admin_bridge", {"bridge_key": "runtime_defaults"}),
                    "stable",
                ),
            ),
        },
        {
            "id": "staged_changes",
            "title": _("Staged changes"),
            "description": _(
                "Use staged activation for changes that should not hit everyone at once — "
                "governed rollout lanes instead of immediate fleet flips."
            ),
            "primary": (
                _("Staged activation"),
                "studio_os:automation_staged_activation",
                "beta",
            ),
            "related": (),
        },
        {
            "id": "publish_rollback",
            "title": _("Publish and rollback"),
            "description": _(
                "Ship or undo: marketplace and package rollout for fleet scope; Control rollback "
                "for feature state; Studio Experience for branded experience publish."
            ),
            "primary": (
                _("Package rollout"),
                "super:package_rollout",
                "danger",
            ),
            "related": (
                (_("Rollback (Control)"), "studio_os:rollback", "beta"),
                (_("Studio Experience (publish)"), "studio_os:experience", "stable"),
            ),
        },
    ]

    out: list[dict[str, Any]] = []
    for spec in step_defs:
        plabel, pname, pstab = spec["primary"]
        purl = _rev(pname, request)
        if not purl:
            continue
        purl = _apply_url_suffix(purl, pname)
        related_out: list[dict[str, Any]] = []
        for rlabel, rurl_ref, rstab in spec.get("related") or ():
            ru = _resolve_link_url(rurl_ref, request)
            if not ru:
                continue
            suffix_key = (
                rurl_ref if isinstance(rurl_ref, str) else str(rurl_ref[0])
            )
            ru = _apply_url_suffix(ru, suffix_key)
            related_out.append(
                {"label": rlabel, "url": ru, "stability": rstab}
            )
        out.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "description": spec["description"],
                "primary": {
                    "label": plabel,
                    "url": purl,
                    "stability": pstab,
                },
                "related": related_out,
            }
        )
    return out
