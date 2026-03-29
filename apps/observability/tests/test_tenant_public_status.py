from django.core.cache import cache
from django.test import TestCase

from apps.accounts.models import User
from apps.observability.models import PlatformIncident
from apps.observability.tenant_public_status import compute_platform_status_strip_bundle
from apps.schools.models import School


class TenantPublicStatusStripTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Status Strip School",
            slug="status-strip-school",
            subdomain="status-strip-school",
            is_active=True,
        )
        self.user = User.objects.create_user(username="strip-user", password="pass")

    def tearDown(self):
        cache.clear()

    def test_fleet_availability_sets_generic_without_tenant_titles(self):
        PlatformIncident.objects.create(
            title="Internal operator title",
            incident_type=PlatformIncident.IncidentType.AVAILABILITY,
            severity=PlatformIncident.Severity.HIGH,
            status=PlatformIncident.Status.OPEN,
            summary="Details stay in operator console.",
            affected_school=None,
        )
        bundle = compute_platform_status_strip_bundle(self.school.pk)
        self.assertTrue(bundle["show"])
        self.assertTrue(bundle["fleet_generic"])
        self.assertEqual(bundle["tenant_items"], [])

    def test_school_scoped_includes_titles_for_that_tenant_only(self):
        PlatformIncident.objects.create(
            title="Your integration delay",
            incident_type=PlatformIncident.IncidentType.INTEGRATION,
            severity=PlatformIncident.Severity.MEDIUM,
            status=PlatformIncident.Status.ACKNOWLEDGED,
            summary="Scoped to tenant.",
            affected_school=self.school,
        )
        bundle = compute_platform_status_strip_bundle(self.school.pk)
        self.assertTrue(bundle["show"])
        self.assertFalse(bundle["fleet_generic"])
        self.assertEqual(len(bundle["tenant_items"]), 1)
        self.assertEqual(bundle["tenant_items"][0]["title"], "Your integration delay")

    def test_resolved_incidents_hidden(self):
        PlatformIncident.objects.create(
            title="Old news",
            incident_type=PlatformIncident.IncidentType.AVAILABILITY,
            severity=PlatformIncident.Severity.LOW,
            status=PlatformIncident.Status.RESOLVED,
            summary="Done.",
            affected_school=None,
        )
        bundle = compute_platform_status_strip_bundle(self.school.pk)
        self.assertFalse(bundle["show"])

    def test_new_incident_invalidates_cached_empty_bundle(self):
        """post_save bumps cache generation so we do not wait TTL after incident create."""
        b0 = compute_platform_status_strip_bundle(self.school.pk)
        self.assertFalse(b0["show"])
        PlatformIncident.objects.create(
            title="Live outage",
            incident_type=PlatformIncident.IncidentType.AVAILABILITY,
            severity=PlatformIncident.Severity.HIGH,
            status=PlatformIncident.Status.OPEN,
            summary="Users may see errors.",
            affected_school=None,
        )
        b1 = compute_platform_status_strip_bundle(self.school.pk)
        self.assertTrue(b1["show"])
        self.assertTrue(b1["fleet_generic"])
