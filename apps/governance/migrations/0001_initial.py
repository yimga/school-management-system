# Generated manually for global governance Phase 2A (batch 1562).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("schools", "0059_v4_00_12_rls_audit_pass"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
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
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                (
                    "legal_owner_type",
                    models.CharField(
                        choices=[
                            ("proprietor", "Proprietor / sole owner"),
                            ("corporation", "Corporation / company"),
                            ("diocese", "Diocese / faith network"),
                            ("ministry", "Ministry / government body"),
                            ("ngo", "NGO / nonprofit cluster"),
                            ("franchise", "Franchise / licensed network"),
                        ],
                        default="proprietor",
                        max_length=32,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Organization",
                "verbose_name_plural": "Organizations",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="GovernanceNode",
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
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="governance_nodes",
                        to="governance.organization",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="governance.governancenode",
                    ),
                ),
            ],
            options={
                "verbose_name": "Governance node",
                "verbose_name_plural": "Governance nodes",
                "ordering": ("organization__name", "name"),
                "unique_together": {("organization", "slug")},
            },
        ),
        migrations.CreateModel(
            name="OrgMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("group_admin", "Group administrator"),
                            ("inspector", "Inspector / auditor"),
                            ("superintendent", "Superintendent"),
                        ],
                        default="group_admin",
                        max_length=32,
                    ),
                ),
                ("is_primary", models.BooleanField(default=False, help_text="Preferred org context when the user belongs to multiple organizations.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="governance.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="org_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Organization membership",
                "verbose_name_plural": "Organization memberships",
                "ordering": ("-is_primary", "organization__name"),
                "unique_together": {("user", "organization")},
            },
        ),
    ]
