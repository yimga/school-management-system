# Plan VIII: Blockchain credentials scaffold — optional on-chain status on ReportDocumentHash

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0010_reportdocumenthash"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportdocumenthash",
            name="on_chain_status",
            field=models.CharField(
                blank=True,
                max_length=32,
                null=True,
                help_text="e.g. anchored, pending, revoked; set when credential is verified on-chain",
            ),
        ),
        migrations.AddField(
            model_name="reportdocumenthash",
            name="blockchain_tx_id",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                help_text="Transaction ID or proof identifier from blockchain gateway",
            ),
        ),
    ]
