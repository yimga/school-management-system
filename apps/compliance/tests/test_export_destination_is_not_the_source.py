"""A cross-border gate must not compare the region to itself.

Found by an A-Z audit follow-up (2026-07-16/17).

``resolve_export_destination_region`` ended with::

    if school is not None:
        school_region = getattr(school, "data_region", None)
        if school_region:
            return str(school_region).strip().lower()
    return ""

...so when no destination was supplied it answered with the SOURCE region. The
only production caller (``siteconfig/views_compliance_exports.py:156``) builds
``params`` that holds nothing but ``academic_year_id``, and passes
``request.user`` -- while the resolver looks for ``user._request``, which
nothing in the codebase ever sets. So ``request`` is None, ``params`` carries no
destination, and the fallback fires every time:

    cross_border_export_blocked(school, destination_region=school.data_region)
      -> school_region == dest -> not blocked. Always.

The gate compared the school's region to itself, so it could never block. The
view had the real ``request`` in scope and passed ``request.user`` instead.

The fabricated fallback destroyed a SECOND guard as well. The predicate opens
with::

    if not dest or not school_region:
        if strict_unknown_regions(): return (True, "... region unknown ...")

That branch exists precisely for a destination that cannot be known -- but
``dest`` was never empty, so it was unreachable too.

WHAT THIS IS AND IS NOT: today the gate is OFF in production
(``DATA_RESIDENCY_ENFORCE`` is unset in render.yaml, so the predicate returns
False on its first line), so this is not a live leak. It is worse in a specific
way: an operator who flips ``DATA_RESIDENCY_ENFORCE=1`` -- and attests to a
regulator that cross-border exports are now blocked -- gets NOTHING. A
compliance control that reports enforcement while enforcing nothing invites the
attestation, which is the actual harm.

FIX: the resolver reports an UNKNOWN destination as unknown (""), never as "the
same place the data already is". Deciding what to do about an unknown
destination belongs to the gate (``strict_unknown_regions``), which already has
that branch and defaults to the backward-compatible posture.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.compliance.cross_border_export import cross_border_export_blocked
from apps.compliance.export_destination import resolve_export_destination_region
from apps.schools.models import School


class _Req:
    """A request with no region pinned -- the shape the export view has."""


class DestinationIsNeverFabricatedFromTheSourceTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(
            name="Region High", slug="region-high", subdomain="region-high",
            data_region="eu",
        )

    def test_an_unknown_destination_resolves_to_unknown(self):
        self.assertEqual(
            resolve_export_destination_region(request=None, params={}),
            "",
            "the resolver answered with the school's OWN region, so every "
            "cross-border check compares the region to itself and can never "
            "block",
        )

    def test_the_academic_year_params_the_real_view_sends_change_nothing(self):
        """The exact params the only production caller builds."""
        self.assertEqual(
            resolve_export_destination_region(request=None, params={"academic_year_id": 3}),
            "",
        )

    def test_an_explicit_destination_still_wins(self):
        self.assertEqual(
            resolve_export_destination_region(request=None, params={"destination_region": "US"}),
            "us",
        )

    def test_a_region_pinned_request_still_wins(self):
        req = _Req()
        req.data_region = "AF"
        self.assertEqual(
            resolve_export_destination_region(request=req, params={}),
            "af",
        )


@override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=True)
class TheGateCanActuallyBlockOnceEnforcedTests(TestCase):
    """Flipping the flag must actually enforce something."""

    def setUp(self):
        self.school = School.objects.create(
            name="Strict High", slug="strict-high", subdomain="strict-high",
            data_region="eu",
        )

    def test_an_unknown_destination_is_blocked_under_strict_enforcement(self):
        dest = resolve_export_destination_region(request=None, params={})
        blocked, message = cross_border_export_blocked(
            self.school, destination_region=dest or None
        )
        self.assertTrue(
            blocked,
            "with residency enforced AND strict-unknown on, an export whose "
            "destination cannot be resolved must not proceed -- this is the "
            "branch the self-comparison made unreachable",
        )
        self.assertIn("unknown", message.lower())

    def test_a_foreign_destination_is_blocked(self):
        blocked, message = cross_border_export_blocked(
            self.school, destination_region="us"
        )
        self.assertTrue(blocked)
        self.assertIn("does not match", message)

    def test_an_in_region_destination_is_allowed(self):
        blocked, _ = cross_border_export_blocked(
            self.school, destination_region="eu"
        )
        self.assertFalse(blocked, "an in-region export must still work")


@override_settings(DATA_RESIDENCY_ENFORCE=False)
class TheDefaultPostureIsUnchangedTests(TestCase):
    """Production today has the flag off. Nothing may change there."""

    def test_nothing_is_blocked_while_residency_enforcement_is_off(self):
        school = School.objects.create(
            name="Off High", slug="off-high", subdomain="off-high",
            data_region="eu",
        )
        dest = resolve_export_destination_region(request=None, params={})
        blocked, _ = cross_border_export_blocked(
            school, destination_region=dest or None
        )
        self.assertFalse(
            blocked,
            "with DATA_RESIDENCY_ENFORCE off the gate must stay a no-op -- "
            "this change must not start blocking live exports",
        )
