"""
Map every Django admin app (and optional model) to a Phase 3 outcome group so Unfold
surfaces show the same operator language as CCC / control plane — without hand-editing
each ModelAdmin.

Used from ``config.admin.BaseRunMyCampusAdminSite.each_context`` for all authenticated
admin pages under /admin/<app>/…
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse

from apps.siteconfig.control_outcome_center import (
    OUTCOME_GROUP_SPECS,
    URL_SUFFIX_BY_NAME,
    _format_source_labels,
    _rev,
    build_outcome_groups_for_request,
)


def parse_admin_path(path: str) -> tuple[str, str | None] | None:
    """
    Return (app_label, model_name_or_none) for admin URLs.

    /admin/app/ -> (app, None)
    /admin/app/model/ -> (app, model)
    /admin/app/model/add/ -> (app, model)
    /admin/app/model/1/change/ -> (app, model)
    """
    raw = (path or "").split("?", 1)[0].strip()
    parts = [p for p in raw.split("/") if p]
    if len(parts) < 2 or parts[0] != "admin":
        return None
    app_label = parts[1]
    if len(parts) == 2:
        return app_label, None
    model_name = parts[2]
    return app_label, model_name


# Default outcome group per Django app_label. Unknown apps fall back to runtime_policies.
APP_LABEL_DEFAULT_OUTCOME: dict[str, str] = {
    "accounts": "security_access",
    "auth": "security_access",
    "academics": "registries_localization",
    "evals": "registries_localization",
    "reports": "brand_experience",
    "finance": "billing_commercial",
    "payroll": "billing_commercial",
    "billing": "billing_commercial",
    "siteconfig": "runtime_policies",
    "schools": "tenants_schools",
    "registries": "registries_localization",
    "policies": "runtime_policies",
    "automation": "packages_marketplace",
    "marketplace": "packages_marketplace",
    "observability": "observability",
    "portal": "brand_experience",
    "compliance": "security_access",
    "integrations": "packages_marketplace",
    "metadata": "registries_localization",
    "people": "tenants_schools",
    "studio_os": "brand_experience",
    "apicenter": "observability",
    "analytics": "observability",
    "communication": "brand_experience",
    "customersuccess": "billing_commercial",
    "emis": "registries_localization",
    "global_registries": "registries_localization",
    "requests": "security_access",
    "staff": "tenants_schools",
    "student360": "tenants_schools",
    "student": "tenants_schools",
    "teacher": "tenants_schools",
    "parent": "tenants_schools",
    "packages": "packages_marketplace",
    "platform_runtime": "runtime_policies",
    "brand_experience": "brand_experience",
    "contenttypes": "runtime_policies",
    "sessions": "runtime_policies",
    "django_celery_beat": "runtime_policies",
    "django_celery_results": "runtime_policies",
    "admin": "runtime_policies",
    "sites": "runtime_policies",
    "flatpages": "brand_experience",
    "guardian": "security_access",
    "otp_static": "security_access",
    "otp_totp": "security_access",
    "axes": "security_access",
    "waffle": "runtime_policies",
}

# Fine-grained overrides: "app_label.modelname" (lowercase) -> outcome id
MODEL_OUTCOME_OVERRIDES: dict[str, str] = {
    "siteconfig.featuretoggledefinition": "runtime_policies",
    "siteconfig.featuretogglestate": "runtime_policies",
    "accounts.user": "security_access",
    "accounts.accessrole": "security_access",
    "auth.group": "security_access",
    "people.studentprofile": "tenants_schools",
    "finance.invoice": "billing_commercial",
}


def resolve_outcome_id(app_label: str, model_name: str | None) -> str:
    if model_name:
        key = f"{app_label}.{model_name}".lower()
        if key in MODEL_OUTCOME_OVERRIDES:
            return MODEL_OUTCOME_OVERRIDES[key]
    return APP_LABEL_DEFAULT_OUTCOME.get(app_label, "runtime_policies")


def _spec_by_id(outcome_id: str) -> dict[str, Any] | None:
    for spec in OUTCOME_GROUP_SPECS:
        if spec["id"] == outcome_id:
            return spec
    return None


def _tenant_operator_shortcuts() -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for label, name in (
        ("Configuration Control Center", "siteconfig:console_domains_hub"),
        ("Feature control", "siteconfig:feature_control_panel"),
        ("Feature audit", "siteconfig:feature_control_audit"),
        ("Studio", "studio_os:shell"),
    ):
        try:
            links.append({"label": label, "url": reverse(name)})
        except NoReverseMatch:
            continue
    return links


def build_admin_outcome_deck_context(
    request, *, is_platform_site: bool
) -> dict[str, Any] | None:
    """
    Context for ``admin/includes/admin_operator_outcome_deck.html``.
    Returns None when not on an admin app/model path.
    """
    parsed = parse_admin_path(getattr(request, "path", "") or "")
    if not parsed:
        return None
    app_label, model_name = parsed
    outcome_id = resolve_outcome_id(app_label, model_name)
    resolved_groups = build_outcome_groups_for_request(request)
    group = next((g for g in resolved_groups if g["id"] == outcome_id), None)
    spec = _spec_by_id(outcome_id)

    title = (group or spec or {}).get("title") if (group or spec) else outcome_id
    subtitle = (group or spec or {}).get("subtitle", "") if (group or spec) else ""
    links_out: list[dict[str, Any]] = []
    if group and group.get("links"):
        links_out = list(group["links"][:8])
    elif spec:
        for label, url_name, stability, sources in spec["links"][:8]:
            url = _rev(url_name, request)
            if not url:
                continue
            extra = URL_SUFFIX_BY_NAME.get(url_name)
            if extra:
                q = extra[1:] if extra.startswith("?") else extra
                url = f"{url}{'&' if '?' in url else '?'}{q}"
            links_out.append(
                {
                    "label": label,
                    "url": url,
                    "stability": stability,
                    "sources": _format_source_labels(sources),
                }
            )

    ctx: dict[str, Any] = {
        "admin_deck_app_label": app_label,
        "admin_deck_model_name": model_name,
        "admin_deck_outcome_id": outcome_id,
        "admin_deck_title": title,
        "admin_deck_subtitle": subtitle,
        "admin_deck_links": links_out,
        "admin_deck_is_platform": bool(is_platform_site),
    }
    if not is_platform_site:
        ctx["admin_deck_tenant_shortcuts"] = _tenant_operator_shortcuts()
    else:
        ctx["admin_deck_tenant_shortcuts"] = []
    return ctx
