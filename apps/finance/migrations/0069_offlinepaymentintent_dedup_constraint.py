"""Atomic offline payment-intent idempotency.

OfflinePaymentIntent shipped without the partial-unique constraint every sibling
offline-capture model has, so concurrent offline replays of one captured payment
could double-insert. This collapses any existing duplicates (non-destructively,
via the idempotent heal) and adds the partial-unique index.

The DDL is performed by the idempotent ``schema_repair`` heal (CREATE UNIQUE
INDEX IF NOT EXISTS, after a conservative dedupe) so a tenant schema that
fake-applies or misses this migration still converges on the next deploy. The
matching ``UniqueConstraint`` is registered in Django's model STATE only
(SeparateDatabaseAndState) so the schema editor doesn't try to create the index a
second time and ``makemigrations --check`` stays clean.
"""

from django.db import migrations, models


def _heal_index(apps, schema_editor):
    from apps.finance.schema_repair import ensure_offlinepaymentintent_client_id_index

    ensure_offlinepaymentintent_client_id_index()


def _drop_index(apps, schema_editor):
    table = "finance_offlinepaymentintent"
    index = "uniq_offlinepaymentintent_invoice_client_id"
    q_index = schema_editor.connection.ops.quote_name(index)
    with schema_editor.connection.cursor() as cursor:
        # rls-bypass-allow: migration-reverse-drops-the-partial-unique-index
        cursor.execute(f"DROP INDEX IF EXISTS {q_index};")


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0068_ensure_offline_capture_tables"),
    ]

    operations = [
        migrations.RunPython(_heal_index, _drop_index),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name="offlinepaymentintent",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("client_offline_id", ""), _negated=True),
                        fields=["invoice", "client_offline_id"],
                        name="uniq_offlinepaymentintent_invoice_client_id",
                    ),
                ),
            ],
        ),
    ]
