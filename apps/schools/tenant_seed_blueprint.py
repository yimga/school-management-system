"""Idempotent tenant seed blueprint for E2E proof school (demo-school / New Test High School)."""

from __future__ import annotations

from typing import Any


from apps.schools.demo_user_seeding import seed_demo_users_for_school
from apps.schools.models import School


DEFAULT_DISPLAY_NAME = "New Test High School"
DEFAULT_SLUG = "demo-school"


def apply_tenant_seed_blueprint(
    *,
    school_slug: str = DEFAULT_SLUG,
    display_name: str = DEFAULT_DISPLAY_NAME,
    password: str = "Test1234",
    username_prefix: str = "demo",
    stdout: Any = None,
    style: Any = None,
) -> School | None:
    """
    Apply the canonical demo tenant blueprint: school identity, portal toggles,
    demo personas, and manifest snapshot on school.settings.
    """
    school = School.objects.filter(slug=school_slug, is_active=True).first()
    if school is None:
        return None

    dirty_fields: list[str] = []
    if display_name and school.name != display_name:
        school.name = display_name
        dirty_fields.append("name")
    if dirty_fields:
        school.save(update_fields=dirty_fields)

    class _Out:
        def write(self, msg: str) -> None:
            if stdout is not None:
                stdout.write(msg)

    class _Style:
        SUCCESS = staticmethod(lambda x: x)
        WARNING = staticmethod(lambda x: x)

    seed_demo_users_for_school(
        school,
        password=password,
        username_prefix=username_prefix,
        stdout=_Out(),
        style=_Style(),
    )

    school.refresh_from_db()
    from django.utils import timezone

    from apps.sync_engine.tenant_manifest_resolver import school_offline_manifest_dict

    settings = dict(getattr(school, "settings", None) or {})
    settings["tenant_manifest_snapshot"] = school_offline_manifest_dict(school)
    settings["seed_blueprint_applied_at"] = timezone.now().isoformat()
    school.settings = settings
    school.save(update_fields=["settings"])
    school.refresh_from_db()

    return school


def blueprint_status(school: School | None) -> dict[str, Any]:
    if school is None:
        return {"ok": False, "reason": "school_missing"}
    settings = getattr(school, "settings", None) or {}
    manifest = settings.get("tenant_manifest_snapshot") if isinstance(settings, dict) else None
    return {
        "ok": bool(manifest),
        "slug": school.slug,
        "name": school.name,
        "has_manifest_snapshot": bool(manifest),
        "seed_blueprint_applied_at": (
            settings.get("seed_blueprint_applied_at") if isinstance(settings, dict) else None
        ),
    }
