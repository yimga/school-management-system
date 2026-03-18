# Migration: APIAuditLog points to Integration; APIService removed (unified module)

import django.db.models.deletion
from django.db import migrations, models


def _category_to_provider(category):
    return {
        "PAYMENT": "payments",
        "LMS": "other",
        "ATTENDANCE": "other",
        "LIBRARY": "other",
        "AI": "other",
        "SIS": "other",
        "OTHER": "other",
    }.get(category, "other")


def migrate_audit_to_integration(apps, schema_editor):
    APIAuditLog = apps.get_model("apicenter", "APIAuditLog")
    _APIService = apps.get_model("apicenter", "APIService")
    Integration = apps.get_model("siteconfig", "Integration")
    for log in APIAuditLog.objects.select_related("api_service").all():
        api = log.api_service
        if api.integration_id:
            log.integration_id = api.integration_id
            log.save(update_fields=["integration_id"])
        else:
            # Standalone APIService: create Integration and point log to it
            slug = api.slug
            if Integration.objects.filter(slug=slug).exists():
                slug = f"{api.slug}-legacy-{api.pk}"
            integ = Integration.objects.create(
                name=api.service_name,
                slug=slug,
                provider=_category_to_provider(api.category),
                category=api.category,
                enabled=api.is_active,
                rate_limit_per_min=api.rate_limit_per_min or None,
                ip_whitelist=api.ip_whitelist or [],
                allowed_scopes=api.allowed_scopes or {},
                secret_key_hash=api.secret_key_hash or "",
                last_call_at=api.last_call_at,
                health_status=api.health_status or "healthy",
                pii_masking=api.pii_masking,
                school_id=api.school_id,
            )
            log.integration_id = integ.pk
            log.save(update_fields=["integration_id"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("apicenter", "0002_add_integration_fk"),
        ("siteconfig", "0084_integration_unified_governance_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="apiauditlog",
            name="integration",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="audit_logs",
                to="siteconfig.integration",
            ),
        ),
        migrations.RunPython(migrate_audit_to_integration, noop),
        migrations.RemoveField(model_name="apiauditlog", name="api_service"),
        migrations.AlterField(
            model_name="apiauditlog",
            name="integration",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="audit_logs",
                to="siteconfig.integration",
            ),
        ),
        migrations.DeleteModel(name="APIService"),
    ]
