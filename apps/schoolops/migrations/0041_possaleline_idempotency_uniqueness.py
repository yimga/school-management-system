"""Make the POS idempotency key mean something at the DB level.

``pos_checkout.checkout()`` deduped by READING for a prior line with the same
key. A read cannot see a sibling transaction that has not committed, so two
workers replaying one flaky-wifi scan both passed the check and both debited
the wallet. Only a unique index can stop that.

The index is per LINE, not per key: one sale writes several ``PosSaleLine`` rows
under a single key, so ``idempotency_seq`` (0-based position within the sale)
joins the key in the constraint.

Existing rows are backfilled by insertion order within each
(school, idempotency_key) group, which reconstructs the per-line sequence for
real multi-line sales AND leaves already-duplicated rows with distinct seq
values — so the AddConstraint below cannot fail on live data, and no money row
is deleted or rewritten to make the migration go through.
"""

from django.db import migrations, models


def _backfill_seq(apps, schema_editor):
    PosSaleLine = apps.get_model("schoolops", "PosSaleLine")
    rows = (
        PosSaleLine.objects.exclude(idempotency_key="")
        .order_by("school_id", "idempotency_key", "id")
        .values_list("id", "school_id", "idempotency_key")
    )
    seq_by_group: dict = {}
    updates = []
    for row_id, school_id, key in rows:
        group = (school_id, key)
        seq = seq_by_group.get(group, 0)
        seq_by_group[group] = seq + 1
        updates.append(PosSaleLine(id=row_id, idempotency_seq=seq))
    if updates:
        PosSaleLine.objects.bulk_update(updates, ["idempotency_seq"], batch_size=500)


def _noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0040_procurement_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="possaleline",
            name="idempotency_seq",
            field=models.PositiveSmallIntegerField(
                default=0,
                db_default=0,
                help_text=(
                    "0-based position of this line within its idempotency_key "
                    "sale. One sale writes several lines under ONE key, so the "
                    "uniqueness that makes the key real has to be per line, not "
                    "per key."
                ),
            ),
        ),
        migrations.RunPython(_backfill_seq, _noop),
        migrations.AddConstraint(
            model_name="possaleline",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key", ""), _negated=True),
                fields=("school", "idempotency_key", "idempotency_seq"),
                name="uniq_possaleline_school_idem",
            ),
        ),
    ]
