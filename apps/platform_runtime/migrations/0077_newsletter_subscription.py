"""NewsletterSubscription model for the public marketing list (v4.00.98 Phase 3)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0076_workflow_run_and_step"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsletterSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, max_length=254, unique=True)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending verification"),
                        ("confirmed", "Confirmed"),
                        ("unsubscribed", "Unsubscribed"),
                        ("bounced", "Bounced"),
                    ],
                    db_index=True, default="pending", max_length=16,
                )),
                ("source", models.CharField(blank=True, default="", max_length=64)),
                ("ip_hash", models.CharField(blank=True, default="", max_length=32)),
                ("utm_source", models.CharField(blank=True, default="", max_length=64)),
                ("utm_medium", models.CharField(blank=True, default="", max_length=64)),
                ("utm_campaign", models.CharField(blank=True, default="", max_length=128)),
                ("confirmation_token", models.CharField(blank=True, default="", max_length=256)),
                ("unsubscribe_token", models.CharField(blank=True, default="", max_length=256)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("confirmed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("unsubscribed_at", models.DateTimeField(blank=True, null=True)),
                ("last_send_at", models.DateTimeField(blank=True, null=True)),
                ("send_count", models.PositiveIntegerField(default=0)),
                ("bounce_count", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Newsletter subscription",
                "verbose_name_plural": "Newsletter subscriptions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="newslettersubscription",
            index=models.Index(fields=["status", "-created_at"], name="newslettersub_status_idx"),
        ),
        migrations.AddIndex(
            model_name="newslettersubscription",
            index=models.Index(fields=["source", "-created_at"], name="newslettersub_source_idx"),
        ),
        migrations.AddIndex(
            model_name="newslettersubscription",
            index=models.Index(fields=["confirmed_at"], name="newslettersub_confirmed_idx"),
        ),
    ]
