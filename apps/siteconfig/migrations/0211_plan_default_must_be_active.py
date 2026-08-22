"""A plan marked as the platform default must stay active.

``Plan.get_default_plan()`` filters on ``is_default=True`` AND ``is_active=True``,
but ``plan_unique_default`` only enforces that at most ONE plan carries the flag --
nothing stopped an operator deactivating the plan that carried it. In that state
``get_default_plan()`` returns None, and ``apps.schools.plan_gating`` could not tell
that apart from "no plan catalog at all": it treated the free tier as having zero
features, which classifies EVERY feature of EVERY active plan as plan-gated. With
``RMC_PLAN_GATING_ENFORCED=1`` that is a platform-wide lockout.

plan_gating now fails open on that state, and this constraint stops it arising.
Any pre-existing offending row is repaired first (the flag is dropped, not the
deactivation reverted -- deactivating was the deliberate act) so the constraint
cannot crash a deploy on live data.
"""

from __future__ import annotations

from django.db import migrations, models


def drop_default_flag_from_inactive_plans(apps, schema_editor):
    Plan = apps.get_model("siteconfig", "Plan")
    Plan.objects.filter(is_default=True, is_active=False).update(is_default=False)


def noop_reverse(apps, schema_editor):
    """Nothing to restore: the flag was invalid where it was cleared."""


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0210_seed_region_academic_calendars"),
    ]

    operations = [
        migrations.RunPython(
            drop_default_flag_from_inactive_plans, noop_reverse
        ),
        migrations.AddConstraint(
            model_name="plan",
            constraint=models.CheckConstraint(
                condition=models.Q(is_default=False) | models.Q(is_active=True),
                name="plan_default_must_be_active",
            ),
        ),
    ]
