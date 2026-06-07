"""
Build PackageVersion.payload_sections for marketplace catalog apps (73 slugs).

Each first-party MarketplaceApp slug maps 1:1 to a PackageVersion row so
activate_sandbox_installation can apply real pack content via PackageEngine.
"""

from __future__ import annotations

from typing import Any

from apps.marketplace.capability_contract import (
    _integration_adapter_target,
    enrich_manifest_capability_bindings,
    extract_capability_bindings,
)


def resolve_package_id_for_app(slug: str, manifest: dict[str, Any] | None) -> str:
    """Package id used by capability_bindings (defaults to marketplace slug)."""
    enriched = enrich_manifest_capability_bindings(slug, manifest or {})
    for binding in extract_capability_bindings(enriched):
        if binding.get("kind") == "package_id" and binding.get("target"):
            return str(binding["target"]).strip()
    return (slug or "").strip()


def _primary_section_for_slug(slug: str) -> str:
    """Map slug to a PackageEngine-recognized payload_sections key."""
    s = (slug or "").lower()
    if "workflow" in s or s in ("attendance-intervention-pack", "procurement-vendor-management"):
        return "workflow"
    if any(
        token in s
        for token in (
            "analytics",
            "insights",
            "executive",
            "student-360",
            "dashboard",
            "grade-publishing",
        )
    ):
        return "dashboard"
    if any(token in s for token in ("compliance", "audit", "backup-disaster")):
        return "policy"
    if "portal-theme" in s or s.endswith("-themes-pack"):
        return "theme"
    if s.startswith("country-bundle") or s.endswith("-starter") or "onboarding" in s:
        return "blueprint"
    if any(
        s.startswith(prefix)
        for prefix in (
            "sis-bridge",
            "lms-bridge",
            "payments",
            "messaging",
            "identity",
            "iot-",
        )
    ):
        return "experience_pack"
    if s in ("migration-connector-pack", "api-webhooks-pack", "sso-identity"):
        return "experience_pack"
    if s.endswith("-pack") or s.endswith("-tracker") or s.endswith("-pro"):
        return "experience_pack"
    return "experience_pack"


def build_marketplace_package_payload(
    *,
    slug: str,
    name: str,
    version: str,
    manifest: dict[str, Any] | None,
    description: str = "",
) -> dict[str, Any]:
    """
    Return non-empty payload_sections for PackageVersion (always includes catalog metadata).
    """
    enriched = enrich_manifest_capability_bindings(slug, manifest or {})
    section = _primary_section_for_slug(slug)
    bindings = extract_capability_bindings(enriched)
    adapter = _integration_adapter_target(slug)
    body: dict[str, Any] = {
        "app_slug": slug,
        "app_name": name,
        "catalog_version": version,
        "description": (description or "")[:500],
        "wedge_ids": list(enriched.get("wedge_ids") or []),
        "scopes": list(enriched.get("scopes") or []),
        "enabled_features": list(enriched.get("enabled_features") or []),
        "capability_bindings": bindings,
        "widgets": dict(enriched.get("widgets") or {})
        if isinstance(enriched.get("widgets"), dict)
        else {},
        "package_id": resolve_package_id_for_app(slug, enriched),
        "source": "marketplace_catalog_package_seed",
    }
    if adapter:
        body["integration_adapter"] = adapter
    if section == "workflow":
        body["pack"] = slug
        body["trigger_events"] = ["app_installed", "marketplace_app_installed"]
    elif section == "dashboard":
        body["surface"] = slug.replace("-", "_")
        body["widget_ids"] = list(body.get("widgets") or {})
    elif section == "policy":
        body["bundle"] = slug
    elif section == "blueprint":
        body["family"] = slug
    elif section == "theme":
        body["preset"] = slug
    return {section: body}


def catalog_app_package_rows(
    first_party_apps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expand FIRST_PARTY_APPS seed list into PackageVersion upsert rows."""
    rows: list[dict[str, Any]] = []
    for app_def in first_party_apps:
        slug = str(app_def.get("slug") or "").strip()
        if not slug:
            continue
        manifest = app_def.get("manifest") or {}
        version = str(app_def.get("version") or "1.0").strip()
        package_id = resolve_package_id_for_app(slug, manifest)
        payload_sections = build_marketplace_package_payload(
            slug=slug,
            name=str(app_def.get("name") or slug),
            version=version,
            manifest=manifest,
            description=str(app_def.get("description") or ""),
        )
        rows.append(
            {
                "package_id": package_id,
                "version": version,
                "slug": slug,
                "payload_sections": payload_sections,
                "changelog_summary": (
                    f"Marketplace catalog pack: {app_def.get('name') or slug}"
                )[:500],
                "compatibility": {"min_platform": "2025.03", "catalog_slug": slug},
            }
        )
    return rows
