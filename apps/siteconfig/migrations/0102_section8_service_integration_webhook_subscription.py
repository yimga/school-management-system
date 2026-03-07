# Section 8: Industry Interoperability — ServiceIntegration, WebhookSubscription (zero-hardcoding gateway)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0101_nuance_engine_custom_pending_nuance"),
        ("schools", "0010_security_powerhouse_audit_passkey"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceIntegration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_name", models.CharField(help_text="e.g. Moodle, Stripe, Google Classroom", max_length=100)),
                ("service_type", models.CharField(
                    choices=[("LTI", "LTI 1.3"), ("OAUTH", "OAuth 2.0 / OpenID"), ("WEBHOOK", "Webhook outbound"), ("OTHER", "Other")],
                    default="OTHER",
                    max_length=20,
                )),
                ("client_id", models.CharField(blank=True, max_length=255)),
                ("client_secret", models.CharField(blank=True, help_text="Encrypt at rest in production; use for OAuth/LTI.", max_length=255)),
                ("endpoint_url", models.URLField(blank=True, help_text="Base URL for API or launch endpoint")),
                ("enabled_scopes", models.JSONField(blank=True, default=list, help_text="e.g. ['grades.read', 'roster.write']. Strict scoping per module.")),
                ("config", models.JSONField(blank=True, default=dict, help_text="LTI: deployment_id, public_key; OAuth: redirect_uri, etc.")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_integrations", to="schools.school")),
            ],
            options={
                "ordering": ["school", "service_name"],
                "verbose_name": "Service integration",
                "verbose_name_plural": "Service integrations",
                "unique_together": {("school", "service_name")},
            },
        ),
        migrations.CreateModel(
            name="WebhookSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(help_text="e.g. exam.completed, fee.paid", max_length=80)),
                ("target_url", models.URLField(help_text="Endpoint to POST the payload")),
                ("secret", models.CharField(blank=True, help_text="HMAC secret for signing payloads", max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webhook_subscriptions", to="schools.school")),
            ],
            options={
                "ordering": ["school", "event_type"],
                "verbose_name": "Webhook subscription",
                "verbose_name_plural": "Webhook subscriptions",
            },
        ),
    ]
