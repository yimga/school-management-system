"""Heal phantom (fake-applied) drift on ``finance_notification``.

Migration ``0071`` adds ``dismissed_at`` / ``expires_at`` / ``school_id`` to
``finance_notification``. On this platform that ``AddField`` was recorded as
applied in ``django_migrations`` but never physically landed on the shared
(public) schema — so ``migrate_schemas --shared`` reports *"no migration to
apply"* while every authenticated page still 500s with
``column finance_notification.dismissed_at does not exist`` (the notification
bell / unread-count context runs on every render).

A plain re-run of ``0071`` cannot help: it is already recorded. This NEW,
unapplied migration is therefore the trigger that actually executes — its
``RunPython`` calls the idempotent ``schema_repair`` heal, which introspects the
live columns and adds only the missing ones (resolved from the live model so the
type / null / FK definition matches ``0071`` exactly). It is a no-op on a healthy
schema and safe to run on every deploy.

The columns are already in Django's model STATE (added by ``0071``), so this
migration carries NO state operations — it only reconciles the physical DB with
that state. Mirrors the ``0069`` pattern (RunPython delegating to schema_repair).
"""

from django.db import migrations


def _heal_notification_columns(apps, schema_editor):
    from apps.finance.schema_repair import ensure_finance_notification_columns

    ensure_finance_notification_columns()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0071_notification_dismissed_at_notification_expires_at_and_more"),
    ]

    operations = [
        # Reverse is a no-op: dropping the columns is owned by 0071's reverse;
        # this migration only ensures the physical schema matches existing state.
        migrations.RunPython(_heal_notification_columns, migrations.RunPython.noop),
    ]
