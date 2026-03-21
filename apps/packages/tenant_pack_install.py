"""
N20: Record DocumentPack / ExperiencePack usage as InstalledPackage rows for tenant rollback parity.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import DatabaseError, IntegrityError

from apps.brand_experience.experience_packs import get_experience_pack_code_for_school

logger = logging.getLogger(__name__)


DOC_PACK_PREFIX = "doc-pack"
EXP_PACK_PREFIX = "exp-pack"


def _package_id_doc_pack(code: str) -> str:
    return f"{DOC_PACK_PREFIX}:{(code or '').strip()}"


def _package_id_exp_pack(code: str) -> str:
    return f"{EXP_PACK_PREFIX}:{(code or '').strip()}"


def record_document_pack_usage(
    school,
    pack,
    *,
    actor_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    When a tenant uses a DocumentPack on a document, ensure an InstalledPackage row exists
    (idempotent per school + pack code + version).
    """
    from apps.packages.engine import PackageEngine
    from apps.packages.models import DocumentPack, InstalledPackage

    if school is None or pack is None:
        return {"ok": True, "skipped": True, "reason": "no school or pack"}
    if not isinstance(pack, DocumentPack):
        return {"ok": True, "skipped": True, "reason": "invalid pack type"}

    package_id = _package_id_doc_pack(pack.code)
    version = str(getattr(pack, "version", None) or "1.0.0").strip() or "1.0.0"
    if InstalledPackage.objects.filter(
        school_id=school.pk,
        package_id=package_id,
        version=version,
        is_active=True,
    ).exists():
        return {"ok": True, "skipped": True, "reason": "already active"}

    payload_sections = {
        "document_pack": {
            "code": pack.code,
            "name": pack.name,
            "lifecycle_states": list(pack.lifecycle_states or []),
        }
    }
    try:
        result = PackageEngine.apply_package(
            tenant_id=school.pk,
            package_id=package_id,
            version=version,
            payload_sections=payload_sections,
            mode="production",
            actor_id=actor_id,
        )
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        logger.warning(
            "record_document_pack_usage failed school=%s package_id=%s: %s",
            getattr(school, "pk", None),
            package_id,
            exc,
            exc_info=True,
        )
        return {"ok": False, "errors": [str(exc)], "package_id": package_id}
    if not result.get("ok"):
        logger.warning(
            "record_document_pack_usage apply rejected school=%s package_id=%s errors=%s",
            getattr(school, "pk", None),
            package_id,
            result.get("errors"),
        )
    return result


def sync_experience_pack_install_from_school(
    school,
    *,
    actor_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    When school settings reference an experience pack code, mirror to InstalledPackage for rollback UI.
    """
    from apps.packages.engine import PackageEngine
    from apps.packages.models import ExperiencePack, InstalledPackage

    if school is None:
        return {"ok": True, "skipped": True, "reason": "no school"}
    code = (get_experience_pack_code_for_school(school) or "").strip()
    if not code:
        return {"ok": True, "skipped": True, "reason": "no experience pack code"}

    pack = ExperiencePack.objects.filter(code=code, is_active=True).first()
    if not pack:
        return {"ok": True, "skipped": True, "reason": "pack not found"}

    package_id = _package_id_exp_pack(pack.code)
    version = str(getattr(pack, "version", None) or "1.0.0").strip() or "1.0.0"
    if InstalledPackage.objects.filter(
        school_id=school.pk,
        package_id=package_id,
        version=version,
        is_active=True,
    ).exists():
        return {"ok": True, "skipped": True, "reason": "already active"}

    payload_sections = {
        "experience_pack": {
            "code": pack.code,
            "name": pack.name,
            "theme_pack_id": pack.theme_pack_id,
        }
    }
    try:
        result = PackageEngine.apply_package(
            tenant_id=school.pk,
            package_id=package_id,
            version=version,
            payload_sections=payload_sections,
            mode="production",
            actor_id=actor_id,
        )
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        logger.warning(
            "sync_experience_pack_install_from_school failed school=%s package_id=%s: %s",
            getattr(school, "pk", None),
            package_id,
            exc,
            exc_info=True,
        )
        return {"ok": False, "errors": [str(exc)], "package_id": package_id}
    if not result.get("ok"):
        logger.warning(
            "sync_experience_pack_install_from_school apply rejected school=%s package_id=%s errors=%s",
            getattr(school, "pk", None),
            package_id,
            result.get("errors"),
        )
    return result
