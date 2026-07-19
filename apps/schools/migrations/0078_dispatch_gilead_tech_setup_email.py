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
    connection = getattr(schema_editor, "connection", None)
    schema = getattr(connection, "schema_name", None)
    # #region agent log
    def _agent_log(hypothesis_id, message, data):
        import json
        import logging
        import time
        from pathlib import Path

        payload = {
            "sessionId": "537138",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": "schools.0078._dispatch",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        logging.getLogger("schools.deploy_dispatch").warning(
            "DEBUG537138 %s", json.dumps(payload, default=str)
        )
        try:
            Path("debug-537138.log").open("a", encoding="utf-8").write(
                json.dumps(payload, default=str) + "\n"
            )
        except Exception:  # noqa: BLE001
            pass

    # #endregion
    # #region agent log
    _agent_log(
        "A",
        "0078_enter",
        {
            "schema": schema,
            "vendor": getattr(connection, "vendor", None),
            "needs_rollback_before": bool(
                getattr(connection, "needs_rollback", False)
            ),
            "in_atomic_block": bool(getattr(connection, "in_atomic_block", False)),
        },
    )
    # #endregion
    if schema is not None and schema != "public":
        # #region agent log
        _agent_log("D", "0078_skip_non_public", {"schema": schema})
        # #endregion
        return
    try:
        from apps.schools.deploy_dispatch import (
            GILEAD_TECH_SLUG,
            dispatch_setup_email_for_slug,
        )

        result = dispatch_setup_email_for_slug(GILEAD_TECH_SLUG)
        # #region agent log
        _agent_log(
            "A",
            "0078_after_dispatch",
            {
                "result": result,
                "needs_rollback_after": bool(
                    getattr(connection, "needs_rollback", False)
                ),
                "in_atomic_block": bool(
                    getattr(connection, "in_atomic_block", False)
                ),
            },
        )
        # #endregion
    except Exception as ex:  # noqa: BLE001 — a deploy must never fail on an email dispatch
        # #region agent log
        _agent_log(
            "A",
            "0078_swallowed_exception",
            {
                "exc_type": type(ex).__name__,
                "exc": str(ex)[:300],
                "needs_rollback": bool(
                    getattr(connection, "needs_rollback", False)
                ),
            },
        )
        # #endregion
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0077_schoolmembership_suspended_at"),
    ]

    operations = [
        migrations.RunPython(_dispatch, migrations.RunPython.noop),
    ]
