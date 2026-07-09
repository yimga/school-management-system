"""Guardian consent / visibility / contact-preference carry on transfer.

Fast, DB-free guards on the two subtlest hops of the carry (2026-07-09
follow-up to the merge/split completeness fix b69fb559d):

  1. The RunMyCampus canonical accelerator must IDENTITY-MAP every flag
     column — a header outside the canonical set is shunted to
     ``custom_fields`` and never reaches the guardian lander, so the target
     would silently reset the flag to the model default.
  2. The boolean encode/decode must round-trip an explicit ``False`` — an
     empty string would be dropped by the exporter's ``_drop_empty`` and the
     flag would reset to its default at the destination.

The full export -> CSV -> accelerator -> mapper -> lander round-trip is proven
end-to-end (with non-default source values) in
``apps/people/tests/test_transfer_real_apply.py::test_real_apply_end_to_end``.
"""
from django.test import SimpleTestCase

from apps.interop.student_transfer_export import _bool_str
from apps.migration_cloud.accelerators.runmycampus_canonical import (
    DOMAIN_CANONICAL_HEADERS,
)
from apps.migration_cloud.landers.guardian_lander import _truthy

# The consent / visibility / contact-preference fields carried on transfer.
# One source of truth so the exporter, the accelerator whitelist, and the
# lander stay in lockstep — a field added to the carry but not the accelerator
# set would be silently dropped between them.
CARRIED_GUARDIAN_FLAG_FIELDS = (
    "receives_email",
    "receives_sms",
    "receives_whatsapp",
    "can_view_results",
    "can_view_finance",
    "preferred_contact",
    "whatsapp_number",
    "address",
)


class GuardianCarryHeaderContractTest(SimpleTestCase):
    def test_accelerator_identity_maps_every_carried_flag(self):
        guardians = DOMAIN_CANONICAL_HEADERS["guardians"]
        missing = [f for f in CARRIED_GUARDIAN_FLAG_FIELDS if f not in guardians]
        self.assertEqual(
            missing, [], f"not identity-mapped (would drop to custom_fields): {missing}"
        )

    def test_every_carried_flag_is_a_real_model_field(self):
        # Ties the whitelist to the model: a future rename/removal fires here
        # instead of silently no-op'ing the carry. Metadata only — no DB query.
        from apps.people.models import StudentGuardian

        model_fields = {f.name for f in StudentGuardian._meta.get_fields()}
        missing = [f for f in CARRIED_GUARDIAN_FLAG_FIELDS if f not in model_fields]
        self.assertEqual(missing, [], f"not on StudentGuardian: {missing}")


class BooleanRoundTripTest(SimpleTestCase):
    def test_bool_str_encodes_explicit_false_not_empty(self):
        # False MUST encode as a non-empty token so _drop_empty keeps the
        # column (an empty string is dropped -> reset to default at target).
        self.assertEqual(_bool_str(True), "true")
        self.assertEqual(_bool_str(False), "false")
        self.assertNotEqual(_bool_str(False), "")

    def test_truthy_decodes_both_ways(self):
        self.assertIs(_truthy("true"), True)
        self.assertIs(_truthy("false"), False)
        self.assertIs(_truthy(""), False)
        self.assertIs(_truthy(None), False)

    def test_encode_decode_is_lossless(self):
        for value in (True, False):
            self.assertIs(_truthy(_bool_str(value)), value)
