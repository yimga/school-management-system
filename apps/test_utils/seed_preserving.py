"""Restore the migration-seeded catalog that a ``TransactionTestCase`` truncates.

``TransactionTestCase._fixture_teardown`` runs ``flush``, which TRUNCATES EVERY
TABLE and is not rolled back. Against this repo's persisted ``--keepdb`` database
that damage is permanent: the migrations stay recorded as applied, so the
idempotent data-seed migrations never re-run. ``flush`` re-emits ``post_migrate``,
which is why exactly one ``AccessRole`` survives -- ``superadmin_sync`` recreates
SUPERADMIN and nothing recreates the rest.

Granular RBAC resolves through ``accounts_permission`` / ``accounts_accessrole``,
so the downstream symptom is **unrelated suites returning 403** and looking like
permission regressions in code that is fine. Measured on this repo
(``docs/audits/TRANSACTION_TESTCASE_FLUSH_2026_09_03.md``):

    table                    TestCase   TransactionTestCase
    accounts_permission            46                     0
    accounts_accessrole            27                     1
    siteconfig_themepack            5                     0

The 2026-09-03 audit converted 32 classes to ``TestCase`` and left the rest with
the instruction "order it last". That is not enforceable and, under pytest, not
even possible: pytest runs in COLLECTION order and never reorders. Django's own
runner does sort ``TestCase`` before ``TransactionTestCase``, which is why the
two runners disagree about this suite -- but even there the flush still lands on
the persisted file, so the NEXT run starts with an empty catalog whatever the
order was. **The flush and the failure need not be in the same run at all**,
which is what makes it so hard to trace: a single-file run can fail because of a
whole-suite run from yesterday.

WHY THIS RESTORES RATHER THAN AVOIDS THE FLUSH
----------------------------------------------
``serialized_rollback = True`` alone does NOT fix it. Django restores the
serialized snapshot in ``_fixture_setup`` -- at the START of each test -- so the
flushing class gets its own seeds and every test that runs AFTER it still finds
an empty database. The restore has to happen after the flush, which is what this
mixin adds.

Setting ``serialized_rollback`` is still required, for two separate reasons:

* under ``manage.py test`` it is what makes Django serialize at all
  (``DiscoverRunner.get_databases`` collects ``serialized_aliases`` from the test
  classes that ask for it), and
* it makes ``_fixture_teardown`` inhibit ``post_migrate``, so the flush leaves a
  genuinely empty database and the restore is EXACT. Without it, ``post_migrate``
  recreates SUPERADMIN with a fresh primary key and the restore then collides
  with it on ``code``.

Under pytest this repo's ``conftest.py`` calls ``setup_databases`` with
``serialized_aliases=None``, which Django reads as "serialize every alias", so the
snapshot is already being taken on every session.

THE INVARIANT
-------------
After any flushing CLASS, the database equals the database as it was after
migrations. That holds for the next class and -- because the file is kept -- for
the next run.

Deliberately per-class rather than per-test: restoring after every test measured
2.9x on a 15-test module (42.07s against 14.55s), and it would also have changed
what those tests see. A ``TransactionTestCase`` has always started each of its
own tests against a flushed database; every one of these classes was written
that way and still is. The damage this module exists to stop is the damage that
ESCAPES the class -- into the next suite, and into the persisted file.
"""

from __future__ import annotations

import logging

from django.db import connections

logger = logging.getLogger(__name__)


class RestoresSeedCatalogMixin:
    """Re-deserialize the post-migration snapshot after the flush.

    Mix in BEFORE the ``TransactionTestCase`` base so this ``_fixture_teardown``
    wins::

        class MyTests(RestoresSeedCatalogMixin, TransactionTestCase):
            ...

    ``LiveServerTestCase`` is a ``TransactionTestCase`` subclass and flushes
    identically, so it needs this too -- and a search for the obvious base class
    does not find it.
    """

    #: Required. See the module docstring: this is what makes Django serialize
    #: under ``manage.py test`` AND what stops ``post_migrate`` racing the
    #: restore. Turning it off silently makes the restore inexact.
    serialized_rollback = True

    @classmethod
    def _fixture_setup(cls):
        """Skip Django's SETUP-side restore; this class restores at teardown.

        With ``serialized_rollback`` on, Django deserializes the snapshot at the
        start of every test. Because this mixin already restores AFTER the flush,
        the database is already the post-migration one by then, and deserializing
        a second time re-inserts rows that are still there. That is not harmless:
        it raises IntegrityError on the first model carrying a unique constraint
        that is not its primary key. Measured 2026-09-06 --
        ``accounts_relationship_tuple`` has a six-column unique constraint, and
        the second test of a converted class died in setUp rather than in its own
        body, which is a confusing place for a fixture to fail.

        The attribute itself must stay True: it is what makes ``DiscoverRunner``
        serialize the alias under ``manage.py test``, and what makes
        ``_fixture_teardown`` inhibit ``post_migrate`` so the flush leaves a
        genuinely empty database for the restore to land in. Only the setup-side
        deserialize is suppressed, and only for the duration of this call.

        Suppressing it is also most of the cost saving: with the restore moved
        to ``tearDownClass``, a converted class deserializes ONCE rather than
        twice per test.
        """
        original = cls.serialized_rollback
        cls.serialized_rollback = False
        try:
            super()._fixture_setup()
        finally:
            cls.serialized_rollback = original

    @classmethod
    def tearDownClass(cls):
        """Restore once per CLASS, not once per test.

        Per-test restore was measured at 42.07s against 14.55s for the same
        15-test module -- 2.9x, for an invariant that only has to hold at the
        BOUNDARY. Restoring here costs one deserialize per class instead of
        fifteen, and it also leaves the intra-class contract exactly as Django
        wrote it: a TransactionTestCase has always started each of its own tests
        against a flushed database, and every one of these classes was written
        against that. Restoring between them would have been a behaviour change
        smuggled in under a correctness fix.

        What downstream code and the persisted --keepdb file see is unchanged:
        by the time the next class -- or the next run -- looks, the database is
        the post-migration one again.
        """
        try:
            cls._restore_seed_catalog()
        finally:
            super().tearDownClass()

    @classmethod
    def _restore_seed_catalog(cls):
        for db_name in cls._databases_names(include_mirrors=False):
            connection = connections[db_name]
            contents = getattr(connection, "_test_serialized_contents", None)
            if not contents:
                # No snapshot to restore from. Do not raise -- a teardown that
                # explodes replaces a real failure with a confusing one -- but do
                # say so, because a silent no-op here is exactly the shape of the
                # bug this module exists to remove.
                logger.warning(
                    "seed-preserving teardown: alias %r has no serialized "
                    "snapshot, so the catalog this test flushed is NOT being "
                    "restored. Every later test in this run, and every later run "
                    "reusing this database file, will see an empty catalog.",
                    db_name,
                )
                continue
            connection.creation.deserialize_db_from_string(contents)
