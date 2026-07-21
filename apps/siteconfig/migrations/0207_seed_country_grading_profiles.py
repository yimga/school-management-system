# Data migration: seed CountryGradingProfile (country -> default grading scale).
#
# Unlocks four scales that no school on the platform could previously reach —
# german_1_6, cbse_10, numeric_1_5, numeric_0_20 — and corrects mappings the old
# five-continent bucket got actively wrong (DE/ES/AU resolved to the UK GCSE 9-1
# axis, whose max of 9 REJECTS a valid mark of 10).
#
# Seeding is a DEFAULT for newly provisioned schools only: existing tenants keep
# whatever GradingScale / AssessmentWeights they already have, because
# ensure_local_grading_scale skips a school that already owns a default scale and
# resolve_school_score_scale reads AssessmentWeights before any country signal.

from django.db import migrations


def seed_country_grading(apps, schema_editor):
    from apps.siteconfig.country_grading_seed import seed_country_grading_profiles

    seed_country_grading_profiles(using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0206_country_grading_profile"),
    ]

    operations = [
        migrations.RunPython(seed_country_grading, noop),
    ]
