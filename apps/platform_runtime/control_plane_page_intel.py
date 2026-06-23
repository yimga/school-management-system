"""Page intelligence for the manager / operator control plane.

Single source of truth that makes the "About this page" explainer
(``apps.siteconfig.ui_route_help``) and the "Your flow" launchpad
(``apps.platform_runtime.action_engine``) **aggressively page-aware**: each
manager route declares what the page IS (title + one-line purpose) and the
logical next steps FROM it, so neither surface falls back to one generic blurb
for every page.

Both consumers degrade safely:
  * a not-explicitly-mapped manager route still gets a page-specific title
    (humanised ``url_name``) + a section descriptor instead of the old flat
    "Operator workspace" default;
  * every flow URL is resolved through ``reverse()`` at call time and skipped
    when it does not resolve, so referencing a not-yet-wired route is harmless.

Keep this list curated, not exhaustive — the humanised fallback covers the long
tail, this map gives the high-traffic operator pages first-class, hand-written
guidance + a real onward flow.
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# viewname -> page intelligence. ``flow`` is the ordered list of the logical
# next viewnames FROM this page; each target is itself described by its own
# entry here (or humanised if it is only a flow target).
# ``priority`` orders the step within "Your flow".
# ---------------------------------------------------------------------------
MANAGER_PAGES: dict[str, dict[str, Any]] = {
    "super:dashboard": {
        "title": "Control plane home",
        "body": "Portfolio pulse, globe footprint, and the tenant heatmap — your operator landing.",
        "priority": 60,
        "flow": ("super:tenant_health", "super:command_center", "super:schools_list"),
    },
    "super:schools_list": {
        "title": "School directory",
        "body": "Query every tenant, open Tenant 360, and run lifecycle actions.",
        "priority": 90,
        "flow": ("super:tenant_health", "super:command_center", "super:offboarding_queue"),
    },
    "super:tenant_health": {
        "title": "Tenant health grid",
        "body": "Health scores, onboarding stage, and the schools that need attention first.",
        "priority": 85,
        "flow": ("super:schools_list", "super:command_center", "super:dashboard"),
    },
    "super:command_center": {
        "title": "Operational queues",
        "body": "Support backlog, provisioning SLA breaches, and approvals waiting on you.",
        "priority": 80,
        "flow": ("super:tenant_health", "super:schools_list", "super:offboarding_queue"),
    },
    "super:offboarding_queue": {
        "title": "Offboarding queue",
        "body": "Wind-down, data export, and scheduled-purge workflows in flight.",
        "priority": 75,
        "flow": ("super:schools_list", "super:tenant_health", "super:command_center"),
    },
    "super:founder_dashboard": {
        "title": "Founder metrics",
        "body": "Platform closure metrics, growth posture, and audit standing.",
        "priority": 55,
        "flow": ("super:dashboard", "super:tenant_health", "super:command_center"),
    },
    "siteconfig:console_domains_hub": {
        "title": "Configuration center",
        "body": "Domains, DNS, branding, and platform wiring with safe defaults.",
        "priority": 50,
        "flow": ("super:dashboard", "super:schools_list", "super:tenant_health"),
    },
}

# When the exact route is not mapped, the section (resolver namespace) still
# leads somewhere sensible instead of the flat global list.
SECTION_DEFAULT_FLOW: dict[str, tuple[str, ...]] = {
    "super": (
        "super:tenant_health",
        "super:command_center",
        "super:schools_list",
        "super:dashboard",
    ),
    "siteconfig": (
        "siteconfig:console_domains_hub",
        "super:dashboard",
        "super:schools_list",
    ),
    "schools": (
        "super:schools_list",
        "super:tenant_health",
        "super:command_center",
    ),
}

# Ordered global fallback (mirrors the prior fixed behaviour) — last resort so
# the strip always has a non-empty flow on the control plane.
GLOBAL_FLOW: tuple[str, ...] = (
    "super:schools_list",
    "super:tenant_health",
    "super:command_center",
    "super:offboarding_queue",
    "super:dashboard",
    "super:founder_dashboard",
    "siteconfig:console_domains_hub",
)

# Per-namespace one-liner used to build a page-specific body when a route is
# not explicitly mapped (still far better than one flat blurb). Used by BOTH
# the manager "About this page" fallback AND the tenant fallback in
# ``apps.siteconfig.ui_route_help.resolve_route_help`` — so an unmapped page on
# either host describes its own section instead of the generic "School
# workspace" / "Operator workspace" default. Keep this broad: every namespace a
# user can land on should have a descriptor here.
SECTION_DESCRIPTOR: dict[str, str] = {
    # --- operator / platform control plane ---
    "super": "operator control plane",
    "siteconfig": "platform configuration",
    "schools": "tenant operations",
    "studio_os": "studio workspace",
    "setup_studio": "guided setup studio",
    "brand_experience": "brand & experience studio",
    "billing": "billing & revenue",
    "plans_entitlements": "plans & entitlements",
    "migration_cloud": "migration cloud",
    "compliance": "compliance & audit",
    "governance": "governance & policy",
    "policies": "access policy",
    "observability": "platform observability",
    "marketplace": "marketplace",
    "integrations_marketplace": "integrations",
    "apicenter": "developer & API center",
    "platform_runtime": "platform runtime",
    "orchestration": "workflow orchestration",
    "sync_engine": "data sync engine",
    "tenancy": "tenancy administration",
    "metadata": "metadata & catalog",
    "registries": "platform registries",
    "global_registries": "global registries",
    "runtime_blueprints": "runtime blueprints",
    "packages": "packages & bundles",
    "customersuccess": "customer success",
    "sales": "sales & growth",
    "automation": "automation",
    # --- tenant-facing school operations ---
    "portal": "your school portal",
    "accounts": "your account & access",
    "authentication": "sign-in & security",
    "people": "people & admissions",
    "admissions": "admissions pipeline",
    "academics": "academics & curriculum",
    "evals": "assessment & grading",
    "student360": "student 360",
    "emis": "school information system",
    "finance": "finance",
    "payroll": "payroll",
    "analytics": "analytics & insight",
    "reports": "reports & insight",
    "communication": "communication",
    "social_media": "social & outreach",
    "events": "events",
    "school_events": "school events",
    "feedback": "help & feedback",
    "requests": "requests & approvals",
    "safeguarding": "safeguarding",
    "schoolops": "school operations",
    "lifecycle": "student lifecycle",
    "assist_dock": "assist dock",
    "sync": "data sync",
}

_DEFAULT_STEP_PRIORITY = 40


def resolve_manager_page(view_name: str) -> Optional[dict[str, Any]]:
    """Return the first-class page-intel entry for a manager route, or None."""
    if not view_name:
        return None
    return MANAGER_PAGES.get(view_name)


def humanised_page_help(view_name: str, namespace: str) -> Optional[tuple[str, str]]:
    """``(title, body)`` for ANY route (manager or tenant) not explicitly mapped:
    humanise the ``url_name`` and append the section descriptor for its namespace.
    Returns ``None`` when there is no ``url_name`` to humanise (caller then uses
    the host-level default). Namespace-agnostic so the tenant "About this page"
    fallback gets a page-specific title + section context too."""
    url_name = view_name.split(":", 1)[-1] if view_name else ""
    if not url_name:
        return None
    title = url_name.replace("_", " ").replace("-", " ").strip().title()
    if not title:
        return None
    descriptor = SECTION_DESCRIPTOR.get(namespace or "")
    body = f"{title} — {descriptor}." if descriptor else f"{title}."
    return title, body


def _flow_targets(view_name: str, namespace: str) -> tuple[str, ...]:
    entry = MANAGER_PAGES.get(view_name)
    if entry and entry.get("flow"):
        return tuple(entry["flow"])
    if namespace and namespace in SECTION_DEFAULT_FLOW:
        return SECTION_DEFAULT_FLOW[namespace]
    return GLOBAL_FLOW


def manager_flow_steps(view_name: str, namespace: str) -> list[dict[str, Any]]:
    """Ordered next-step descriptors ``{viewname,title,body,priority}`` FROM the
    current manager page. Each target is described by its own ``MANAGER_PAGES``
    entry; targets that exist only as flow destinations get a humanised label.
    URL resolution and current-page exclusion are the caller's job (so this
    stays import-light and unit-testable without the URLconf)."""
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in _flow_targets(view_name, namespace):
        if not target or target in seen or target == view_name:
            continue
        seen.add(target)
        meta = MANAGER_PAGES.get(target)
        if meta:
            steps.append(
                {
                    "viewname": target,
                    "title": meta["title"],
                    "body": meta["body"],
                    "priority": int(meta.get("priority", _DEFAULT_STEP_PRIORITY)),
                }
            )
            continue
        hum = humanised_page_help(target, target.split(":", 1)[0])
        if hum:
            steps.append(
                {
                    "viewname": target,
                    "title": hum[0],
                    "body": hum[1],
                    "priority": _DEFAULT_STEP_PRIORITY,
                }
            )
    return steps
