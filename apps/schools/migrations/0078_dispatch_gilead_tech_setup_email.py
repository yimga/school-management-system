"""One-time, on-deploy dispatch of the gilead-tech owner setup email.

Runs once (recorded in django_migrations, so it never re-fires on later deploys)
during the release ``migrate``. Test-skipped and fully fail-soft — a deploy must
never fail on an email. Delivery still needs the Brevo mail secrets in prod; when
absent the send layer no-ops. The manual ``manage.py resend_owner_setup_email``
remains the reliable path. Real logic lives in apps/schools/deploy_dispatch.py.
"""
from __future__ import annotations

from django.conf import settings
from django.db import migrations


def _dispatch(apps, schema_editor):
    # Never send during a test-DB build — only on a real deploy migrate.
    if getattr(settings, "RUNNING_TESTS", False):
        return
    # `School` lives in the shared/public schema; under django-tenants only the
    # public run should dispatch (belt-and-suspenders against a per-tenant re-run).
    schema = getattr(getattr(schema_editor, "connection", None), "schema_name", None)
    if schema is not None and schema != "public":
        return
    try:
        from apps.schools.deploy_dispatch import (
            GILEAD_TECH_SLUG,
            dispatch_setup_email_for_slug,
        )

        dispatch_setup_email_for_slug(GILEAD_TECH_SLUG)
    except Exception:  # noqa: BLE001 — a deploy must never fail on an email dispatch
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0077_schoolmembership_suspended_at"),
    ]

    operations = [
        migrations.RunPython(_dispatch, migrations.RunPython.noop),
    ]
