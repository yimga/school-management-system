# Generated manually for Web Push subscriptions (2026-06-08).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("communication", "0022_consentevent_messagedeliveryreceipt"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebPushSubscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="web_push_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Web push subscription",
                "verbose_name_plural": "Web push subscriptions",
                "ordering": ["-updated_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "is_active"],
                        name="communicati_user_id_6f0d8d_idx",
                    )
                ],
            },
        ),
    ]
