from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlsplit

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


LEGACY_NAMESPACE = "_rmc_admin_navigation_v1"


def _normalized_host(value: object) -> str:
    raw = str(value or "").strip().lower().rstrip(".")
    try:
        return (urlsplit(f"//{raw}").hostname or "unknown-host")[:255]
    except ValueError:
        return "unknown-host"


def _entry(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    path = str(raw.get("path") or "").strip()
    label = " ".join(str(raw.get("label") or "").split())[:100]
    if not path.startswith("/admin/") or not label:
        return None
    digest = sha256(path.encode("utf-8")).hexdigest()[:20]
    return {"id": f"legacy:{digest}", "path": path[:600], "label": label}


def copy_legacy_admin_navigation(apps, schema_editor):
    DashboardPreference = apps.get_model("siteconfig", "DashboardUserPreference")
    AdminPreference = apps.get_model("siteconfig", "AdminNavigationPreference")
    rows = []
    for preference in DashboardPreference.objects.all().iterator():
        layout = preference.dashboard_layout
        namespace = layout.get(LEGACY_NAMESPACE, {}) if isinstance(layout, dict) else {}
        if not isinstance(namespace, dict):
            continue
        for raw_scope, raw_state in namespace.items():
            if not isinstance(raw_scope, str) or "|" not in raw_scope or not isinstance(raw_state, dict):
                continue
            host, admin_site = raw_scope.rsplit("|", 1)
            pinned = [item for item in (_entry(value) for value in raw_state.get("pinned", [])) if item]
            recent = [item for item in (_entry(value) for value in raw_state.get("recent", [])) if item]
            state = {
                "pinned": pinned[:8],
                "recent": recent[:10],
                "mode": "compact" if raw_state.get("compact") else "expanded",
                "focus": False,
                "expansions": {
                    "advanced": bool(raw_state.get("advancedOpen")),
                    "models": bool(raw_state.get("appsOpen")),
                },
                "dismissedRecommendations": [],
            }
            rows.append(
                AdminPreference(
                    user_id=preference.user_id,
                    host=_normalized_host(host),
                    admin_site=str(admin_site).strip().lower()[:64],
                    schema_version=3,
                    revision=1,
                    state=state,
                    applied_mutation_ids=[],
                )
            )
    if rows:
        AdminPreference.objects.bulk_create(rows, ignore_conflicts=True, batch_size=250)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("siteconfig", "0211_plan_default_must_be_active"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminNavigationPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("host", models.CharField(max_length=255)),
                ("admin_site", models.CharField(max_length=64)),
                ("schema_version", models.PositiveSmallIntegerField(default=3)),
                ("revision", models.PositiveBigIntegerField(default=0)),
                ("state", models.JSONField(blank=True, default=dict)),
                ("applied_mutation_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="admin_navigation_preferences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Admin navigation preference",
                "verbose_name_plural": "Admin navigation preferences",
                "indexes": [
                    models.Index(fields=["host", "admin_site"], name="siteconfig_admin_nav_scope_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "host", "admin_site"),
                        name="uniq_admin_nav_user_host_site",
                    )
                ],
            },
        ),
        migrations.RunPython(copy_legacy_admin_navigation, migrations.RunPython.noop),
    ]
