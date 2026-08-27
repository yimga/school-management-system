# Outbox retry bookkeeping + attribution idempotency.
#
# 1. SocialPostOutbox.attempts / next_attempt_at. 'throttled' and 'processing'
#    were both TERMINAL states reached by accident: the only sweeper filtered
#    status="pending", nothing anywhere moved a row back, and the caller had
#    already been handed 202 Accepted. These two columns are what let the drainer
#    retry a rate-limited row on a backoff and reap a row whose worker died.
#
# 2. A PARTIAL unique constraint on (school, provider, transaction_id).
#    record_utm_attribution was an unconditional create(), so a retried call
#    double-counted attributed donation revenue in the dashboard chart. Partial
#    (transaction_id != '') because the column is blank=True: an unqualified
#    unique index would allow exactly ONE blank row per (school, provider), which
#    is the blank+unique trap, not the constraint we want.
#
# The RunPython ahead of AddConstraint collapses any pre-existing duplicates,
# keeping the earliest row per key -- AddConstraint on a table that already
# violates the constraint fails the deploy, and "there probably are none" is not
# a migration strategy.

from django.conf import settings
from django.db import migrations, models


def collapse_duplicate_attributions(apps, schema_editor):
    from django.db.models import Count

    Attribution = apps.get_model("social_media", "SocialCampaignAttribution")
    dupes = (
        Attribution.objects.exclude(transaction_id="")
        .values("school_id", "provider", "transaction_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for group in dupes:
        rows = list(
            Attribution.objects.filter(
                school_id=group["school_id"],
                provider=group["provider"],
                transaction_id=group["transaction_id"],
            ).order_by("recorded_at", "id")
        )
        # Keep the first-recorded row; the rest are the double-counts.
        for row in rows[1:]:
            row.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0087_alter_school_subdomain'),
        ('social_media', '0003_rls_policy_default_deny'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='socialpostoutbox',
            name='attempts',
            field=models.PositiveSmallIntegerField(default=0, help_text='Delivery attempts made so far. Drives the retry backoff and the give-up ceiling.'),
        ),
        migrations.AddField(
            model_name='socialpostoutbox',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, help_text='Earliest retry time (throttled) or worker lease expiry (processing).', null=True),
        ),
        migrations.AddIndex(
            model_name='socialpostoutbox',
            index=models.Index(fields=['status', 'next_attempt_at'], name='social_post_status__d41a77_idx'),
        ),
        migrations.RunPython(
            collapse_duplicate_attributions, migrations.RunPython.noop, elidable=True
        ),
        migrations.AddConstraint(
            model_name='socialcampaignattribution',
            constraint=models.UniqueConstraint(condition=models.Q(('transaction_id', ''), _negated=True), fields=('school', 'provider', 'transaction_id'), name='uniq_social_attribution_transaction'),
        ),
    ]
