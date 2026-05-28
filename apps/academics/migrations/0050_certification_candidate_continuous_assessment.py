"""v4.00.13 — Add CertificationCandidate.continuous_assessment JSONField.

Backs the new CA-mark input UI at
``apps/academics/views_ca_marks.py::CAMarksInputView`` and the export
command ``export_certification_pack`` which already reads the field
defensively (returns blank when absent).

Default ``dict`` so existing rows materialize as ``{}`` without backfill.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0049_alter_certificationfeetemplate_currency_and_more"),
    ]
    operations = [
        migrations.AddField(
            model_name="certificationcandidate",
            name="continuous_assessment",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
