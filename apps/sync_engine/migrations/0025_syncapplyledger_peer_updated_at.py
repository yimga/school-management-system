# The causality half of SyncApplyLedger: the PEER's updated_at on the version this side
# actually applied. `edge_outbox` ships it as a delta row's `base_updated_at`, which is
# what lets `sync_services._conflict_decision` grade a row CAUSALLY instead of racing the
# cloud's clock against an appliance's - see the model docstring for why this cannot be
# derived from `applied_updated_at`.
#
# ADD-COLUMN ONLY, on a table that already exists. No new table, therefore no new RLS
# work: `sync_engine_syncapplyledger` is already enumerated in 0008_enable_rls_postgresql
# and 0009_rls_policy_default_deny, and both `scan_rls_table_coverage.py` and
# `scan_rls_force_coverage.py` ask about TABLES, not columns. Verified by running the
# table-coverage scanner before and after this migration: 0 uncovered, unchanged.
#
# NULLABLE, and null on every existing row, which IS the mixed-fleet contract rather than
# an omission. A row with no peer stamp emits no `base_updated_at`, the receiver parses
# None, and every wall-clock rule decides exactly as it does today. There is deliberately
# no backfill: the only value that could be invented here is `applied_updated_at`, which
# is THIS side's stamp - handing it to the far side as a base version would assert descent
# from an edit we may never have seen, which is the precise failure this column exists to
# prevent. The column fills itself on the next sync apply of each row.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync_engine', '0024_syncdeadletter_rls'),
    ]

    operations = [
        migrations.AddField(
            model_name='syncapplyledger',
            name='peer_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
