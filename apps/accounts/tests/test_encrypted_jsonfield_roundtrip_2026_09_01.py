"""An encrypted JSONField must give back a dict, not the ciphertext string.

FOUND BY: two tests failing with ``AssertionError: '{}' != {}`` that were being
carried as known-red. The message is the whole bug -- the value came back as
the STRING "{}" instead of the empty dict.

WHAT IS ACTUALLY HAPPENING

``EncryptedJSONField.get_prep_value`` returns TEXT: Fernet ciphertext, or the
literal ``"{}"`` sentinel for empty. ``JSONField.get_db_prep_value`` then runs
that through ``connection.ops.adapt_json_value``, i.e. ``json.dumps``, so what
reaches the column is a JSON *string* wrapping the TEXT.

That second encoding is not a bug and must not be removed. The column carries

    CHECK (JSON_VALID("legacy_hash_params") OR "legacy_hash_params" IS NULL)

and raw Fernet ciphertext is not valid JSON. Removing the wrap raises
``sqlite3.IntegrityError`` on the first save -- measured, on the first attempt
at this fix.

The defect was entirely on the read side, which never undid the wrap.
``from_db_value`` tried to decrypt the QUOTED form, failed, fell through to
``json.loads``, which succeeded, and returned the ciphertext as a plain ``str``.

WHY IT MATTERS BEYOND A RED TEST

``apps/accounts/auth_backends_legacy.py`` reads this field and hands it to
``verify_legacy_hash(algo, params, hash, password)`` as the algorithm's
parameters -- salt, iterations, key length. A ``str`` there is not a params
mapping, so a user carried over by the migration cloud could not log in with
their old password. The empty-dict case is the visible half; the tests below
pin the half that matters.
"""

from __future__ import annotations

import json

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.accounts.legacy_hashes.encryption import EncryptedJSONField, _get_fernet
from apps.accounts.models import User

PARAMS = {"salt": "s0m3-s4lt", "iterations": 120000, "keylen": 32}
QUOTE = chr(34)


def _raw_column(user_pk):
    """The bytes actually in the column, with no field conversion at all."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT legacy_hash_params FROM accounts_user WHERE id = %s", [user_pk]
        )
        return cursor.fetchone()[0]


class EncryptedJsonRoundTripTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="encjson_%s" % id(self),
            email="encjson_%s@example.com" % id(self),
            password="password123",
        )

    def _save(self, value):
        self.user.legacy_hash_params = value
        self.user.save(update_fields=["legacy_hash_params"])
        return User.objects.get(pk=self.user.pk)

    def test_a_params_dict_comes_back_as_a_dict(self):
        fetched = self._save(PARAMS)
        self.assertIsInstance(fetched.legacy_hash_params, dict)
        self.assertEqual(fetched.legacy_hash_params, PARAMS)

    def test_an_empty_dict_comes_back_as_a_dict(self):
        fetched = self._save({})
        self.assertIsInstance(fetched.legacy_hash_params, dict)
        self.assertEqual(fetched.legacy_hash_params, {})

    def test_the_salt_never_reaches_the_column(self):
        """The mirror. Without it, 'return the value unchanged' passes above."""
        self._save(PARAMS)
        raw = _raw_column(self.user.pk)
        self.assertNotIn("s0m3-s4lt", raw, "the salt is sitting in the column")

    def test_the_column_holds_valid_json_wrapping_a_fernet_token(self):
        """Why the write path keeps the JSON layer, in an executable form.

        The column's CHECK constraint requires JSON_VALID. A future change that
        stored the ciphertext bare would raise IntegrityError on save; this
        records the shape so the reason survives the next person to look at it.
        """
        self._save(PARAMS)
        raw = _raw_column(self.user.pk)
        inner = json.loads(raw)
        self.assertIsInstance(inner, str)
        self.assertTrue(inner.startswith("gAAAA"), f"not a Fernet token: {inner[:12]!r}")
        self.assertEqual(
            json.loads(_get_fernet().decrypt(inner.encode()).decode()), PARAMS
        )

    def test_the_database_refuses_a_bare_ciphertext_row(self):
        """Why the write path must keep the JSON layer -- proved by the database.

        The first attempt at this fix removed the second encoding on the WRITE
        side, which looked like the tidier change. This is the error it got,
        on the first save. Pinning it means the next person to reach for that
        change is told why before they spend the afternoon.
        """
        bare = EncryptedJSONField().get_prep_value(PARAMS)
        self.assertFalse(bare.startswith(QUOTE))
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE accounts_user SET legacy_hash_params = %s WHERE id = %s",
                    [bare, self.user.pk],
                )

    def test_an_empty_sentinel_written_either_way_reads_as_a_dict(self):
        for stored in (QUOTE + "{}" + QUOTE, "{}"):
            with self.subTest(stored=stored):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE accounts_user SET legacy_hash_params = %s WHERE id = %s",
                        [stored, self.user.pk],
                    )
                fetched = User.objects.get(pk=self.user.pk)
                self.assertIsInstance(fetched.legacy_hash_params, dict)
                self.assertEqual(fetched.legacy_hash_params, {})
