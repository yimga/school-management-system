from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db.models import Q

from apps.packages.engine import rollback as rollback_package
from apps.packages.models import ExperiencePack, InstalledPackage

from .models import ThemePack


def _school_settings_payload(school: Any) -> dict[str, Any]:
    payload = getattr(school, "settings", None) or {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def get_experience_pack_code_for_school(school: Any, *, role: str | None = None) -> str:
    if school is None:
        return ""
    settings_payload = _school_settings_payload(school)
    role_key = str(role or "").strip().upper()
    if role_key:
        per_role = settings_payload.get("experience_pack_by_role") or {}
        if isinstance(per_role, Mapping):
            candidate = str(per_role.get(role_key) or "").strip()
            if candidate:
                return candidate
    direct_code = str(settings_payload.get("experience_pack_code") or "").strip()
    if direct_code:
        return direct_code
    install = (
        InstalledPackage.objects.filter(
            school=school,
            package_type="theme",
            is_active=True,
        )
        .order_by("-applied_at", "-pk")
        .first()
    )
    if install:
        return str(install.package_id or "").strip()
    return ""


def get_effective_experience_pack(
    school: Any = None, *, role: str | None = None
) -> ExperiencePack | None:
    code = get_experience_pack_code_for_school(school, role=role)
    if not code:
        return None
    return ExperiencePack.objects.filter(code=code, is_active=True).first()


def resolve_experience_theme_pack(
    school: Any = None, *, role: str | None = None
) -> ThemePack | None:
    pack = get_effective_experience_pack(school, role=role)
    theme_pack_id = getattr(pack, "theme_pack_id", None)
    if not theme_pack_id:
        return None
    return ThemePack.objects.filter(pk=theme_pack_id, is_active=True).first()


def compare_experience_packs(
    base_pack: ExperiencePack | str | None,
    compare_pack: ExperiencePack | str | None,
) -> dict[str, Any]:
    def _resolve(value: ExperiencePack | str | None) -> ExperiencePack | None:
        if value is None:
            return None
        if isinstance(value, ExperiencePack):
            return value
        code = str(value).strip()
        if not code:
            return None
        return ExperiencePack.objects.filter(code=code).first()

    base = _resolve(base_pack)
    compare = _resolve(compare_pack)
    if base is None or compare is None:
        return {
            "base_code": getattr(base, "code", ""),
            "compare_code": getattr(compare, "code", ""),
            "changes": {},
            "changed_sections": [],
        }

    changes = {}
    for key in ("theme_pack_id", "layout_schema", "communication_style", "is_active"):
        base_value = getattr(base, key, None)
        compare_value = getattr(compare, key, None)
        if base_value != compare_value:
            changes[key] = {"base": base_value, "compare": compare_value}
    return {
        "base_code": base.code,
        "compare_code": compare.code,
        "changes": changes,
        "changed_sections": sorted(changes.keys()),
    }


def rollback_experience_pack(
    school: Any, *, actor_id: int | None = None
) -> dict[str, Any]:
    code = get_experience_pack_code_for_school(school)
    if not school or not code:
        return {
            "ok": False,
            "message": "No active experience pack configured.",
            "rolled_back": False,
        }
    exp_pid = f"exp-pack:{code}"
    install = (
        InstalledPackage.objects.filter(
            school=school,
            is_active=True,
        )
        .filter(
            Q(package_id=exp_pid, package_type="experience_pack")
            | Q(package_id=code, package_type="theme")
        )
        .order_by("-applied_at", "-pk")
        .first()
    )
    if install is None:
        return {
            "ok": False,
            "message": "No active installed package found for the configured experience pack.",
            "rolled_back": False,
        }
    result = rollback_package(install, actor_id=actor_id)
    result["rolled_back"] = bool(result.get("ok"))
    return result
