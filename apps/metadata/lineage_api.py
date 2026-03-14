"""
§3.3 Unified lineage API — single aggregation of usage_registry + package lineage + blast radius.

Answers "what uses this?" and "what does this use?" for entities, fields, packages, and consumers.
Used by governance UI and operator tooling. Staff-only.
"""
from __future__ import annotations

from typing import Any

# Soft-fail set for optional imports and DB (same as usage_registry)
from django.db import DatabaseError

_LINEAGE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


def get_unified_lineage(
    *,
    object_type: str,
    code: str | None = None,
    entity_code: str | None = None,
    field_name: str | None = None,
    package_id: str | None = None,
    consumer_type: str | None = None,
    consumer_code: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Single lineage response aggregating usage_registry (MetadataDependency),
    package registry (get_package_lineage_registry), and blast radius.

    Supported object_type and required params:
      - entity: code (entity_code)
      - field: entity_code + field_name
      - package: package_id
      - consumer: consumer_type + consumer_code (e.g. dashboard, principal_home)

    Returns:
      {
        "object": { "type", "identifier", ... },
        "downstream": [ { "consumer_type", "consumer_code", "entity_code", "field_name" }, ... ],
        "downstream_summary": { "consumer_count", "consumer_type_counts", "consumers": [...] },
        "packages": [ { "package_id", "version", "blast_radius", ... } ] (when relevant),
        "blast_radius": { "consumer_count", "consumer_type_counts", "consumers": [...] } (when entity/field),
      }
    """
    result: dict[str, Any] = {
        "object": {},
        "downstream": [],
        "downstream_summary": {"consumer_count": 0, "consumer_type_counts": {}, "consumers": []},
        "packages": [],
        "blast_radius": None,
    }
    try:
        from apps.metadata.services import (
            build_metadata_blast_radius,
            get_downstream_dependencies,
            get_package_lineage_registry,
            summarize_dependency_consumers,
        )
        from apps.metadata.models import FieldCatalogEntry
    except _LINEAGE_SOFT_FAILURES:
        return result

    object_type = (object_type or "").strip().lower()
    limit = max(1, min(500, limit))

    if object_type == "entity" and (code or entity_code):
        entity_code = (code or entity_code or "").strip()
        if not entity_code:
            return result
        result["object"] = {"type": "entity", "entity_code": entity_code}
        deps = get_downstream_dependencies(entity_code=entity_code)
        result["downstream"] = deps[:limit]
        blast = build_metadata_blast_radius(entity_codes=[entity_code])
        result["blast_radius"] = blast
        result["downstream_summary"] = {
            "consumer_count": blast["consumer_count"],
            "consumer_type_counts": blast["consumer_type_counts"],
            "consumers": blast["consumers"][:limit],
        }
        # Packages that reference this entity
        try:
            from apps.packages.models import PackageVersion
            for pkg in PackageVersion.objects.all().order_by("-created_at")[:50]:
                impact = pkg.impact_summary or {}
                codes = [c for c in (impact.get("entity_codes") or []) if c == entity_code]
                if codes:
                    reg = get_package_lineage_registry(package_id=pkg.package_id, limit=1)
                    if reg:
                        result["packages"].append(reg[0])
        except _LINEAGE_SOFT_FAILURES:
            pass
        return result

    if object_type == "field" and entity_code and field_name:
        entity_code = entity_code.strip()
        field_name = field_name.strip()
        if not entity_code or not field_name:
            return result
        try:
            field = FieldCatalogEntry.objects.select_related("entity").get(
                entity__code=entity_code,
                field_name=field_name,
            )
        except (FieldCatalogEntry.DoesNotExist, Exception):
            result["object"] = {"type": "field", "entity_code": entity_code, "field_name": field_name}
            return result
        result["object"] = {
            "type": "field",
            "entity_code": entity_code,
            "field_name": field_name,
            "field_id": field.id,
        }
        deps = get_downstream_dependencies(field_id=field.id)
        result["downstream"] = deps[:limit]
        blast = build_metadata_blast_radius(field_ids=[field.id])
        result["blast_radius"] = blast
        result["downstream_summary"] = {
            "consumer_count": blast["consumer_count"],
            "consumer_type_counts": blast["consumer_type_counts"],
            "consumers": blast["consumers"][:limit],
        }
        return result

    if object_type == "package" and (package_id or code):
        package_id = (package_id or code or "").strip()
        if not package_id:
            return result
        result["object"] = {"type": "package", "package_id": package_id}
        reg = get_package_lineage_registry(package_id=package_id, limit=10)
        result["packages"] = reg
        if reg:
            result["blast_radius"] = reg[0].get("blast_radius")
        return result

    if object_type == "consumer" and (consumer_type or consumer_code):
        consumer_type = (consumer_type or "").strip()
        consumer_code = (consumer_code or "").strip()
        if not consumer_type and not consumer_code:
            return result
        result["object"] = {"type": "consumer", "consumer_type": consumer_type, "consumer_code": consumer_code}
        rows = summarize_dependency_consumers(consumer_type=consumer_type or None, limit=limit)
        if consumer_code:
            rows = [r for r in rows if r.get("consumer_code") == consumer_code]
        result["downstream"] = []
        result["downstream_summary"] = {
            "consumer_count": len(rows),
            "consumer_type_counts": {consumer_type or "": len(rows)} if rows else {},
            "consumers": [
                {
                    "consumer_type": r.get("consumer_type"),
                    "consumer_code": r.get("consumer_code"),
                    "entity_codes": r.get("entity_codes", []),
                    "field_names": r.get("field_names", []),
                    "dependency_count": r.get("dependency_count", 0),
                }
                for r in rows[:limit]
            ],
        }
        return result

    return result
