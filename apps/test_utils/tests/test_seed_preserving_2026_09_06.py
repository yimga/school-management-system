"""The flush that empties the seed catalog, and the mixin that puts it back.

This is an A/B inside one test method, on purpose. The alternative -- a control
class WITHOUT the mixin -- would itself truncate the database for everything
that runs after it, which is the very defect under test, and it would have to be
excused from the gate that forbids exactly that shape. Calling Django's
unpatched ``_fixture_teardown`` directly reproduces the damage and the mixin's
own teardown repairs it, so the whole proof is contained in one method and
leaves the database as it found it.
"""

from __future__ import annotations

from django.db import connections
from django.test import TransactionTestCase

from apps.accounts.models import AccessRole, Permission
from apps.test_utils.seed_preserving import RestoresSeedCatalogMixin


def _catalog():
    """The rows a flush destroys and the data migrations never re-create."""
    return (
        set(
            AccessRole.objects.filter(school__isnull=True).values_list(
                "code", flat=True
            )
        ),
        Permission.objects.count(),
    )


class SeedCatalogSurvivesTheFlushTests(RestoresSeedCatalogMixin, TransactionTestCase):
    """Reproduce the truncation and prove the restore, in that order."""

    def test_flush_empties_the_catalog_and_the_mixin_restores_it(self):
        roles_before, perms_before = _catalog()

        # Precondition. If the database this test is running against ALREADY has
        # an emptied catalog then the assertions below would pass vacuously --
        # 'unchanged' is trivially true when there was nothing to lose. That is
        # not hypothetical: it is the state every reused --keepdb database was in
        # before this mixin existed, so the test has to refuse to run rather than
        # report a green it has not earned.
        self.assertGreater(
            len(roles_before),
            1,
            "precondition: the global AccessRole catalog must be seeded before "
            "this test can say anything. Exactly one role means SUPERADMIN was "
            "recreated by post_migrate and the rest were flushed away -- rebuild "
            "the test database rather than trusting a green here.",
        )
        self.assertGreater(perms_before, 0, "precondition: permissions must be seeded")

        # Django's own teardown: this is what every TransactionTestCase in the
        # tree does after each test, and it is not rolled back.
        TransactionTestCase._fixture_teardown(self)

        roles_during, perms_during = _catalog()
        self.assertLess(
            len(roles_during),
            len(roles_before),
            "the unpatched teardown was expected to truncate the catalog; if it "
            "did not, this test is no longer measuring anything",
        )

        # The mixin's restore. It runs from tearDownClass in real use; calling
        # it directly is what lets this assert the repair in the same method
        # that caused the damage, instead of hoping a later test notices.
        self._restore_seed_catalog()

        roles_after, perms_after = _catalog()
        self.assertEqual(
            roles_after,
            roles_before,
            "the seed-preserving teardown must leave the global role catalog "
            "exactly as migrations left it",
        )
        self.assertEqual(perms_after, perms_before)

    def test_serialized_rollback_is_on_or_the_restore_is_inexact(self):
        """Not decoration -- two separate behaviours depend on this flag.

        Under ``manage.py test`` it is what makes Django serialize the database
        at all, and in ``_fixture_teardown`` it is what inhibits ``post_migrate``
        so the flush leaves a genuinely empty table. Without it ``post_migrate``
        recreates SUPERADMIN with a new primary key and the restore then collides
        with it on ``code``.
        """
        self.assertTrue(self.serialized_rollback)
        self.assertTrue(
            hasattr(connections["default"], "_test_serialized_contents"),
            "no post-migration snapshot was taken, so the mixin has nothing to "
            "restore from and is silently a no-op",
        )
