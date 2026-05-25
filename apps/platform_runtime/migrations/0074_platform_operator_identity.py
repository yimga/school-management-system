# Platform operator identity 10x — profiles, invites, promotion requests

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def backfill_operator_profiles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    PlatformOperatorProfile = apps.get_model(
        "platform_runtime", "PlatformOperatorProfile"
    )
    for user in User.objects.filter(is_superuser=True):
        PlatformOperatorProfile.objects.get_or_create(
            user_id=user.pk,
            defaults={
                "status": "active",
                "tier": "break_glass",
                "mfa_required": True,
                "break_glass_only": False,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0073_sodp_provision_signup"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorProfile",
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
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("invited", "Invited"),
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("offboarded", "Offboarded"),
                        ],
                        db_index=True,
                        default="invited",
                        max_length=16,
                    ),
                ),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("observer", "Observer"),
                            ("support", "Support"),
                            ("fleet", "Fleet"),
                            ("billing", "Billing"),
                            ("security", "Security"),
                            ("principal", "Principal"),
                            ("break_glass", "Break Glass"),
                        ],
                        default="support",
                        max_length=32,
                    ),
                ),
                (
                    "extra_scopes",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Optional extra platform.* scope codes beyond tier defaults.",
                    ),
                ),
                ("mfa_required", models.BooleanField(default=True)),
                (
                    "break_glass_only",
                    models.BooleanField(
                        default=False,
                        help_text="When true, operator should use break-glass admin sparingly.",
                    ),
                ),
                ("invited_at", models.DateTimeField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("offboarded_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_operator_invites_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="platform_operator_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Platform operator profile",
                "verbose_name_plural": "Platform operator profiles",
                "db_table": "platform_runtime_operatorprofile",
            },
        ),
        migrations.CreateModel(
            name="PlatformOperatorInvite",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("email", models.EmailField(db_index=True, max_length=254)),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("observer", "Observer"),
                            ("support", "Support"),
                            ("fleet", "Fleet"),
                            ("billing", "Billing"),
                            ("security", "Security"),
                            ("principal", "Principal"),
                            ("break_glass", "Break Glass"),
                        ],
                        default="support",
                        max_length=32,
                    ),
                ),
                (
                    "token",
                    models.UUIDField(
                        db_index=True, default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_operator_invite_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "platform_runtime_operatorinvite",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PlatformOperatorPromotionRequest",
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
                (
                    "requested_tier",
                    models.CharField(
                        choices=[
                            ("observer", "Observer"),
                            ("support", "Support"),
                            ("fleet", "Fleet"),
                            ("billing", "Billing"),
                            ("security", "Security"),
                            ("principal", "Principal"),
                            ("break_glass", "Break Glass"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending peer approval"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                (
                    "peer_approver",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_promotions_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requester",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_promotions_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="platform_promotion_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "platform_runtime_operatorpromotionrequest",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(backfill_operator_profiles, migrations.RunPython.noop),
    ]
