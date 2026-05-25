# Generated manually for tenant identity hub (TenantStaffInvite)

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0036_user_security_posture_fields_alter"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantStaffInvite",
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
                ("email", models.EmailField(max_length=254)),
                ("role", models.CharField(default="TEACHER", max_length=32)),
                (
                    "token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
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
                        related_name="tenant_staff_invites_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_invites",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant staff invite",
                "verbose_name_plural": "Tenant staff invites",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "email"],
                        name="accounts_te_school__a1b2c3_idx",
                    ),
                    models.Index(
                        fields=["token"],
                        name="accounts_te_token_4d5e6f_idx",
                    ),
                ],
            },
        ),
    ]
