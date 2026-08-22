"""Setup Studio 50X — recommended setup apply."""

from django.test import TestCase

from apps.policies.models import BlueprintPack
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.zero_friction import apply_recommended_setup
from apps.setup_studio.views_zero_friction import api_recommended_setup
from django.contrib.auth import get_user_model
from django.test import RequestFactory


class SetupStudioRecommendedSetupTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Rec School",
            slug="rec-school",
            subdomain="rec-school",
            country_code="CM",
            is_active=True,
        )

    def test_recommended_setup_returns_next_url(self):
        result = apply_recommended_setup(self.school, actor_id=1)
        self.assertTrue(result["ok"])
        self.assertIn("next_url", result)

    def test_recommended_setup_stable(self):
        a = apply_recommended_setup(self.school)
        b = apply_recommended_setup(self.school)
        self.assertEqual(a["next_step_key"], b["next_step_key"])

    def test_recommended_blueprint_slug_is_surfaced(self):
        """Regression: a rankable pack must surface its slug on the launch
        surface. Before the fix ``_rank_blueprints`` emitted only ``pack_slug``
        while ``apply_recommended_setup`` read ``slug``/``key`` — so the
        recommended blueprint slug was always the empty string."""
        BlueprintPack.objects.create(
            slug="cm-secondary-launch",
            name="Cameroon Secondary Launch Baseline",
            category="regional",
            supported_country_scope=["CM"],
            is_active=True,
        )
        # _rank_blueprints ranks every ACTIVE pack, and seed_blueprint_policy_packs
        # ships its own CM-scoped pack ("cameroon-anglophone"). Whether that seed is
        # present depends on what else ran against this --keepdb database, so the
        # assertion below passed alone and failed inside the full bundle. Narrow the
        # field to this test's pack so the outcome depends on the code under test
        # rather than on database history; the assertion itself is unchanged.
        BlueprintPack.objects.exclude(slug="cm-secondary-launch").update(is_active=False)
        result = apply_recommended_setup(self.school, actor_id=1)
        self.assertEqual(
            result["recommended_blueprint_slug"], "cm-secondary-launch"
        )

    def test_form_encoded_fix_automatically_runs_repair(self):
        user = get_user_model().objects.create_user(username="repair-owner")
        request = RequestFactory().post("/api/setup-studio/recommended/", {"auto_fix": "1"})
        request.user = user
        request.school = self.school
        response = api_recommended_setup(request)
        self.assertEqual(response.status_code, 200)
        import json

        payload = json.loads(response.content)
        self.assertIn("auto_repair", payload)
        self.assertIn("needs_human", payload["auto_repair"])

    def test_fix_automatically_survives_consumed_request_stream(self):
        """Regression (prod 500): the 'Fix automatically' form posts multipart
        FormData, so CSRF middleware reads request.POST (to pull the token)
        BEFORE the view runs — consuming the stream. The view then read
        request.body, which raised RawPostDataException (an uncaught 500 on
        /api/setup-studio/recommended/). Simulate that ordering and assert the
        endpoint still repairs and returns 200 instead of crashing."""
        user = get_user_model().objects.create_user(username="repair-owner-stream")
        request = RequestFactory().post(
            "/api/setup-studio/recommended/", {"auto_fix": "1"}
        )
        request.user = user
        request.school = self.school
        # CSRF middleware reads request.POST first — consumes the multipart stream
        # so a later request.body access would raise RawPostDataException.
        _ = request.POST
        response = api_recommended_setup(request)
        self.assertEqual(response.status_code, 200)
        import json

        payload = json.loads(response.content)
        self.assertIn("auto_repair", payload)
        self.assertTrue(payload["auto_repair"]["ok"])
