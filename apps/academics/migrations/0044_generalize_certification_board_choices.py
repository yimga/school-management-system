"""Expand certification Board choices beyond Cameroon GCE/OBC so a school in any country
can register candidates. Change the default board from GCE_BOARD to OTHER so a new tenant
does not inherit Cameroon-specific assumptions. Update help texts on legacy `_fcfa` columns
to clarify the value is in the tenant's fee-template currency, not necessarily FCFA.

This migration only adjusts choices/defaults/help_text — no data migration is required.
Existing rows keep their stored board values; the new choices simply expand the option list.
"""

from django.db import migrations, models


SHARED_BOARD_CHOICES = [
    ("GCE_BOARD", "GCE Board (Cameroon)"),
    ("OBC", "Office du Baccalauréat du Cameroun (OBC)"),
    ("WAEC", "WAEC (West Africa)"),
    ("NECO", "NECO (Nigeria)"),
    ("KCSE", "KCSE (Kenya)"),
    ("IGCSE_CIE", "Cambridge IGCSE"),
    ("IB", "International Baccalaureate (IB)"),
    ("AP_CB", "College Board (AP/SAT)"),
    ("BAC_FR", "Baccalauréat (France)"),
    ("ABITUR_DE", "Abitur (Germany)"),
    ("STATE_BOARD", "State/Provincial Board"),
    ("OTHER", "Other"),
]

SHARED_LEVEL_CHOICES = [
    ("O_LEVEL", "O-Level / IGCSE"),
    ("A_LEVEL", "A-Level / Advanced"),
    ("TECHNICAL", "Technical / Vocational"),
    ("DIPLOMA", "Diploma"),
    ("OTHER", "Other"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0043_classroom_updated_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="certificationexamsession",
            name="board",
            field=models.CharField(
                choices=SHARED_BOARD_CHOICES,
                default="OTHER",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="certificationexamsession",
            name="level",
            field=models.CharField(
                choices=SHARED_LEVEL_CHOICES,
                default="OTHER",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="certificationexamsession",
            name="name",
            field=models.CharField(
                help_text=(
                    "e.g., 'GCE Registration 2026 - O Level', 'IGCSE May/June 2026', "
                    "'WAEC SSCE 2026'"
                ),
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name="certificationexampreset",
            name="board",
            field=models.CharField(
                choices=SHARED_BOARD_CHOICES,
                default="OTHER",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="certificationexampreset",
            name="level",
            field=models.CharField(
                choices=SHARED_LEVEL_CHOICES,
                default="OTHER",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="certificationexampreset",
            name="code",
            field=models.CharField(
                help_text=(
                    "Short code, e.g. GCE_OLEVEL_2026, IGCSE_2026, WAEC_SSCE, BAC_FR_2026."
                ),
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="certificationcandidate",
            name="payment_transaction_id",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Payment gateway transaction/reference id used for validation "
                    "(Stripe, MTN MoMo, Paystack, etc.)."
                ),
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name="certificationcandidate",
            name="payment_amount_fcfa",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Amount paid in the tenant's fee-template currency (legacy column name "
                    "retained for backwards compatibility — value is not assumed to be in FCFA). "
                    "Use the linked CertificationFeeTemplate.currency for display."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="certificationfeeline",
            name="amount_fcfa",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Fee amount in the parent template's currency (legacy column name kept for "
                    "backwards compatibility — the value is NOT assumed to be FCFA)."
                ),
            ),
        ),
    ]
