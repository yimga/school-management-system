"""schools.0078 — intentionally inert (was: on-deploy gilead-tech setup email).

History: this node originally dispatched the "your school is ready" owner-setup
email during the release ``migrate``. That is fundamentally unsafe — the send does
fail-soft DB writes + SMTP *inside the migration's atomic transaction*. When any
query fails (a cross-app table not yet migrated, an SMTP-audit INSERT, etc.), the
fail-soft ``except`` swallows the Python error but Postgres leaves the connection
in ``needs_rollback``. The migration framework's ``record_applied`` then raises
``TransactionManagementError`` and ABORTS THE ENTIRE DEPLOY. A savepoint dance
cannot rescue it: once ``needs_rollback`` is set, the ``ROLLBACK TO SAVEPOINT``
SQL is itself blocked by ``validate_no_broken_transaction`` (which is exactly the
Render pre-deploy crash observed 2026-07-19).

The owner-setup email now lives ONLY where it belongs — OUTSIDE migrate, in a
normal request/command context where a mail failure can never abort a deploy:

  * ``manage.py resend_owner_setup_email --school gilead-tech``
  * the operator "Resend owner setup email" button on the tenant-360 page
    (``apps/schools/super_views_owner_email.py``).

This node is kept (it may already be recorded in some environments'
``django_migrations``) but is now a guaranteed no-op.
"""
from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0077_schoolmembership_suspended_at"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
