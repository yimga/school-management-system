"""Tenant sovereignty kernel — satisfies fintech/HR prerequisites without operator-only wizard.

Uses school ``country_code`` + open-source stack defaults (PostgreSQL tenant schema,
Caddy reverse proxy, Let's Encrypt ACME). No paid edge vendor required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def sovereignty_kernel_ready(school: Any) -> bool:
    if school is None:
        return False
    settings = getattr(school, "settings", None) or {}
    if settings.get("sovereignty_kernel_ready"):
        return True
    sk = (settings.get("sovereignty") or {})
    if sk.get("jurisdiction_seeded"):
        return True
    cc = (getattr(school, "country_code", None) or "").strip()
    return bool(cc and settings.get("operational_kernel_version"))


def ensure_sovereignty_kernel_for_tenant(*, school: Any, dry_run: bool = False) -> dict[str, Any]:
    """Seed jurisdiction + mark prerequisite wizard complete for tenant admins."""
    from apps.setup_studio.models import SetupProgress

    cc = (getattr(school, "country_code", None) or "US").strip().upper()
    region_map = {
        "US": "us-east", "CA": "ca-central", "GB": "eu-west", "FR": "eu-west",
        "DE": "eu-central", "IN": "ap-south", "NG": "af-west", "CM": "af-central",
        "AE": "me-central", "SA": "me-central", "AU": "ap-southeast",
    }
    region = region_map.get(cc, "global")

    if dry_run:
        return {"country_code": cc, "data_residency_region": region, "dry_run": True}

    settings = dict(getattr(school, "settings", None) or {})
    settings["sovereignty"] = {
        "jurisdiction_seeded": True,
        "country_code": cc,
        "data_residency_region": region,
        "edge_stack": "caddy-acme",  # OSS: Caddy + Let's Encrypt; not Cloudflare Workers
        "seeded_at": datetime.now(timezone.utc).isoformat(),
    }
    settings["sovereignty_kernel_ready"] = True
    school.settings = settings
    school.save(update_fields=["settings"])

    progress, _ = SetupProgress.objects.get_or_create(school=school)
    step_state = dict(progress.step_state or {})
    wizards = dict(step_state.get("wizards") or {})
    wizards["multi_campus_local_sovereignty"] = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "completed": [
            "jurisdiction_mapping",
            "dynamic_core_routing",
            "cultural_vocabulary_injection",
            "statutory_alignment",
        ],
        "answers": {
            "jurisdiction_mapping": {
                "country_code": cc,
                "data_residency_region": region,
            },
        },
        "kernel_auto_seeded": True,
    }
    step_state["wizards"] = wizards
    progress.step_state = step_state
    progress.save(update_fields=["step_state"])

    return {"country_code": cc, "data_residency_region": region, "wizard_marked_complete": True}


def _sovereignty_settings(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    return dict(settings.get("sovereignty") or {})


def _persist_sovereignty(school: Any | None, sk: dict[str, Any]) -> None:
    if school is None:
        return
    settings = dict(getattr(school, "settings", None) or {})
    sk["updated_at"] = datetime.now(timezone.utc).isoformat()
    settings["sovereignty"] = sk
    settings["sovereignty_kernel_ready"] = True
    school.settings = settings
    school.save(update_fields=["settings"])


def apply_dynamic_routing(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    routing = payload.get("value") or payload.get("routing") or payload
    sk = _sovereignty_settings(school)
    sk["dynamic_core_routing"] = routing
    sk["edge_stack"] = sk.get("edge_stack") or "caddy-acme"
    _persist_sovereignty(school, sk)
    return {"ok": True, "dynamic_core_routing": routing}


def apply_statutory_alignment(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("value") or payload.get("statutory_schema")
    sk = _sovereignty_settings(school)
    sk["statutory_schema"] = schema
    _persist_sovereignty(school, sk)
    return {"ok": True, "statutory_schema": schema}


def apply_jurisdiction_mapping(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    cc = payload.get("country_code")
    state = payload.get("state_code")
    region = payload.get("data_residency_region")
    for field, val in (("country_code", cc), ("state_code", state), ("data_residency_region", region)):
        if val and hasattr(school, field):
            setattr(school, field, val)
    update_fields = [f for f in ("country_code", "state_code", "data_residency_region") if hasattr(school, f) and getattr(school, f)]
    if update_fields:
        school.save(update_fields=update_fields)
    sk = _sovereignty_settings(school)
    sk["jurisdiction"] = {
        "country_code": cc,
        "state_code": state,
        "data_residency_region": region,
    }
    _persist_sovereignty(school, sk)
    return {"ok": True, "jurisdiction": sk["jurisdiction"]}


def apply_vocabulary_pack(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    pack = payload.get("value") or payload.get("vocabulary_pack") or payload
    sk = _sovereignty_settings(school)
    sk["vocabulary_pack"] = pack
    _persist_sovereignty(school, sk)
    return {"ok": True, "vocabulary_pack": pack}
