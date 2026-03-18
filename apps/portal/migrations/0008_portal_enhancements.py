# Generated migration to add portal enhancement models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0007_alter_kbarticleattachment_file"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuardianLinkInvitation",
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
                ("student_id", models.IntegerField()),
                ("parent_email", models.EmailField(max_length=254)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("token", models.CharField(max_length=100, unique=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.IntegerField()),
            ],
            options={
                "ordering": ["-sent_at"],
                "indexes": [
                    models.Index(
                        fields=["token"], name="portal_guardianlinkinvitation_token_idx"
                    ),
                    models.Index(
                        fields=["parent_email"],
                        name="portal_guardianlinkinvitation_parent_email_idx",
                    ),
                    models.Index(
                        fields=["student_id"],
                        name="portal_guardianlinkinvitation_student_id_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ParentStudentLink",
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
                ("parent_id", models.IntegerField()),
                ("student_id", models.IntegerField()),
                ("relationship", models.CharField(default="parent", max_length=20)),
                ("is_primary", models.BooleanField(default=False)),
                ("access_level", models.CharField(default="limited", max_length=20)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("linked_by", models.IntegerField()),
            ],
            options={
                "unique_together": {("parent_id", "student_id")},
                "ordering": ["-linked_at"],
                "indexes": [
                    models.Index(
                        fields=["parent_id", "student_id"],
                        name="portal_parentstudentlink_parent_student_idx",
                    ),
                    models.Index(
                        fields=["parent_id"],
                        name="portal_parentstudentlink_parent_id_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PortalNotification",
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
                ("parent_id", models.IntegerField()),
                ("student_id", models.IntegerField()),
                ("notification_type", models.CharField(max_length=20)),
                ("title", models.CharField(max_length=200)),
                ("message", models.TextField()),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("related_id", models.IntegerField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["parent_id", "is_read"],
                        name="portal_portalnotification_parent_read_idx",
                    ),
                    models.Index(
                        fields=["student_id"],
                        name="portal_portalnotification_student_id_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PortalPreferences",
            fields=[
                (
                    "parent_id",
                    models.OneToOneField(
                        on_delete=models.CASCADE,
                        related_name="portal_prefs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("notification_email", models.BooleanField(default=True)),
                ("notification_sms", models.BooleanField(default=False)),
                ("language", models.CharField(default="en", max_length=10)),
                ("theme", models.CharField(default="light", max_length=20)),
                ("show_grades", models.BooleanField(default=True)),
                ("show_attendance", models.BooleanField(default=True)),
                ("show_fees", models.BooleanField(default=True)),
                ("show_announcements", models.BooleanField(default=True)),
                ("dashboard_widgets", models.JSONField(default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ParentMessage",
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
                ("sender_id", models.IntegerField()),
                ("recipient_id", models.IntegerField()),
                ("subject", models.CharField(max_length=200)),
                ("message", models.TextField()),
                ("status", models.CharField(default="sent", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reply_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        to="portal.parentmessage",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["recipient_id", "status"],
                        name="portal_parentmessage_recipient_status_idx",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PortalFeatureAccess",
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
                ("parent_id", models.IntegerField()),
                ("feature", models.CharField(max_length=50)),
                ("is_enabled", models.BooleanField(default=True)),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "unique_together": {("parent_id", "feature")},
                "ordering": ["feature"],
            },
        ),
        migrations.CreateModel(
            name="PortalSession",
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
                ("parent_id", models.IntegerField()),
                ("session_token", models.CharField(max_length=255, unique=True)),
                ("ip_address", models.GenericIPAddressField()),
                ("user_agent", models.TextField()),
                ("login_at", models.DateTimeField(auto_now_add=True)),
                ("logout_at", models.DateTimeField(blank=True, null=True)),
                ("last_activity", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("device_type", models.CharField(default="unknown", max_length=50)),
            ],
            options={
                "ordering": ["-login_at"],
                "indexes": [
                    models.Index(
                        fields=["parent_id", "is_active"],
                        name="portal_portalsession_parent_active_idx",
                    ),
                    models.Index(
                        fields=["session_token"],
                        name="portal_portalsession_session_token_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PortalAuditLog",
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
                ("parent_id", models.IntegerField()),
                ("action", models.CharField(max_length=50)),
                ("description", models.TextField()),
                ("ip_address", models.GenericIPAddressField()),
                ("user_agent", models.TextField()),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("details", models.JSONField(default=dict)),
            ],
            options={
                "ordering": ["-timestamp"],
                "indexes": [
                    models.Index(
                        fields=["parent_id", "action"],
                        name="portal_portalauditlog_parent_action_idx",
                    ),
                    models.Index(
                        fields=["timestamp"], name="portal_portalauditlog_timestamp_idx"
                    ),
                ],
            },
        ),
    ]
