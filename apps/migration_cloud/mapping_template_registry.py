"""Deterministic vendor column-map registry — repeat supplier CSV ~0% mapping review.

``MigrationConnectorProfile.mapping_template`` stores platform-curated and
operator-confirmed column maps. The pipeline applies them BEFORE the universal
mapper (same merge pattern as accelerators), so a second PowerSchool export
skips AI tiebreakers entirely when the profile key matches.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Template shape::
#
#   {
#     "by_artifact": {
#       "students.csv": {
#         "domain": "students",
#         "canonical_mappings": {"Student_Number": "external_id", ...},
#       },
#     },
#     "by_domain": {
#       "students": {"Student_Number": "external_id", ...},
#     },
#   }


def resolve_connector_profile_key(bundle: Any) -> str:
    """Best-effort profile key from bundle source classification."""
    if not bundle:
        return ""
    hint = str(getattr(bundle, "source_hint", "") or "").strip()
    if hint:
        return hint
    discovery = getattr(bundle, "discovery_summary", None) or {}
    source = discovery.get("source") or {}
    return str(source.get("chosen") or "").strip()


def _artifact_lookup_keys(artifact_path: str) -> list[str]:
    """Keys to try when matching a template entry to an artifact."""
    path = (artifact_path or "").strip().replace("\\", "/")
    if not path:
        return []
    basename = path.rsplit("/", 1)[-1]
    keys = [path]
    if basename and basename != path:
        keys.append(basename)
    return keys


def load_profile_template_entry(
    *,
    profile_key: str,
    artifact_path: str,
    domain: str,
) -> dict[str, Any] | None:
    """Return ``{domain, canonical_mappings}`` for this artifact, if seeded."""
    if not profile_key:
        return None
    try:
        from apps.migration_cloud.models_connectors import MigrationConnectorProfile
    except ImportError:  # pragma: no cover
        return None

    profile = (
        MigrationConnectorProfile.objects.filter(key=profile_key, active=True)
        .only("mapping_template")
        .first()
    )
    if profile is None:
        return None
    template = profile.mapping_template or {}
    if not isinstance(template, dict):
        return None

    by_artifact = template.get("by_artifact") or {}
    for key in _artifact_lookup_keys(artifact_path):
        entry = by_artifact.get(key)
        if isinstance(entry, dict) and entry.get("canonical_mappings"):
            return {
                "domain": str(entry.get("domain") or domain),
                "canonical_mappings": dict(entry.get("canonical_mappings") or {}),
                "method": "profile_template",
            }

    by_domain = template.get("by_domain") or {}
    domain_maps = by_domain.get(domain)
    if isinstance(domain_maps, dict) and domain_maps:
        return {
            "domain": domain,
            "canonical_mappings": dict(domain_maps),
            "method": "profile_template_domain",
        }
    return None


def merge_template_mappings(
    *,
    artifact,
    domain: str,
    bundle: Any,
    pre_mappings_dict: dict[str, str] | None = None,
    pre_domain: str | None = None,
) -> tuple[dict[str, str], str, str | None]:
    """Overlay profile template maps onto accelerator pre-maps (template wins)."""
    merged = dict(pre_mappings_dict or {})
    effective_domain = pre_domain or domain
    method: str | None = None

    profile_key = resolve_connector_profile_key(bundle)
    entry = load_profile_template_entry(
        profile_key=profile_key,
        artifact_path=getattr(artifact, "path_within_bundle", "") or getattr(artifact, "filename", ""),
        domain=domain,
    )
    if entry:
        merged.update(entry.get("canonical_mappings") or {})
        effective_domain = str(entry.get("domain") or effective_domain)
        method = str(entry.get("method") or "profile_template")

    return merged, effective_domain, method


def _deep_merge_template(existing: dict, incoming: dict) -> dict:
    out = dict(existing or {})
    for section, payload in (incoming or {}).items():
        if not isinstance(payload, dict):
            out[section] = payload
            continue
        current = out.get(section)
        if not isinstance(current, dict):
            out[section] = dict(payload)
            continue
        if section in ("by_artifact", "by_domain"):
            merged_section = dict(current)
            for key, entry in payload.items():
                if key not in merged_section:
                    merged_section[key] = entry
                    continue
                prior = merged_section[key]
                if isinstance(prior, dict) and isinstance(entry, dict):
                    combined = dict(prior)
                    if "canonical_mappings" in entry:
                        maps = dict(prior.get("canonical_mappings") or {})
                        maps.update(entry.get("canonical_mappings") or {})
                        combined["canonical_mappings"] = maps
                    if entry.get("domain"):
                        combined["domain"] = entry["domain"]
                    merged_section[key] = combined
                else:
                    merged_section[key] = entry
            out[section] = merged_section
        else:
            out[section] = {**current, **payload}
    return out


def persist_bundle_mappings_to_profile(
    *,
    bundle: Any,
    artifact_path: str,
    mappings: list[dict[str, Any]],
    domain: str,
) -> bool:
    """Upsert operator-confirmed maps into the connector profile registry."""
    profile_key = resolve_connector_profile_key(bundle)
    if not profile_key or not mappings:
        return False
    canonical: dict[str, str] = {}
    for row in mappings:
        src = str(row.get("source_column") or "").strip()
        dest = str(row.get("canonical_field") or "").strip()
        if src and dest and not dest.startswith("custom_fields."):
            canonical[src] = dest
    if not canonical:
        return False

    try:
        from apps.migration_cloud.models_connectors import MigrationConnectorProfile
    except ImportError:  # pragma: no cover
        return False

    profile = MigrationConnectorProfile.objects.filter(key=profile_key).first()
    if profile is None:
        return False

    basename = (artifact_path or "").rsplit("/", 1)[-1]
    patch = {
        "by_artifact": {
            artifact_path: {"domain": domain, "canonical_mappings": canonical},
        },
        "by_domain": {domain: canonical},
    }
    if basename and basename != artifact_path:
        patch["by_artifact"][basename] = {"domain": domain, "canonical_mappings": canonical}

    profile.mapping_template = _deep_merge_template(profile.mapping_template or {}, patch)
    profile.save(update_fields=["mapping_template", "updated_at"])
    logger.info(
        "mapping_template_registry: persisted %s columns to profile %s artifact %s",
        len(canonical),
        profile_key,
        artifact_path,
    )
    return True


def persist_confirmed_connector_mappings(
    *,
    connection: Any,
    entity_type: str,
) -> bool:
    """Mirror confirmed ``MigrationFieldMapping`` rows into ``mapping_template``."""
    profile = getattr(connection, "connector_profile", None)
    if profile is None:
        return False
    try:
        from apps.migration_cloud.models_connectors import (
            FieldMappingStatus,
            MigrationFieldMapping,
        )
    except ImportError:  # pragma: no cover
        return False

    rows = MigrationFieldMapping.objects.filter(
        school=connection.school,
        source_connection=connection,
        source_entity=entity_type,
        status=FieldMappingStatus.CONFIRMED,
    ).exclude(destination_field="")
    canonical = {
        str(r.source_field): str(r.destination_field)
        for r in rows
        if r.source_field and r.destination_field
    }
    if not canonical:
        return False

    patch = {"by_domain": {entity_type: canonical}}
    profile.mapping_template = _deep_merge_template(profile.mapping_template or {}, patch)
    profile.save(update_fields=["mapping_template", "updated_at"])
    return True


def build_powerschool_mapping_template() -> dict[str, Any]:
    """Seed template from the PowerSchool accelerator file map."""
    from apps.migration_cloud.accelerators.powerschool import POWERSCHOOL_FILE_MAP

    by_artifact: dict[str, Any] = {}
    by_domain: dict[str, dict[str, str]] = {}
    for filename, (domain, mappings) in POWERSCHOOL_FILE_MAP.items():
        by_artifact[filename] = {
            "domain": domain,
            "canonical_mappings": dict(mappings),
        }
        domain_acc = dict(by_domain.get(domain) or {})
        domain_acc.update(mappings)
        by_domain[domain] = domain_acc
    return {"by_artifact": by_artifact, "by_domain": by_domain}


__all__ = [
    "build_powerschool_mapping_template",
    "load_profile_template_entry",
    "merge_template_mappings",
    "persist_bundle_mappings_to_profile",
    "persist_confirmed_connector_mappings",
    "resolve_connector_profile_key",
]
