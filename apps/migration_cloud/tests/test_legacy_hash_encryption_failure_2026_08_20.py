"""A Fernet key that cannot encrypt is not a DatabaseError, and the guard only caught
DatabaseError.

Three of the four ``INTAKE_FIELDS`` are ``EncryptedCharField``s, and
``EncryptedCharField.get_prep_value`` builds a ``Fernet`` on every NON-EMPTY write. A
``DJANGO_CRYPTOGRAPHY_KEY`` that is not 32 url-safe base64 bytes raises::

    ValueError: Fernet key must be 32 url-safe base64-encoded bytes.

``ValueError`` is not a ``DatabaseError``, so it sailed straight past the handler and
became a 500 on the import. The sovereign box measured on 2026-08-20 carried a 20-char
/ 15-byte key.

Why it stayed invisible: ``from_db_value`` wraps decrypt in try/except and returns the
raw value, so READS never fail; and ``""``/``None`` short-circuit before the Fernet is
ever constructed, so a deployment with no legacy hashes looks completely healthy right
up to the first import that carries one. That asymmetry is why it reads as intermittent.

Returning False (rather than raising) matches the DatabaseError contract already in the
function: this user keeps no legacy hash and will reset their password, while the rest
of the import proceeds. One misconfigured key must not cost the whole migration.

NOTE ON THE LOG ASSERTIONS. ``config/settings_test.py`` calls
``logging.disable(logging.CRITICAL)``, so ``assertLogs`` sees nothing here no matter
what the code emits — a trap that makes a log assertion pass or fail for reasons
unrelated to the code. These tests patch the module logger and assert on the CALL,
which is what we actually care about and is immune to the global disable.
"""
from __future__ import annotations

import contextlib
from unittest import mock

from django.db import DatabaseError
from django.test import SimpleTestCase

from apps.migration_cloud.services import legacy_hash_intake
from apps.migration_cloud.services.legacy_hash_intake import (
    INTAKE_FIELDS,
    store_legacy_hash,
)

FERNET_MESSAGE = "Fernet key must be 32 url-safe base64-encoded bytes."
GOOD_HASH = "$2b$12$abcdefghijklmnopqrstuv"


def _user(save_raises=None):
    """A spec'd mock: ``store_legacy_hash`` isinstance-checks the user model, and a mock
    with ``spec=`` satisfies that without needing the database."""
    from django.contrib.auth import get_user_model

    user = mock.MagicMock(spec=get_user_model())
    user.pk = 4242
    if save_raises is not None:
        user.save.side_effect = save_raises
    return user


class _NoDbMixin:
    """Neutralise ``transaction.atomic`` so these stay SimpleTestCase.

    What is under test is WHICH except clause catches the encryption failure, and that
    is decided entirely by exception type — the transaction adds nothing to it. Keeping
    the database out means this module runs in milliseconds rather than waiting on a
    migration replay, which is the difference between a test people run and one they
    skip.
    """

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(
            legacy_hash_intake.transaction,
            "atomic",
            lambda *a, **k: contextlib.nullcontext(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def captured_logger(self):
        with mock.patch.object(legacy_hash_intake, "logger") as logger:
            yield logger

    @staticmethod
    def _extra(logger):
        assert logger.exception.called, "expected logger.exception to be called"
        return logger.exception.call_args.kwargs["extra"]


class EncryptionFailureTests(_NoDbMixin, SimpleTestCase):
    def test_a_bad_fernet_key_returns_false_instead_of_500ing(self):
        """THE BUG. Before the fix this ValueError escaped and became a 500."""
        user = _user(save_raises=ValueError(FERNET_MESSAGE))
        with self.captured_logger():
            self.assertFalse(
                store_legacy_hash(
                    user,
                    hash_value=GOOD_HASH,
                    algorithm="bcrypt",
                    source_vendor="powerschool",
                )
            )

    def test_it_is_reported_as_an_encryption_failure_not_a_save_failure(self):
        """Distinct from the DB branch, so the operator is not sent to the wrong layer."""
        user = _user(save_raises=ValueError(FERNET_MESSAGE))
        with self.captured_logger() as logger:
            store_legacy_hash(user, hash_value=GOOD_HASH, algorithm="bcrypt")
        self.assertEqual(logger.exception.call_args.args[0], "legacy_hash_intake_encryption_failed")
        self.assertEqual(self._extra(logger)["result"], "encryption_failed")

    def test_the_log_names_the_env_var_and_the_command_that_checks_it(self):
        """A diagnosis an operator cannot act on is a more precise way of being stuck."""
        user = _user(save_raises=ValueError(FERNET_MESSAGE))
        with self.captured_logger() as logger:
            store_legacy_hash(user, hash_value=GOOD_HASH, algorithm="bcrypt")
        remediation = self._extra(logger)["remediation"]
        self.assertIn("DJANGO_CRYPTOGRAPHY_KEY", remediation)
        self.assertIn("check_edge_readiness", remediation)

    def test_the_failure_log_carries_no_hash_material(self):
        """The whole point of the field being encrypted."""
        secret = "$2b$12$THISMUSTNEVERBELOGGED"
        user = _user(save_raises=ValueError(FERNET_MESSAGE))
        with self.captured_logger() as logger:
            store_legacy_hash(user, hash_value=secret, algorithm="bcrypt")
        blob = repr(logger.exception.call_args)
        self.assertNotIn(secret, blob)

    def test_a_database_error_still_behaves_exactly_as_before(self):
        """The pre-existing contract must not shift underneath the new branch."""
        user = _user(save_raises=DatabaseError("connection lost"))
        with self.captured_logger() as logger:
            self.assertFalse(store_legacy_hash(user, hash_value=GOOD_HASH, algorithm="bcrypt"))
        self.assertEqual(self._extra(logger)["result"], "save_failed")

    def test_an_unexpected_error_is_still_allowed_to_propagate(self):
        """Widening to ValueError must not turn the write into a silent swallow-all.

        A TypeError here is a programming error and must reach a human.
        """
        user = _user(save_raises=TypeError("wrong shape"))
        with self.captured_logger():
            with self.assertRaises(TypeError):
                store_legacy_hash(user, hash_value=GOOD_HASH, algorithm="bcrypt")

    def test_a_healthy_write_still_succeeds(self):
        user = _user()
        with self.captured_logger():
            self.assertTrue(
                store_legacy_hash(
                    user,
                    hash_value=GOOD_HASH,
                    algorithm="bcrypt",
                    source_vendor="powerschool",
                )
            )
        user.save.assert_called_once()
        self.assertEqual(
            set(user.save.call_args.kwargs["update_fields"]), set(INTAKE_FIELDS)
        )


class BlastRadiusTests(_NoDbMixin, SimpleTestCase):
    def test_the_three_encrypted_fields_are_still_the_ones_written(self):
        """If a fourth encrypted field joins INTAKE_FIELDS this test should be revisited,
        because it widens the surface a bad key can take down."""
        for field in ("legacy_password_hash", "legacy_hash_algorithm", "legacy_hash_params"):
            self.assertIn(field, INTAKE_FIELDS)

    def test_an_empty_hash_never_reaches_the_encryption_path(self):
        """Why a broken key looks healthy: "" short-circuits before Fernet is built, so
        every import WITHOUT legacy passwords passes on a box that would 500 on one."""
        user = _user(save_raises=ValueError(FERNET_MESSAGE))
        with self.captured_logger():
            with self.assertRaises(ValueError):
                store_legacy_hash(user, hash_value="", algorithm="bcrypt")
        user.save.assert_not_called()
