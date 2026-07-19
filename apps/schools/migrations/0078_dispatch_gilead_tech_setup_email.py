"""One-time, on-deploy dispatch of the gilead-tech owner setup email.

Runs once (recorded in django_migrations, so it never re-fires on later deploys)
during the release ``migrate``. Test-skipped and fully fail-soft — a deploy must
never fail on an email. Delivery still needs the Brevo mail secrets in prod; when
absent the send layer no-ops. The manual ``manage.py resend_owner_setup_email``
remains the reliable path. Real logic lives in apps/schools/deploy_dispatch.py.

Important (Postgres): ``deploy_dispatch`` is fail-soft and may swallow a DB error
after the connection is already marked ``needs_rollback``. That aborts the outer
migration atomic block and makes ``record_applied`` raise
``TransactionManagementError``. The email work MUST run inside a savepoint that
we roll back whenever the connection is broken, so migrate can still record this
node and continue.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import migrations

logger = logging.getLogger("schools.deploy_dispatch")


def _dispatch(apps, schema_editor):
    # Never send during a test-DB build — only on a real deploy migrate.
    if getattr(settings, "RUNNING_TESTS", False):
        return
    # `School` lives in the shared/public schema; under django-tenants only the
    # public run should dispatch (belt-and-suspenders against a per-tenant re-run).
    connection = getattr(schema_editor, "connection", None)
    if connection is None:
        return
    schema = getattr(connection, "schema_name", None)
    if schema is not None and schema != "public":
        return

    sid = connection.savepoint()
    try:
        from apps.schools.deploy_dispatch import (
            GILEAD_TECH_SLUG,
            dispatch_setup_email_for_slug,
        )

        dispatch_setup_email_for_slug(GILEAD_TECH_SLUG)
    except Exception:  # noqa: BLE001 — a deploy must never fail on an email dispatch
        logger.warning("schools.0078 dispatch raised; rolling back savepoint", exc_info=True)
    finally:
        # If any query inside the savepoint failed (even when deploy_dispatch
        # swallowed the Python exception), restore a clean outer transaction
        # so django_migrations.record_applied can run.
        if getattr(connection, "needs_rollback", False):
            logger.warning(
                "schools.0078: connection needs_rollback after dispatch — "
                "savepoint_rollback so migrate can record the migration"
            )
            connection.savepoint_rollback(sid)
        else:
            try:
                connection.savepoint_commit(sid)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "schools.0078: savepoint_commit failed; rolling back",
                    exc_info=True,
                )
                try:
                    connection.savepoint_rollback(sid)
                except Exception:  # noqa: BLE001
                    pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0077_schoolmembership_suspended_at"),
    ]

    operations = [
        migrations.RunPython(_dispatch, migrations.RunPython.noop),
    ]
