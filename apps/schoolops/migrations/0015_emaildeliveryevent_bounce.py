"""v3.58.x Wave 9 Agent M — Add bounce tracking to EmailDeliveryEvent.

Pure additive AddField — no model imports (scan_migration_model_imports
zero-tolerance gate). Two new fields:

* ``bounced`` (BooleanField, default=False) — set when an SMTP 5xx /
  SenderRefused / RecipientsRefused happens at send time OR when a
  provider webhook (Postmark/SendGrid/SES/Mailgun) reports the message
  bounced after-the-fact.
* ``bounce_kind`` (CharField max_length=32, blank, default="") — coarse
  taxonomy label. ``hard_5xx`` / ``soft_4xx`` / ``senderrefused`` /
  ``recipientsrefused`` / ``unknown`` for send-time classification;
  ``provider_<type>`` for webhook-reported bounces.

Append-only contract preserved — neither field weakens the existing
``save()`` / ``delete()`` guards on EmailDeliveryEvent. The webhook
view writes via raw UPDATE on the bounce columns ONLY (does NOT call
``.save()``), so the read-only guard still applies to row-as-a-whole.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0014_email_delivery_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="emaildeliveryevent",
            name="bounced",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True when the send-time SMTP layer raised an "
                    "SMTPSenderRefused / SMTPRecipientsRefused / 5xx, OR "
                    "when a provider webhook (Postmark/SendGrid/SES/Mailgun) "
                    "later told us the message bounced. Separate from "
                    "``ok=False`` because a transient retry-eligible failure "
                    "is not a bounce."
                ),
            ),
        ),
        migrations.AddField(
            model_name="emaildeliveryevent",
            name="bounce_kind",
            field=models.CharField(
                blank=True,
                default="",
                max_length=32,
                help_text=(
                    "Bounce taxonomy — 'hard_5xx' | 'soft_4xx' | "
                    "'senderrefused' | 'recipientsrefused' | 'unknown' | "
                    "'provider_<type>' where <type> is the raw vendor-"
                    "reported bounce label."
                ),
            ),
        ),
    ]
