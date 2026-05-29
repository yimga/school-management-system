"""v4.00.42 — Support 10X follow-on schema.

Additive:
  - GlobalSupportTicket.linked_to (self FK, nullable) — parent incident.
  - GlobalSupportTicket.merged_into (self FK, nullable) — canonical duplicate target.
  - GlobalSupportTicketAttachment (new) — files attached by submitter or operator.
"""

from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _support_attachment_upload_to(instance, filename: str) -> str:
    return f"support_tickets/{instance.ticket_id}/{filename}"


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0187_countrymultiplier_tax_rate_tax_code"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="globalsupportticket",
            name="linked_to",
            field=models.ForeignKey(
                blank=True,
                help_text="Parent incident this ticket belongs to.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_children",
                to="siteconfig.globalsupportticket",
            ),
        ),
        migrations.AddField(
            model_name="globalsupportticket",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical ticket this one was merged into as a duplicate.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="merged_duplicates",
                to="siteconfig.globalsupportticket",
            ),
        ),
        migrations.CreateModel(
            name="GlobalSupportTicketAttachment",
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
                    "file",
                    models.FileField(
                        max_length=400,
                        upload_to=_support_attachment_upload_to,
                    ),
                ),
                ("filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, default="", max_length=120)),
                ("byte_size", models.PositiveIntegerField(default=0)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("QUICK_CREATE", "Quick-create chip"),
                            ("FOLLOW_UP", "Tenant follow-up"),
                            ("OPERATOR", "Operator upload"),
                        ],
                        default="QUICK_CREATE",
                        max_length=24,
                    ),
                ),
                ("visible_to_submitter", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="siteconfig.globalsupportticket",
                    ),
                ),
                (
                    "uploader",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="support_ticket_attachments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Global support ticket attachment",
                "verbose_name_plural": "Global support ticket attachments",
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["ticket", "created_at"],
                        name="siteconfig__ticket__24a1e7_idx",
                    ),
                ],
            },
        ),
    ]
