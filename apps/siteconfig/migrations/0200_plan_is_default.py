"""Add Plan.is_default + seed the Free tier as the platform default plan.

New tenants created without an explicit plan bind to the default plan (Free),
which activates Free-tier entitlements + usage limits from day one. At most one
active plan may be the default (partial-unique constraint).
"""

from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


def seed_default_plan(apps, schema_editor):
    Plan = apps.get_model("siteconfig", "Plan")
    if Plan.objects.filter(is_default=True).exists():
        return
    # Prefer the canonical Free plan by slug, then any active free-priced plan,
    # then the first active plan. Mark EXACTLY ONE so the partial-unique
    # constraint added below is satisfied.
    candidate = (
        Plan.objects.filter(is_active=True, slug="basic").first()
        or Plan.objects.filter(is_active=True, slug="free").first()
        or Plan.objects.filter(is_active=True)
        .filter(Q(base_price__isnull=True) | Q(base_price=0))
        .order_by("name", "id")
        .first()
        or Plan.objects.filter(is_active=True).order_by("name", "id").first()
    )
    if candidate is not None:
        candidate.is_default = True
        candidate.save(update_fields=["is_default"])


def unset_default_plan(apps, schema_editor):
    Plan = apps.get_model("siteconfig", "Plan")
    Plan.objects.filter(is_default=True).update(is_default=False)


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0199_reseed_dashboard_packs_depth"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="is_default",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When set, new tenants created without an explicit plan are "
                    "bound to this plan (the platform default — typically the Free "
                    "tier). At most one active plan may be the default."
                ),
            ),
        ),
        migrations.RunPython(seed_default_plan, unset_default_plan),
        migrations.AddConstraint(
            model_name="plan",
            constraint=models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="plan_unique_default",
            ),
        ),
    ]
