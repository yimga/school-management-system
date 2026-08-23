"""The Studio activity feed must not name another tenant's package installs.

``studio_os`` is mounted at ``studio/`` in the TENANT url graph, and ``packages``
is a SHARED app — ``packages_installedpackage`` is one public-schema table
holding every school's rows under both tenancy modes. So an unfiltered
``InstalledPackage`` queryset in the feed shows School A's admin what School B
installed, plus the id of the user who installed it.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.packages.models import InstalledPackage
from apps.schools.models import School
from apps.studio_os.services import get_studio_activity_feed

User = get_user_model()


class StudioActivityFeedTenantIsolationTests(TestCase):
    def setUp(self):
        # Distinct subdomains: School.subdomain is unique and blank counts as a value.
        self.school_a = School.objects.create(
            name="Feed School A", slug="feed-school-a", subdomain="feed-school-a"
        )
        self.school_b = School.objects.create(
            name="Feed School B", slug="feed-school-b", subdomain="feed-school-b"
        )
        self.user = User.objects.create_user(
            username="feed-admin", email="feed-admin@example.com", password="x"
        )
        self.own_pkg = InstalledPackage.objects.create(
            package_id="doc-pack:own-package",
            version="1.0.0",
            school=self.school_a,
            is_active=True,
        )
        self.other_pkg = InstalledPackage.objects.create(
            package_id="doc-pack:board-disciplinary-minutes",
            version="1.0.0",
            school=self.school_b,
            is_active=True,
        )

    def tearDown(self):
        set_urlconf(None)

    def _request_for(self, school):
        from django.contrib.sessions.backends.signed_cookies import SessionStore

        request = RequestFactory().get("/studio/experience/")
        request.session = SessionStore()
        request.user = self.user
        request.school = school
        request.tenant = school
        # The feed reverses studio_os URLs; without the tenant graph every entry
        # is dropped and any "not present" assertion would pass vacuously.
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        return request

    def test_feed_hides_other_tenants_package_installs(self):
        feed = get_studio_activity_feed(self._request_for(self.school_a))
        labels = [row["label"] for row in feed if row.get("kind") == "package_apply"]

        # Guard: the feed really reached the package branch for THIS tenant.
        self.assertIn(f"Package {self.own_pkg.package_id}@1.0.0 applied", labels)
        self.assertNotIn(
            f"Package {self.other_pkg.package_id}@1.0.0 applied",
            labels,
            "Studio activity feed leaked another tenant's package install",
        )
