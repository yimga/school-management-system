"""A downloaded export goes WHERE THE OPERATOR IS — resolve that, or the gate is dead.

Follow-up to ``test_export_destination_is_not_the_source.py`` (2026-07-17).

That earlier fix removed the self-comparison (the resolver no longer answered
with the school's OWN region). But it left the resolver with three arms that
have no producer on the real download path:

* ``params['destination_region']`` — the only production caller
  (``siteconfig/views_compliance_exports.py``) builds ``params`` holding nothing
  but ``academic_year_id``;
* ``tenant_runtime.compliance.export_restrictions`` — a config dict that is empty
  by default and that nothing writes a ``destination_region`` into;
* ``request.data_region`` — set NOWHERE in production (only a test assigns it).

So in the real prod shape the resolver still returned ``""`` every time, and the
gate could only ever (a) pass, or (b) — under strict-unknown — blanket-block
EVERYTHING for "unknown region". Neither is a *real cross-border decision*: an
operator in region B downloading a region-A school's PII was never distinguished
from an in-region download.

A downloaded CSV physically lands wherever the person clicking it is. That is the
export's true destination. This suite drives the resolver through the EXACT shape
the real view hands it — an ``HttpRequest`` plus ``params={'academic_year_id': …}``
— and asserts the operator's own location is resolved as the destination, so a
genuinely cross-border download is BLOCKED while a same-region one is allowed.

Against HEAD before the fix, ``resolve_export_destination_region`` returns ``""``
for these requests, so the two "foreign destination" assertions FAIL (the region
is unresolved and, with strict-unknown off, nothing blocks). After the fix they
pass and the same-region case stays green.
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase, override_settings

from apps.compliance.cross_border_export import cross_border_export_blocked
from apps.compliance.export_destination import resolve_export_destination_region
from apps.schools.models import School


@override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=False)
class OperatorLocationIsTheRealExportDestinationTests(TestCase):
    """strict-unknown is OFF: an unresolved destination must NOT block. So any
    block here proves a REAL foreign destination was resolved, not the
    unknown-region blanket."""

    def setUp(self):
        self.rf = RequestFactory()
        # An EU-residency school (regulatory region pinned to eu_central).
        self.school = School.objects.create(
            name="Bonn Gymnasium",
            slug="bonn-gym",
            subdomain="bonn-gym",
            data_region="eu_central",
        )

    def _download_request(self, country_code: str):
        """The EXACT shape the real download view hands the resolver: an
        HttpRequest carrying the operator's edge-resolved country, and params
        holding only ``academic_year_id``."""
        req = self.rf.get(
            "/siteconfig/compliance/exports/waec_wassce_student_summary/download/"
            "?academic_year_id=3"
        )
        # Cloudflare (and most edge proxies) stamp the client country here; no
        # GeoIP DB required. This is the operator's physical location.
        req.META["HTTP_CF_IPCOUNTRY"] = country_code
        return req

    def _resolve_prod_shape(self, request):
        # Mirrors apps/reports/compliance_exports.py:378 exactly.
        return resolve_export_destination_region(
            request=request, params={"academic_year_id": 3}
        )

    def test_a_foreign_operator_yields_a_real_foreign_destination(self):
        dest = self._resolve_prod_shape(self._download_request("US"))
        self.assertEqual(
            dest,
            "us_east",
            "the download goes to the US operator's machine; the resolver must "
            "report us_east, not '' (HEAD returns '' — no producer for the "
            "operator's location on the real download path)",
        )

    def test_a_foreign_operator_download_is_blocked_under_enforcement(self):
        dest = self._resolve_prod_shape(self._download_request("US"))
        blocked, message = cross_border_export_blocked(
            self.school, destination_region=dest or None
        )
        self.assertTrue(
            blocked,
            "an EU school's student PII downloaded to a US operator crosses a "
            "forbidden border and must be blocked once residency is enforced",
        )
        self.assertIn("does not match", message)

    def test_an_in_region_operator_download_is_allowed(self):
        dest = self._resolve_prod_shape(self._download_request("DE"))
        self.assertEqual(dest, "eu_central")
        blocked, _ = cross_border_export_blocked(
            self.school, destination_region=dest or None
        )
        self.assertFalse(
            blocked,
            "a same-region (DE→eu_central) download must still work — the fix "
            "must not block in-region exports",
        )

    def test_an_operator_with_no_edge_country_stays_unknown(self):
        """No country signal at all → '' (unknown), and with strict-unknown off
        the gate does NOT block. Honest: an unknown destination stays unknown."""
        req = self.rf.get("/siteconfig/compliance/exports/x/download/")
        dest = self._resolve_prod_shape(req)
        self.assertEqual(dest, "")
        blocked, _ = cross_border_export_blocked(
            self.school, destination_region=dest or None
        )
        self.assertFalse(blocked)


@override_settings(DATA_RESIDENCY_ENFORCE=False)
class OperatorRegionResolutionDoesNotBlockWhenResidencyIsOffTests(TestCase):
    """Production today runs with the flag OFF. Resolving the operator's region
    must not, by itself, start blocking live exports."""

    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Off High", slug="off-high2", subdomain="off-high2",
            data_region="eu_central",
        )

    def test_foreign_operator_is_not_blocked_while_enforcement_off(self):
        req = self.rf.get("/x/?academic_year_id=3")
        req.META["HTTP_CF_IPCOUNTRY"] = "US"
        dest = resolve_export_destination_region(
            request=req, params={"academic_year_id": 3}
        )
        blocked, _ = cross_border_export_blocked(
            self.school, destination_region=dest or None
        )
        self.assertFalse(
            blocked,
            "with DATA_RESIDENCY_ENFORCE off the gate stays a no-op regardless "
            "of a resolved foreign destination",
        )
