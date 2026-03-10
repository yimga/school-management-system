from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_alter_securityauditlog_event_type"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="RolloverProposal"),
                migrations.DeleteModel(name="RolloverProposalItem"),
            ],
            database_operations=[],
        ),
    ]
