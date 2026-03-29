# Global support ticket threading, CSAT, and reply model.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("siteconfig", "0164_globalsupportticket_internal_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalsupportticket",
            name="csat_score",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="1–5 satisfaction after resolution (tenant-submitted).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="globalsupportticket",
            name="csat_comment",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="globalsupportticket",
            name="csat_submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="GlobalSupportTicketReply",
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
                (
                    "visibility",
                    models.CharField(
                        choices=[
                            ("INTERNAL", "Operators only"),
                            ("SUBMITTER_VISIBLE", "Visible to submitter"),
                        ],
                        default="INTERNAL",
                        max_length=24,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="global_support_ticket_replies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="thread_replies",
                        to="siteconfig.globalsupportticket",
                    ),
                ),
            ],
            options={
                "verbose_name": "Global support ticket reply",
                "verbose_name_plural": "Global support ticket replies",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="globalsupportticketreply",
            index=models.Index(
                fields=["ticket", "created_at"],
                name="siteconfig_gstreply_tc",
            ),
        ),
    ]
