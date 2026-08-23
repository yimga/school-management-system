"""The operator regional mask must cover all EU member states, not 6 of them.

``apply_regional_mask`` normalised to "EU" from a hardcoded 6-country tuple
('DE','FR','IT','ES','NL','PL'), so ``_REGIONAL_MASK_FIELDS.get(region, frozenset())``
returned an EMPTY set for Ireland, Sweden, Belgium, Austria and the rest — every
person field passed through in the clear. The correct membership set already
lived in the same app in ``tenant_mask_wiring._EU_MEMBER_COUNTRIES``; the two
lists had drifted apart.

``compose_operator_view`` and ``mask_dict_for_school`` both funnel through
``apply_regional_mask``, so both surfaces inherit the gap.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase, TestCase

from apps.platform_runtime.jit_operator_controller import (
    apply_regional_mask,
    compose_operator_view,
)
from apps.platform_runtime.tenant_mask_wiring import (
    _EU_MEMBER_COUNTRIES,
    mask_dict_for_school,
)
from apps.schools.models import School

# Member states the old 6-country tuple silently excluded.
_PREVIOUSLY_UNMASKED = (
    "IE", "SE", "BE", "AT", "PT", "DK", "FI", "GR", "CZ", "RO",
    "HU", "BG", "HR", "CY", "EE", "LV", "LT", "LU", "MT", "SK", "SI",
)


class RegionalMaskEuMembershipTests(SimpleTestCase):
    def test_every_eu_member_state_masks_person_fields(self):
        for code in _PREVIOUSLY_UNMASKED:
            with self.subTest(country=code):
                out = apply_regional_mask(
                    {
                        "full_name": "Aoife Byrne",
                        "phone": "+353 1 555 0100",
                        "email": "aoife@example.ie",
                        "grade": "A",
                    },
                    region=code,
                )
                self.assertNotIn("Aoife", out["full_name"], f"{code} leaked the name")
                self.assertNotIn("353", out["phone"], f"{code} leaked the phone")
                self.assertNotIn("aoife", out["email"], f"{code} leaked the email")
                # Vacuity guard: the mask must stay selective. A blanket redaction
                # of every value would satisfy the three asserts above.
                self.assertEqual(out["grade"], "A")

    def test_membership_list_is_the_single_shared_set(self):
        """Regression on the drift itself, not only on its symptom."""
        for code in _EU_MEMBER_COUNTRIES:
            with self.subTest(country=code):
                out = apply_regional_mask({"full_name": "Aoife Byrne"}, region=code)
                self.assertNotIn("Aoife", out["full_name"])

    def test_non_eu_non_us_country_is_untouched(self):
        """Vacuity guard: the fix must not mask the whole world."""
        out = apply_regional_mask({"full_name": "Ada Nkeng"}, region="CM")
        self.assertEqual(out["full_name"], "Ada Nkeng")

    def test_compose_operator_view_masks_for_an_irish_tenant(self):
        """The composition an operator surface actually calls."""
        expires = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
        settings_dict = {
            "operator_access": {
                "jit_grants": [
                    {
                        "operator_user_id": 4242,
                        "expires_at_iso": expires,
                        "reason": "support ticket 42",
                    }
                ]
            }
        }
        grant, visible = compose_operator_view(
            operator_user_id=4242,
            school_settings=settings_dict,
            region="IE",
            record={"full_name": "Aoife Byrne", "phone": "+353 1 555 0100", "class_size": 30},
        )
        # Vacuity guard: without a live grant `visible` is {} and every
        # "no PII present" assertion below would pass for the wrong reason.
        self.assertTrue(grant.granted, f"JIT grant refused: {grant.reason}")
        self.assertEqual(visible["class_size"], 30, "the record actually reached the mask")
        self.assertNotIn("Aoife", visible["full_name"])
        self.assertNotIn("353", visible["phone"])


class TenantMaskWiringEuMembershipTests(TestCase):
    """``mask_dict_for_school`` derives "EU" for IE but then hit the 6-country tuple."""

    def test_irish_school_masks_person_record(self):
        school = School.objects.create(
            name="Dublin Academy",
            slug="dublin-academy",
            subdomain="dublin-academy",
            country_code="IE",
        )
        out = mask_dict_for_school(
            {"first_name": "Aoife", "last_name": "Byrne", "year_group": "5"}, school
        )
        self.assertEqual(out["year_group"], "5", "non-PII passes through")
        self.assertNotIn("Aoife", out["first_name"])
        self.assertNotIn("Byrne", out["last_name"])
