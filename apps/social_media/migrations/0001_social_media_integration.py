# Generated manually for social media integration engine.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.accounts.legacy_hashes.encryption


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("schools", "0051_add_default_language"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialMediaIntegration",
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
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("x", "X (Twitter)"),
                            ("instagram", "Instagram"),
                            ("linkedin", "LinkedIn"),
                            ("facebook", "Facebook"),
                        ],
                        max_length=32,
                    ),
                ),
                ("handle", models.CharField(blank=True, default="", max_length=120)),
                (
                    "encrypted_oauth_token",
                    apps.accounts.legacy_hashes.encryption.EncryptedCharField(
                        blank=True,
                        default="",
                        help_text="Fernet-encrypted access token at rest.",
                        max_length=2048,
                    ),
                ),
                (
                    "refresh_token",
                    apps.accounts.legacy_hashes.encryption.EncryptedCharField(
                        blank=True, default="", max_length=2048
                    ),
                ),
                ("token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("feed_cache_json", models.JSONField(blank=True, default=list)),
                ("feed_cached_at", models.DateTimeField(blank=True, null=True)),
                (
                    "allowed_features",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Subscription-tier feature flags, e.g. publish, emergency, "
                            "analytics."
                        ),
                    ),
                ),
                (
                    "webhook_secret",
                    apps.accounts.legacy_hashes.encryption.EncryptedCharField(
                        blank=True, default="", max_length=512
                    ),
                ),
                ("audit_log", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("needs_reauth", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        help_text="Null for platform-wide corporate integrations.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_integrations",
                        to="schools.school",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SocialPostOutbox",
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
                ("body", models.TextField()),
                ("media_urls", models.JSONField(blank=True, default=list)),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        choices=[(10, "Standard"), (0, "Emergency")],
                        default=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("posted", "Posted"),
                            ("failed", "Failed"),
                            ("throttled", "Throttled"),
                        ],
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                (
                    "external_post_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_posts_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outbox_posts",
                        to="social_media.socialmediaintegration",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_post_outbox",
                        to="schools.school",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SocialModerationItem",
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
                ("caption", models.CharField(blank=True, default="", max_length=500)),
                ("image_url", models.URLField(max_length=2048)),
                ("hashtag", models.CharField(blank=True, default="", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_moments_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_moderation_items",
                        to="schools.school",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_moments_submitted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SocialCampaignAttribution",
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
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("x", "X (Twitter)"),
                            ("instagram", "Instagram"),
                            ("linkedin", "LinkedIn"),
                            ("facebook", "Facebook"),
                        ],
                        max_length=32,
                    ),
                ),
                ("utm_source", models.CharField(blank=True, default="", max_length=120)),
                ("utm_medium", models.CharField(blank=True, default="", max_length=120)),
                (
                    "utm_campaign",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                ("post_id", models.CharField(blank=True, default="", max_length=255)),
                (
                    "transaction_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("amount_cents", models.BigIntegerField(default=0)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_campaign_attributions",
                        to="schools.school",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="socialmediaintegration",
            index=models.Index(
                fields=["school", "provider"], name="social_medi_school__a0ea0d_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="socialmediaintegration",
            index=models.Index(
                fields=["school", "is_active"], name="social_medi_school__b8e2c1_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="socialmediaintegration",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("school__isnull", False)),
                fields=("school", "provider"),
                name="uniq_active_social_provider_per_school",
            ),
        ),
        migrations.AddConstraint(
            model_name="socialmediaintegration",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("school__isnull", True)),
                fields=("provider",),
                name="uniq_active_platform_social_provider",
            ),
        ),
        migrations.AddIndex(
            model_name="socialpostoutbox",
            index=models.Index(
                fields=["school", "status", "priority", "created_at"],
                name="social_post_school__4c8f21_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="socialmoderationitem",
            index=models.Index(
                fields=["school", "status", "created_at"],
                name="social_mode_school__9d12ab_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="socialcampaignattribution",
            index=models.Index(
                fields=["school", "provider", "recorded_at"],
                name="social_camp_school__e3a901_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="socialcampaignattribution",
            index=models.Index(
                fields=["school", "utm_campaign"],
                name="social_camp_school__f2b110_idx",
            ),
        ),
    ]
