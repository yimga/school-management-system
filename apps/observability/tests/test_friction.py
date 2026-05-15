"""Wave B — G5: friction telemetry tests."""

from __future__ import annotations

import json
import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.observability.models_friction import FRICTION_KIND_CODES, FrictionEvent
from apps.observability.views_friction import ingest_friction_event
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig

User = get_user_model()
_HOST = "friction.runmycampus.com"


def _make_school(plan, region):
    slug = f"friction-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"Friction School {slug}",
        slug=slug,
        subdomain=slug,
        is_active=True,
        plan=plan,
        default_region=region,
        settings={},
    )


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST])
class FrictionEndpointTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Fr", slug="fr", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="FR", name="Frland", timezone="UTC", default_currency="USD")

    def setUp(self):
        FrictionEvent.objects.all().delete()
        self.school = _make_school(self.plan, self.region)
        self.user = User.objects.create_user(username=f"u-{uuid.uuid4().hex[:6]}", password="pw")
        self.factory = RequestFactory()

    def _post(self, body):
        request = self.factory.post(
            "/api/observability/friction/",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        return ingest_friction_event(request)

    def test_known_kinds_match_choices(self):
        # Hardcoded list shouldn't drift away from the model choices.
        for code in ("validation_retry", "form_abandon", "dwell_excess", "repeat_error"):
            self.assertIn(code, FRICTION_KIND_CODES)

    def test_creates_row_on_first_event(self):
        resp = self._post({"view_name": "portal:grades.entry", "kind": "validation_retry"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(FrictionEvent.objects.count(), 1)
        row = FrictionEvent.objects.get()
        self.assertEqual(row.count, 1)
        self.assertEqual(row.view_name, "portal:grades.entry")
        self.assertEqual(row.user, self.user)
        self.assertEqual(row.school, self.school)

    def test_increments_existing_row_same_day(self):
        self._post({"view_name": "portal:grades.entry", "kind": "validation_retry"})
        self._post({"view_name": "portal:grades.entry", "kind": "validation_retry"})
        self._post({"view_name": "portal:grades.entry", "kind": "validation_retry"})
        self.assertEqual(FrictionEvent.objects.count(), 1)
        row = FrictionEvent.objects.get()
        self.assertEqual(row.count, 3)

    def test_rejects_invalid_kind(self):
        resp = self._post({"view_name": "x", "kind": "BOGUS"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(FrictionEvent.objects.count(), 0)

    def test_rejects_blank_view_name(self):
        resp = self._post({"view_name": "  ", "kind": "validation_retry"})
        self.assertEqual(resp.status_code, 400)

    def test_rejects_malformed_json(self):
        request = self.factory.post(
            "/api/observability/friction/",
            data=b"not-json",
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        resp = ingest_friction_event(request)
        self.assertEqual(resp.status_code, 400)

    def test_payload_too_large_is_truncated(self):
        big = {f"k{i}": "x" * 200 for i in range(50)}  # ~10KB
        self._post({"view_name": "x", "kind": "validation_retry", "payload": big})
        row = FrictionEvent.objects.get()
        # Body either stored as-is (under threshold) or truncated to key markers.
        self.assertTrue(len(json.dumps(row.last_payload)) <= 4096 or
                        all(v == "<truncated>" for v in row.last_payload.values()))

    def test_anonymous_no_school_returns_200_without_writing(self):
        request = self.factory.post(
            "/api/observability/friction/",
            data=json.dumps({"view_name": "marketing:home", "kind": "form_abandon"}),
            content_type="application/json",
        )
        # No user, no school
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        # No request.school
        resp = ingest_friction_event(request)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FrictionEvent.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class FrictionDigestTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Dg", slug="dg", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="DG", name="Dgland", timezone="UTC", default_currency="USD")

    def setUp(self):
        FrictionEvent.objects.all().delete()
        self.school = _make_school(self.plan, self.region)
        self.user = User.objects.create_user(username=f"u-{uuid.uuid4().hex[:6]}", password="pw")

    def _create_friction(self, count: int):
        return FrictionEvent.objects.create(
            user=self.user,
            school=self.school,
            view_name="portal:grades.entry",
            kind="validation_retry",
            utc_day=timezone.now().date(),
            count=count,
        )

    def test_digest_skips_below_threshold(self):
        self._create_friction(count=2)
        out = StringIO()
        call_command("digest_friction", "--threshold", "5", "--dry-run", stdout=out)
        self.assertIn("No friction events above threshold", out.getvalue())

    def test_digest_dry_run_outputs_warm_copy(self):
        self._create_friction(count=7)
        out = StringIO()
        call_command("digest_friction", "--threshold", "3", "--dry-run", "--no-ai", stdout=out)
        body = out.getvalue()
        self.assertIn("Friction digest for", body)
        self.assertIn("getting stuck", body)
        self.assertIn("nudge to review", body)
        self.assertIn("Nothing requires immediate action", body)

    def test_digest_prepends_empathy_narrative_when_ai_available(self):
        from unittest import mock

        self._create_friction(count=7)
        out = StringIO()
        with mock.patch(
            "apps.observability.management.commands.digest_friction.Command._invoke_empathy_narrative",
            return_value="Hi — we noticed teachers retried the gradebook form a few times today.",
        ):
            call_command("digest_friction", "--threshold", "3", "--dry-run", stdout=out)
        body = out.getvalue()
        # AI summary appears BEFORE the template body.
        self.assertIn("we noticed teachers retried", body)
        ai_pos = body.find("we noticed teachers retried")
        tmpl_pos = body.find("Friction digest for")
        self.assertLess(ai_pos, tmpl_pos)

    def test_digest_no_ai_flag_skips_narrative(self):
        from unittest import mock

        self._create_friction(count=7)
        out = StringIO()
        with mock.patch(
            "apps.observability.management.commands.digest_friction.Command._invoke_empathy_narrative",
        ) as patched:
            call_command("digest_friction", "--threshold", "3", "--dry-run", "--no-ai", stdout=out)
        patched.assert_not_called()

    def test_digest_falls_back_silently_when_ai_returns_none(self):
        from unittest import mock

        self._create_friction(count=7)
        out = StringIO()
        with mock.patch(
            "apps.observability.management.commands.digest_friction.Command._invoke_empathy_narrative",
            return_value=None,
        ):
            call_command("digest_friction", "--threshold", "3", "--dry-run", stdout=out)
        body = out.getvalue()
        self.assertIn("Friction digest for", body)
        # No prepended AI prose — template body sits at the top of the rendered output.
        marker_index = body.find("─")  # the divider the dry-run loop emits
        first_block = body[marker_index:marker_index + 200] if marker_index >= 0 else body
        self.assertIn("Friction digest for", first_block)
