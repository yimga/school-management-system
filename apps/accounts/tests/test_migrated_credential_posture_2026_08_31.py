"""Audit seal: the credential posture of a migrated / provisioned account.

The audited requirement has THREE independently-checkable properties. A newly
migrated or provisioned account must be created with

  1. a HIGH-ENTROPY, single-use temporary credential,
  2. stored ONLY as a salted cryptographic hash, and
  3. carrying a force-password-reset marker.

Each property gets its own test class, and each test is written so that
BREAKING the product code turns it red -- not so that it restates what the code
currently does. Two of them are regression seals for defects this audit found:

  * ``test_provisioning_refuses_a_dictionary_word`` -- before 2026-08-31
    ``provision_tenant_user_with_temp_password`` checked only ``len >= 8``, so
    the literal string "password" (37.6 bits) provisioned a tenant account.
  * ``test_handover_sheet_is_marked_no_store`` -- the one-time password CSV is
    ``text/csv``, and ``HtmlNoCacheMiddleware`` only stamps ``text/html``, so a
    download of up to 5000 cleartext credentials carried no cache directives.

The log-leak detector in :class:`TempCredentialStorageTests` PROVES itself
before it is believed: it plants a known leak, asserts it is caught, and only
then asserts the real paths are clean. A detector that has never fired is not
evidence of anything.
"""

from __future__ import annotations

import logging
import math
import uuid
from contextlib import contextmanager

from django.test import TestCase

from apps.accounts import credential_reset
from apps.accounts.credential_reset import (
    generate_temp_password,
    set_temporary_password,
)
from apps.accounts.models import User
from apps.accounts.tenant_user_provisioning import (
    TEMP_PASSWORD_MIN_BITS,
    ProvisioningError,
    provision_tenant_user_with_temp_password,
    temp_password_entropy_bits,
)
from apps.migration_cloud.people_activation import handover_csv_response
from apps.people.models import TeacherProfile
from apps.schools.models import School

# The generator's own claim, asserted rather than trusted: 14 characters over a
# 54-symbol alphabet is 14 * log2(54) = 80.57 bits.
REQUIRED_GENERATED_BITS = 80.0

# Loggers every in-scope credential path writes through. Captured by name AND
# via root, because a logger with propagate=False would otherwise hide a leak
# from a root-only handler.
_CREDENTIAL_LOGGERS = (
    "",
    "security.account_recovery",
    "apps.migration_cloud.people_activation",
    "apps.accounts.guardian_invite",
    "apps.accounts.tenant_user_provisioning",
)


