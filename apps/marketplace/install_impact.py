"""
N17: Build install-impact payload for marketplace UI (package preview + scopes + compatibility).
Used before sandbox install (tenant catalog and control-plane catalog).
"""

from __future__ import annotations

from typing import Any

from apps.marketplace.services import check_app_compatibility


def build_tenant_install_impact(school, app) -> dict[str, Any]:
    from apps.packages.engine import (
        list_reverse_dependent_package_ids,
        normalize_declared_dependencies,
        preview_diff,
    )
    from apps.packages.models import InstalledPackage, PackageVersion

    manifest = app.manifest or {}
    package_candidates: list[str] = []
    pid = (manifest.get("package_id") or "").strip()
    if pid:
        package_candidates.append(pid)
    package_candidates.append(app.slug)
    wedge_slug = f"wedge-pack-{str(app.slug).replace('_', '-')}"[:120]
    if wedge_slug not in package_candidates:
        package_candidates.append(wedge_slug)
    deduped: list[str] = []
    seen: set[str] = set()
    for x in package_candidates:
        if x and x not in seen:
            seen.add(x)
            deduped.append(x)
    package_candidates = deduped

    compat_ok, warnings, errors = check_app_compatibility(school, app, warn_only=True)
    scopes = list(app.scopes.values("scope_code", "description", "sensitive"))

    package_preview: dict[str, Any] | None = None
    package_id_used: str | None = None
    pv_used = None
    for pid in package_candidates:
        pv = (
            PackageVersion.objects.filter(package_id=pid)
            .order_by("-created_at")
            .first()
        )
        if not pv or not (pv.payload_sections or {}):
            continue
        try:
            package_preview = preview_diff(
                school.pk,
                pid,
                pv.version,
                dict(pv.payload_sections or {}),
            )
            package_id_used = pid
            pv_used = pv
            break
        except (TypeError, ValueError, AttributeError):
            package_preview = None

    inst_summary: dict[str, Any] = {}
    for pid in package_candidates:
        inst = (
            InstalledPackage.objects.filter(
                package_id=pid, school=school, is_active=True
            )
            .order_by("-applied_at")
            .first()
        )
        if inst and (inst.impact_summary or {}):
            inst_summary = dict(inst.impact_summary or {})
            break

    upstream: list[str] = []
    downstream: list[str] = []
    if package_id_used:
        if pv_used:
            try:
                upstream = normalize_declared_dependencies(pv_used.dependencies)
            except ValueError:
                upstream = []
        downstream = list_reverse_dependent_package_ids(package_id_used)

    return {
        "app": {
            "id": app.pk,
            "name": app.name,
            "slug": app.slug,
            "version": app.version,
        },
        "scopes": scopes,
        "compatibility": {
            "ok": compat_ok,
            "warnings": list(warnings or []),
            "errors": list(errors or []),
        },
        "package_resolution": {
            "candidates": package_candidates,
            "matched_package_id": package_id_used,
        },
        "dependency_graph": {
            "upstream_package_ids": upstream,
            "downstream_package_ids": downstream,
            "matched_package_id": package_id_used,
        },
        "package_impact_preview": package_preview,
        "installed_impact_summary": inst_summary,
        "rollback": {
            "sandbox": "Uninstall from Installed apps at any time.",
            "activation": "Sandbox installs stay out of live navigation until you activate.",
        },
    }
