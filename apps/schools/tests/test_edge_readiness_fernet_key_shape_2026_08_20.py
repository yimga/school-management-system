"""A configured encryption key that cannot encrypt must fail the boot check.

The self-hosted box at 10.10.20.137 booted clean for weeks with a 20-char
``DJANGO_CRYPTOGRAPHY_KEY`` (15 raw bytes; Fernet wants 44 chars / 32 bytes).
``check_edge_readiness`` — which the web entrypoint runs on EVERY boot expressly
to surface edge footguns — printed ``OK: At-rest field-encryption key (Fernet) is
set and offline.`` because it only tested that the variable was non-empty.

The asymmetry that makes this invisible lives in
``apps/accounts/legacy_hashes/encryption.py``: ``from_db_value`` catches every
decrypt failure and returns the raw value, while ``get_prep_value`` does not
guard ``_get_fernet()``. So reads look healthy and writes raise ValueError. The
first casualty is normally Migration Cloud, whose ``legacy_hash_intake`` assigns
``user.legacy_password_hash`` on import.

These tests are DB-free on purpose so they can run without the test database.
"""

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.schools.management.commands.check_edge_readiness import (
    _fernet_key_defects,
)

# The exact shape measured on the box: 20 chars, decodes to 15 bytes.
BOX_KEY = "A" * 20


def _real_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


class FernetKeyDefectsTests(SimpleTestCase):
    def test_a_freshly_generated_key_has_no_defects(self):
        self.assertEqual(_fernet_key_defects(_real_key()), [])

    def test_the_key_shape_that_shipped_on_the_box_is_rejected(self):
        defects = _fernet_key_defects(BOX_KEY)
        self.assertEqual(len(defects), 1)
        self.assertIn("20 chars", defects[0])
        self.assertIn("want 44", defects[0])

    def test_a_44_char_string_that_is_not_base64_is_still_rejected(self):
        # Length alone was never the real test — this is why the check builds
        # the Fernet instead of measuring the string.
        self.assertTrue(_fernet_key_defects("!" * 44))

    def test_defects_never_echo_key_material(self):
        secret = "S3cr3tPassphraseNobodyShouldEverSee!!"
        for defect in _fernet_key_defects(secret):
            self.assertNotIn(secret, defect)
            self.assertNotIn(secret[:8], defect)

    def test_a_rotation_list_reports_the_offending_position(self):
        defects = _fernet_key_defects([_real_key(), BOX_KEY, _real_key()])
        self.assertEqual(len(defects), 1)
        self.assertIn("key #2", defects[0])

    def test_bytes_entries_are_accepted_like_strings(self):
        self.assertEqual(_fernet_key_defects(_real_key().encode("ascii")), [])

    def test_blank_entries_are_skipped_not_reported(self):
        # Absence is a different finding, handled by the "no explicit key" branch.
        self.assertEqual(_fernet_key_defects(["", None, "   "]), [])


@override_settings(SINGLE_TENANT=False, DJANGO_CRYPTOGRAPHY_KEYS_SOURCE="env")
class CheckEdgeReadinessReportsKeyShapeTests(SimpleTestCase):
    def _run(self, **settings_kwargs):
        out = StringIO()
        with override_settings(**settings_kwargs):
            call_command("check_edge_readiness", stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_an_unusable_key_is_a_FAIL_not_an_OK(self):
        output = self._run(DJANGO_CRYPTOGRAPHY_KEYS=[BOX_KEY])
        self.assertIn("NOT a usable Fernet key", output)
        self.assertIn("FAIL", output)

    def test_the_failure_names_the_consequence_and_the_remedy(self):
        output = self._run(DJANGO_CRYPTOGRAPHY_KEYS=[BOX_KEY])
        self.assertIn("raises ValueError", output)
        self.assertIn("Fernet.generate_key()", output)

    def test_a_good_key_still_reports_OK(self):
        output = self._run(DJANGO_CRYPTOGRAPHY_KEYS=[_real_key()])
        self.assertIn("well-formed", output)
        self.assertNotIn("NOT a usable Fernet key", output)

    def test_strict_mode_refuses_to_boot_on_an_unusable_key(self):
        # The entrypoint honours RMC_EDGE_READINESS_STRICT=1; this is what makes
        # that switch actually protect a box from the write-time 500.
        from django.core.management.base import CommandError

        with override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[BOX_KEY]):
            with self.assertRaises(CommandError):
                call_command(
                    "check_edge_readiness", "--strict",
                    stdout=StringIO(), stderr=StringIO(),
                )