def _mk_school(tag):
    """A school with a unique slug + subdomain.

    Both are ``blank=True, unique=True``, so a second blank one collides -- the
    tests must never rely on the seeded school being free.
    """
    return School.objects.create(
        name=f"Credential Posture {tag}",
        slug=f"{tag}-{uuid.uuid4().hex[:8]}",
        subdomain=f"{tag}-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


def _mk_unusable_user(role=User.Role.TEACHER):
    """An imported-but-not-yet-activated account: real row, no usable password."""
    user = User.objects.create_user(
        username=f"u-{uuid.uuid4().hex[:10]}",
        email=f"{uuid.uuid4().hex[:10]}@example.test",
        role=role,
    )
    user.set_unusable_password()
    user.save()
    return user


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def blob(self):
        parts = []
        for record in self.records:
            try:
                parts.append(record.getMessage())
            except Exception:  # noqa: BLE001 -- a bad format string is not the subject
                parts.append(str(record.msg))
            parts.append(str(getattr(record, "args", "") or ""))
        return " ".join(parts)


@contextmanager
def _capture_credential_logs():
    """Capture every credential-path log record, defeating ``logging.disable``.

    ``config.settings`` can raise the global disable level, which silently makes
    a log assertion inert -- the trap that left 115 assertions in this repo
    passing against nothing. The previous level is restored on exit.
    """
    handler = _Capture()
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    touched = []
    for name in _CREDENTIAL_LOGGERS:
        logger = logging.getLogger(name)
        touched.append((logger, logger.level, logger.propagate))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = True
    try:
        yield handler
    finally:
        for logger, level, propagate in touched:
            logger.removeHandler(handler)
            logger.setLevel(level)
            logger.propagate = propagate
        logging.disable(previous_disable)


# --------------------------------------------------------------------------- #
# Property 1 -- ENTROPY
# --------------------------------------------------------------------------- #
class TempCredentialEntropyTests(TestCase):
    """The temporary credential must be unguessable, whoever supplies it."""

    def test_generator_is_secrets_backed_and_never_uses_random(self):
        import inspect

        source = inspect.getsource(credential_reset)
        self.assertIn("secrets.choice", source)
        self.assertNotIn("import random", source)
        self.assertNotIn("random.choice", source)
        self.assertEqual(credential_reset.secrets.__name__, "secrets")

    def test_generator_alphabet_is_unambiguous_and_measures_over_80_bits(self):
        alphabet = credential_reset._TEMP_PW_ALPHABET
        length = credential_reset._TEMP_PW_LENGTH
        symbols = set(alphabet)
        # A duplicated symbol would silently skew the distribution.
        self.assertEqual(len(alphabet), len(symbols))
        # Transcription-safe: none of the shapes a human misreads.
        for ambiguous in "0O1lI":
            self.assertNotIn(ambiguous, alphabet)
        bits = length * math.log2(len(symbols))
        self.assertGreaterEqual(
            bits,
            REQUIRED_GENERATED_BITS,
            f"generated credential measures {bits:.2f} bits, floor is "
            f"{REQUIRED_GENERATED_BITS}",
        )

    def test_generated_credentials_are_distinct_and_span_the_alphabet(self):
        alphabet = set(credential_reset._TEMP_PW_ALPHABET)
        length = credential_reset._TEMP_PW_LENGTH
        sample = [generate_temp_password() for _ in range(500)]
        # A collision in 500 draws from a 1.8e24 space means the generator is
        # not drawing from the space it claims.
        self.assertEqual(len(set(sample)), len(sample))
        observed = set("".join(sample))
        self.assertTrue(observed <= alphabet)
        # A stuck or truncated alphabet would show as a narrow observed set.
        self.assertGreaterEqual(len(observed), 40)
        self.assertEqual({len(p) for p in sample}, {length})

    def test_entropy_measure_separates_a_wordlist_hit_from_a_minted_one(self):
        weak = temp_password_entropy_bits("password")
        minted = temp_password_entropy_bits(generate_temp_password())
        self.assertLess(weak, TEMP_PASSWORD_MIN_BITS)
        self.assertGreaterEqual(minted, TEMP_PASSWORD_MIN_BITS)

    def test_provisioning_refuses_a_dictionary_word(self):
        """Regression seal: "password" provisioned an account until 2026-08-31."""
        school = _mk_school("entropy-word")
        with self.assertRaises(ProvisioningError):
            provision_tenant_user_with_temp_password(
                school=school,
                email=f"{uuid.uuid4().hex[:8]}@example.test",
                role=User.Role.TEACHER,
                temp_password="password",
            )

    def test_provisioning_refuses_a_repeated_character_credential(self):
        school = _mk_school("entropy-repeat")
        for weak in ("aaaaaaaaaaaa", "abababababab"):
            with self.subTest(weak=weak), self.assertRaises(ProvisioningError):
                provision_tenant_user_with_temp_password(
                    school=school,
                    email=f"{uuid.uuid4().hex[:8]}@example.test",
                    role=User.Role.TEACHER,
                    temp_password=weak,
                )

    def test_provisioning_refuses_an_all_numeric_credential(self):
        school = _mk_school("entropy-digits")
        with self.assertRaises(ProvisioningError):
            provision_tenant_user_with_temp_password(
                school=school,
                email=f"{uuid.uuid4().hex[:8]}@example.test",
                role=User.Role.TEACHER,
                temp_password="12345678",
            )

    def test_provisioning_accepts_a_minted_credential(self):
        """The floor must admit the generator, or the fix is unusable."""
        school = _mk_school("entropy-ok")
        temp = generate_temp_password()
        user, created = provision_tenant_user_with_temp_password(
            school=school,
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            role=User.Role.TEACHER,
            temp_password=temp,
        )
        self.assertTrue(created)
        self.assertTrue(user.check_password(temp))

    def test_a_refused_credential_leaves_no_half_provisioned_account(self):
        """A refusal must not land the row -- the guard runs before any write."""
        school = _mk_school("entropy-atomic")
        email = f"{uuid.uuid4().hex[:8]}@example.test"
        with self.assertRaises(ProvisioningError):
            provision_tenant_user_with_temp_password(
                school=school,
                email=email,
                role=User.Role.TEACHER,
                temp_password="password",
            )
        self.assertFalse(User.objects.filter(email__iexact=email).exists())


# --------------------------------------------------------------------------- #
# Property 2 -- STORAGE + LEAKAGE
# --------------------------------------------------------------------------- #
class TempCredentialStorageTests(TestCase):
    """The cleartext must reach the admin's screen and nowhere else."""

    def _assert_hashed_only(self, user, cleartext):
        user.refresh_from_db()
        stored = user.password
        self.assertTrue(user.check_password(cleartext))
        # Salted + algorithm-tagged: Django's format is <algo>$<params>$<salt>$<hash>.
        self.assertGreaterEqual(len(stored.split("$")), 4, stored[:24])
        self.assertNotIn(cleartext, stored)

    def test_provisioned_credential_is_stored_only_as_a_salted_hash(self):
        school = _mk_school("store-prov")
        temp = generate_temp_password()
        user, _ = provision_tenant_user_with_temp_password(
            school=school,
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            role=User.Role.TEACHER,
            temp_password=temp,
        )
        self._assert_hashed_only(user, temp)

    def test_reset_credential_is_stored_only_as_a_salted_hash(self):
        user = _mk_unusable_user()
        temp, _ = set_temporary_password(user)
        self._assert_hashed_only(user, temp)

    def test_the_same_credential_hashes_differently_for_two_users(self):
        """Proves the hash is SALTED -- an unsalted digest would collide."""
        school = _mk_school("store-salt")
        temp = generate_temp_password()
        first, _ = provision_tenant_user_with_temp_password(
            school=school,
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            role=User.Role.TEACHER,
            temp_password=temp,
        )
        second, _ = provision_tenant_user_with_temp_password(
            school=school,
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            role=User.Role.TEACHER,
            temp_password=temp,
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertNotEqual(first.password, second.password)

    def test_no_user_column_holds_the_cleartext(self):
        """The credential must not be stashed on the model beside the hash."""
        user = _mk_unusable_user()
        temp, _ = set_temporary_password(user)
        user.refresh_from_db()
        for field in User._meta.concrete_fields:
            if field.attname == "password":
                continue
            value = getattr(user, field.attname, None)
            if value is None:
                continue
            self.assertNotIn(
                temp,
                str(value),
                f"cleartext temp credential found on User.{field.attname}",
            )

    def test_credential_paths_never_log_the_cleartext(self):
        """The detector proves itself on a planted leak before it is believed."""
        school = _mk_school("store-log")
        staff = _mk_unusable_user(User.Role.TEACHER)
        TeacherProfile.objects.create(user=staff, school=school)

        # 1. Prove the detector fires. A capture that has never caught anything
        #    is not evidence that nothing leaked.
        canary = generate_temp_password()
        with _capture_credential_logs() as planted:
            logging.getLogger("security.account_recovery").warning(
                "planted canary %s", canary
            )
        self.assertIn(canary, planted.blob(), "log-leak detector does not fire")

        # 2. Now run the real minting paths under the same detector.
        with _capture_credential_logs() as captured:
            reset_user = _mk_unusable_user()
            reset_temp, _ = set_temporary_password(reset_user)
            response = handover_csv_response(school=school, kind="staff")
            provisioned_temp = generate_temp_password()
            provision_tenant_user_with_temp_password(
                school=school,
                email=f"{uuid.uuid4().hex[:8]}@example.test",
                role=User.Role.TEACHER,
                temp_password=provisioned_temp,
            )
        blob = captured.blob()
        self.assertTrue(captured.records, "captured no records; detector inert")
        for secret in (reset_temp, provisioned_temp):
            self.assertNotIn(secret, blob)
        for row in response.content.decode().splitlines()[1:]:
            if row:
                self.assertNotIn(row.split(",")[2], blob)

    def test_handover_sheet_is_marked_no_store(self):
        """Regression seal: a cleartext-credential CSV must not be cacheable."""
        school = _mk_school("store-csv")
        staff = _mk_unusable_user(User.Role.TEACHER)
        TeacherProfile.objects.create(user=staff, school=school)
        response = handover_csv_response(school=school, kind="staff")
        cache_control = (response.get("Cache-Control") or "").lower()
        self.assertIn("no-store", cache_control)
        self.assertIn("private", cache_control)
        # HtmlNoCacheMiddleware only stamps text/html, so this response can
        # never inherit the directive -- it has to carry its own.
        self.assertIn("csv", (response.get("Content-Type") or "").lower())

    def test_handover_credential_authenticates_and_is_not_stored_in_clear(self):
        school = _mk_school("store-csvpw")
        staff = _mk_unusable_user(User.Role.TEACHER)
        TeacherProfile.objects.create(user=staff, school=school)
        response = handover_csv_response(school=school, kind="staff")
        rows = [r for r in response.content.decode().splitlines() if r][1:]
        self.assertEqual(len(rows), 1, response.content)
        temp = rows[0].split(",")[2]
        self._assert_hashed_only(staff, temp)


# --------------------------------------------------------------------------- #
# Property 3 -- FORCE-RESET MARKER
# --------------------------------------------------------------------------- #
class ForcedResetMarkerTests(TestCase):
    """Every path that MINTS a temporary credential must force a change."""

    def test_provisioning_marks_a_new_account(self):
        school = _mk_school("flag-new")
        user, created = provision_tenant_user_with_temp_password(
            school=school,
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            role=User.Role.TEACHER,
            temp_password=generate_temp_password(),
        )
        self.assertTrue(created)
        user.refresh_from_db()
        self.assertTrue(user.requires_password_change)
        self.assertFalse(user.profile_setup_completed)

    def test_provisioning_marks_a_reclaimed_unusable_account(self):
        """The ``existing`` branch must set the marker too, not just the new one."""
        school = _mk_school("flag-reclaim")
        existing = _mk_unusable_user(User.Role.TEACHER)
        existing.requires_password_change = False
        existing.profile_setup_completed = True
        existing.save(
            update_fields=["requires_password_change", "profile_setup_completed"]
        )
        user, created = provision_tenant_user_with_temp_password(
            school=school,
            email=existing.email,
            role=User.Role.TEACHER,
            temp_password=generate_temp_password(),
            username=existing.username,
        )
        self.assertFalse(created)
        self.assertEqual(user.pk, existing.pk)
        user.refresh_from_db()
        self.assertTrue(user.requires_password_change)
        self.assertFalse(user.profile_setup_completed)

    def test_set_temporary_password_marks_the_account(self):
        user = _mk_unusable_user()
        self.assertFalse(user.requires_password_change)
        set_temporary_password(user)
        user.refresh_from_db()
        self.assertTrue(user.requires_password_change)

    def test_set_temporary_password_marks_an_inactive_account_it_reactivates(self):
        user = _mk_unusable_user()
        user.is_active = False
        user.save(update_fields=["is_active"])
        _temp, reactivated = set_temporary_password(user)
        user.refresh_from_db()
        self.assertTrue(reactivated)
        self.assertTrue(user.is_active)
        self.assertTrue(user.requires_password_change)

    def test_handover_sheet_marks_every_account_it_issues_for(self):
        """The CSV hardcodes ``must_change_on_first_login=yes`` -- it must be true."""
        school = _mk_school("flag-csv")
        staff = [_mk_unusable_user(User.Role.TEACHER) for _ in range(3)]
        for user in staff:
            TeacherProfile.objects.create(user=user, school=school)
        response = handover_csv_response(school=school, kind="staff")
        rows = [r for r in response.content.decode().splitlines() if r][1:]
        self.assertEqual(len(rows), len(staff))
        for row in rows:
            self.assertEqual(row.split(",")[4], "yes")
        for user in staff:
            user.refresh_from_db()
            self.assertTrue(
                user.requires_password_change,
                f"{user.username} got a temp credential with no forced change",
            )
            self.assertFalse(user.profile_setup_completed)

    def test_every_minting_path_sets_the_marker(self):
        """Table-driven, so a NEW minting path added without the flag shows up."""
        school = _mk_school("flag-table")

        def _via_provisioning():
            user, _ = provision_tenant_user_with_temp_password(
                school=school,
                email=f"{uuid.uuid4().hex[:8]}@example.test",
                role=User.Role.TEACHER,
                temp_password=generate_temp_password(),
            )
            return user

        def _via_reset():
            user = _mk_unusable_user()
            set_temporary_password(user)
            return user

        def _via_handover():
            user = _mk_unusable_user(User.Role.TEACHER)
            TeacherProfile.objects.create(user=user, school=school)
            handover_csv_response(school=school, kind="staff", users=[user])
            return user

        paths = {
            "tenant_user_provisioning.provision_tenant_user_with_temp_password": (
                _via_provisioning
            ),
            "credential_reset.set_temporary_password": _via_reset,
            "people_activation.handover_csv_response": _via_handover,
        }
        unmarked = []
        for name, mint in paths.items():
            user = mint()
            user.refresh_from_db()
            if not user.requires_password_change:
                unmarked.append(name)
        self.assertEqual(
            unmarked, [], f"minting paths with no forced reset: {unmarked}"
        )
