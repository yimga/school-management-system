"""v4.00.39 — Per-tenant institution-type fields for Tier-C wedges 16/17/18.

Pure-additive AddField x 3 — closes the v4.00.38 "deferred" item where
Wedge 16 / 17 / 18 detail pages couldn't show a real per-school value.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0061_alter_school_governance_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="charter_authorizer_code",
            field=models.CharField(
                blank=True,
                default="",
                max_length=40,
                help_text=(
                    "Wedge 16 (Charter): the authorizer code from "
                    "apps.siteconfig._institution_types.CHARTER_AUTHORIZERS "
                    "(e.g. 'us-soe', 'uk-academy-trust')."
                ),
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="ib_programmes",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Wedge 17 (International): list of IB / Cambridge programme "
                    "codes this school is authorized for (e.g. ['pyp', 'myp', "
                    "'dp', 'cam-igcse'])."
                ),
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="faith_tradition_code",
            field=models.CharField(
                blank=True,
                default="",
                max_length=40,
                help_text=(
                    "Wedge 18 (Faith-based): the tradition code from "
                    "apps.siteconfig._institution_types.FAITH_TRADITIONS "
                    "(e.g. 'catholic', 'islamic-sunni', 'interfaith')."
                ),
            ),
        ),
    ]
