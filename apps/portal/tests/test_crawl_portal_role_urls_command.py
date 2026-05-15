"""Management command ``crawl_portal_role_urls``: host resolution and operator contract."""

import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"])
@patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
class CrawlPortalRoleUrlsCommandTests(TestCase):
    def test_command_errors_when_host_does_not_resolve_school(self):
        err = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "crawl_portal_role_urls",
                host="unknown-tenant.example.com",
                stderr=err,
                verbosity=0,
            )
        msg = str(ctx.exception)
        self.assertIn("Could not resolve", msg)
        self.assertIn("HTTP_HOST", msg)

    @override_settings(DEBUG=True)
    def test_command_runs_when_school_resolves(self):
        School.objects.create(
            name="Cmd Crawl School",
            slug="cmd-crawl",
            subdomain="cmd-crawl",
            is_active=True,
        )
        out = StringIO()
        err = StringIO()
        smoke_seeds = [
            {
                "url_name": "portal:student_onboarding",
                "roles": (User.Role.STUDENT,),
            }
        ]
        with patch(
            "apps.portal.management.commands.crawl_portal_role_urls.PORTAL_ROLE_SMOKE_SEEDS",
            smoke_seeds,
        ):
            call_command(
                "crawl_portal_role_urls",
                host="cmd-crawl.example.com",
                stdout=out,
                stderr=err,
                verbosity=0,
            )
        combined = out.getvalue() + err.getvalue()
        self.assertIn("Resolved school", combined)
        self.assertIn("Ensured portal smoke prerequisites", combined)
        self.assertIn("0 failure", combined)
