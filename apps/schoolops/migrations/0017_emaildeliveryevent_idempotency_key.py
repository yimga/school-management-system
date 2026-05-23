"""SODP — EmailDeliveryEvent idempotency_key for deduplicated sends."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0016_rename_schoolops_em_to_hash_idx_schoolops_e_to_hash_e50803_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="emaildeliveryevent",
            name="idempotency_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Optional caller-supplied dedupe key. When non-empty, a second "
                    "send with the same key returns the existing row id without SMTP."
                ),
                max_length=128,
            ),
        ),
        migrations.AddIndex(
            model_name="emaildeliveryevent",
            index=models.Index(
                condition=models.Q(("idempotency_key__gt", "")),
                fields=["idempotency_key"],
                name="schoolops_em_idem_nonempty",
            ),
        ),
        migrations.AddConstraint(
            model_name="emaildeliveryevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__gt", "")),
                fields=("idempotency_key",),
                name="schoolops_email_delivery_idem_unique",
            ),
        ),
    ]
