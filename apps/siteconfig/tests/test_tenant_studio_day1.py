"""Tests for the tenant School Studio Day-1 Magic service + views.

Most of the service is pure logic on a ``School``-like duck — we stub a
lightweight ``FakeSchool`` for those paths to keep the test boot fast and
independent of the migration graph. The view-layer tests use real Django
plumbing through ``RequestFactory``.
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.siteconfig.tenant_studio_day1 import (
    Day1MagicService,
    PALETTE_TONES,
    PaletteVariation,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSchool:
    """Minimal duck-typed stand-in for ``apps.schools.models.School``."""

    def __init__(
        self,
        *,
        pk: str = "school-pk-1",
        slug: str = "ghs-limbe",
        name: str = "Gilead Tech High",
        logo_url: str = "",
        primary_color: str = "#0d6efd",
        branding_metadata: dict | None = None,
        settings: dict | None = None,
    ) -> None:
        self.pk = pk
        self.slug = slug
        self.name = name
        self.logo_url = logo_url
        self.primary_color = primary_color
        self.branding_metadata = dict(branding_metadata or {})
        self.settings = dict(settings or {})
        self.save_calls: list[dict] = []

    def save(self, update_fields=None):  # noqa: D401 - django save mimic
        self.save_calls.append({"update_fields": tuple(update_fields or ())})


class FakeUser:
    def __init__(self, *, pk=42, is_staff=False, is_superuser=False, role="ADMIN"):
        self.pk = pk
        self.is_authenticated = True
        self.is_staff = is_staff
        self.is_superuser = is_superuser
        self.role = role


# ---------------------------------------------------------------------------
# is_day1_required
# ---------------------------------------------------------------------------


class IsDay1RequiredTests(SimpleTestCase):
    def test_fresh_tenant_requires_day1(self):
        school = FakeSchool()
        self.assertTrue(Day1MagicService.is_day1_required(school))

    def test_locked_tenant_skips_day1(self):
        school = FakeSchool(branding_metadata={"palette_locked_at": "2026-05-20T12:00:00Z"})
        self.assertFalse(Day1MagicService.is_day1_required(school))

    def test_explicitly_skipped_tenant_skips_day1(self):
        school = FakeSchool(settings={"day1_skipped": True})
        self.assertFalse(Day1MagicService.is_day1_required(school))

    def test_none_school_returns_false(self):
        self.assertFalse(Day1MagicService.is_day1_required(None))


# ---------------------------------------------------------------------------
# resolve_brand_seed
# ---------------------------------------------------------------------------


class ResolveBrandSeedTests(SimpleTestCase):
    def test_no_logo_no_color_falls_back(self):
        school = FakeSchool()
        seed = Day1MagicService.resolve_brand_seed(school)
        self.assertEqual(seed["source"], "fallback")
        self.assertEqual(seed["seed_hex"].lower(), "#4f46e5")

    def test_primary_color_when_no_logo(self):
        school = FakeSchool(primary_color="#FF6600")
        seed = Day1MagicService.resolve_brand_seed(school)
        self.assertEqual(seed["source"], "primary_color")
        self.assertEqual(seed["seed_hex"], "#ff6600")

    def test_default_primary_color_is_treated_as_fallback(self):
        """A school still on the default ``#0d6efd`` is treated as having no seed."""
        school = FakeSchool(primary_color="#0d6efd")
        seed = Day1MagicService.resolve_brand_seed(school)
        self.assertEqual(seed["source"], "fallback")

    def test_logo_dispatches_to_theme_intelligence(self):
        school = FakeSchool(logo_url="https://example.test/logo.png")
        fake_module = mock.MagicMock()
        fake_module.extract_dominant_colors_from_image.return_value = "#abcdef"
        with mock.patch.dict(
            "sys.modules", {"services.theme_intelligence": fake_module}
        ):
            seed = Day1MagicService.resolve_brand_seed(school)
        self.assertEqual(seed["source"], "logo")
        self.assertEqual(seed["seed_hex"], "#abcdef")

    def test_logo_with_missing_theme_intelligence_falls_back(self):
        """ImportError on services.theme_intelligence must not crash."""
        school = FakeSchool(logo_url="https://example.test/logo.png", primary_color="#00ff00")
        # Force ImportError by ensuring the module is absent from sys.modules
        # AND patching the import machinery to raise.
        with mock.patch("builtins.__import__", side_effect=_raise_for_target("services.theme_intelligence")):
            seed = Day1MagicService.resolve_brand_seed(school)
        # Should NOT crash; should fall through to primary_color.
        self.assertEqual(seed["source"], "primary_color")
        self.assertEqual(seed["seed_hex"], "#00ff00")


def _raise_for_target(target: str):
    real_import = __import__

    def _imp(name, *args, **kwargs):
        if name == target:
            raise ImportError(target)
        return real_import(name, *args, **kwargs)

    return _imp


# ---------------------------------------------------------------------------
# generate_variations
# ---------------------------------------------------------------------------


class GenerateVariationsTests(SimpleTestCase):
    def test_returns_exactly_three_variations(self):
        school = FakeSchool()
        variations = Day1MagicService.generate_variations(school)
        self.assertEqual(len(variations), 3)

    def test_variation_tones_are_unique_and_canonical(self):
        school = FakeSchool()
        variations = Day1MagicService.generate_variations(school)
        tones = [v.tone for v in variations]
        self.assertEqual(tones, list(PALETTE_TONES))
        self.assertEqual(len(set(tones)), 3)

    def test_each_variation_has_stops_and_preview_targets(self):
        school = FakeSchool()
        for v in Day1MagicService.generate_variations(school):
            self.assertIsInstance(v, PaletteVariation)
            self.assertIn("primary", v.stops)
            self.assertIn("surface", v.stops)
            self.assertIn("ink", v.stops)
            self.assertIn("portal_tile", v.preview_targets)

    def test_ai_unreachable_returns_rules_fallback(self):
        """With ai_palette missing, all three variations still appear."""
        school = FakeSchool(primary_color="#114488")
        with mock.patch("builtins.__import__", side_effect=_raise_for_target("services.ai_palette")):
            variations = Day1MagicService.generate_variations(school)
        self.assertEqual(len(variations), 3)
        # And each id is stable across re-runs (deterministic).
        again = Day1MagicService.generate_variations(school)
        with mock.patch("builtins.__import__", side_effect=_raise_for_target("services.ai_palette")):
            again = Day1MagicService.generate_variations(school)
        self.assertEqual([v.id for v in variations], [v.id for v in again])

    def test_day1_act2_passes_tone_to_ai_palette(self):
        """Day-1 calls ai_palette.generate_palette_from_seed with the correct tone per variation.

        Replaces the v3.39 tone->mode coerce hack: each of the three
        variations must reach the AI with its real tone string, so the
        cloud tier can produce genuinely distinct hue biases.
        """
        school = FakeSchool(primary_color="#114488")

        captured_tones: list[str] = []

        def _fake_generate(seed_hex, *args, **kwargs):
            tone = kwargs.get("tone")
            if tone is not None:
                captured_tones.append(str(tone))

            class _Stub:
                stops = {
                    "500": "#114488",
                    "600": "#0d3366",
                    "200": "#aac4ff",
                    "50": "#f7faff",
                    "900": "#06112b",
                }
                surface_chain = {"bg": "#ffffff"}
                text_chain = {"primary": "#06112b"}
                accent_hex = "#114488"

            return _Stub()

        fake_module = mock.MagicMock()
        fake_module.generate_palette_from_seed = _fake_generate
        with mock.patch.dict(
            "sys.modules", {"services.ai_palette": fake_module}
        ):
            variations = Day1MagicService.generate_variations(school)
        self.assertEqual(len(variations), 3)
        # Each tone was passed in distinctly, in canonical order.
        self.assertEqual(captured_tones, list(PALETTE_TONES))


# ---------------------------------------------------------------------------
# lock_palette_choice
# ---------------------------------------------------------------------------


class LockPaletteChoiceTests(TestCase):
    # Uses TestCase because Day1MagicService.lock_palette_choice wraps the
    # mutation in transaction.atomic(); SimpleTestCase forbids the BEGIN.
    def test_lock_persists_palette_and_locked_at(self):
        school = FakeSchool(primary_color="#114488")
        variations = Day1MagicService.generate_variations(school)
        chosen = variations[1]

        with mock.patch("apps.siteconfig.tenant_studio_day1._mirror_to_site_settings"):
            Day1MagicService.lock_palette_choice(school, chosen.id, by_user=FakeUser())

        self.assertIn("palette_locked_at", school.branding_metadata)
        self.assertEqual(school.branding_metadata["palette_locked_tone"], chosen.tone)
        self.assertEqual(school.branding_metadata["palette_locked_variation_id"], chosen.id)
        self.assertEqual(school.branding_metadata["primary"], chosen.stops["primary"])
        # ``save`` was called with update_fields including branding_metadata.
        self.assertTrue(school.save_calls)
        self.assertIn("branding_metadata", school.save_calls[0]["update_fields"])

    def test_lock_with_unknown_variation_id_raises(self):
        school = FakeSchool()
        with self.assertRaises(ValueError):
            Day1MagicService.lock_palette_choice(
                school, "not-a-real-variation-id", by_user=FakeUser()
            )

    def test_lock_with_empty_variation_id_raises(self):
        school = FakeSchool()
        with self.assertRaises(ValueError):
            Day1MagicService.lock_palette_choice(school, "", by_user=FakeUser())


# ---------------------------------------------------------------------------
# View-layer tests (RequestFactory)
# ---------------------------------------------------------------------------


class _ViewTestsBase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _attach(self, request, *, school, user):
        request.school = school
        request.user = user
        request._messages = mock.MagicMock()
        return request


class _ViewTestsWithDbBase(TestCase):
    """Counterpart for tests whose service path uses ``transaction.atomic()``."""

    def setUp(self):
        self.factory = RequestFactory()

    def _attach(self, request, *, school, user):
        request.school = school
        request.user = user
        request._messages = mock.MagicMock()
        return request


class Day1Act1ViewTests(_ViewTestsBase):
    def test_act1_get_renders_with_seed_in_context(self):
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1Act1View

        school = FakeSchool(primary_color="#114488")
        request = self._attach(
            self.factory.get("/siteconfig/studio/day1/act1/"),
            school=school,
            user=FakeUser(is_staff=True),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=True,
        ), mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.render"
        ) as render_mock:
            render_mock.return_value = mock.MagicMock(status_code=200)
            TenantStudioDay1Act1View.as_view()(request)
            ctx = render_mock.call_args.args[2]
            self.assertIn("seed_hex", ctx)
            self.assertEqual(ctx["seed_source"], "primary_color")
            self.assertEqual(ctx["active_act"], 1)

    def test_act1_denies_non_operator(self):
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1Act1View

        request = self._attach(
            self.factory.get("/siteconfig/studio/day1/act1/"),
            school=FakeSchool(),
            user=FakeUser(is_staff=False, role="STUDENT"),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=False,
        ):
            resp = TenantStudioDay1Act1View.as_view()(request)
        self.assertEqual(resp.status_code, 403)


class Day1Act2ViewTests(_ViewTestsBase):
    def test_act2_returns_three_variations(self):
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1Act2View

        request = self._attach(
            self.factory.get("/siteconfig/studio/day1/act2/"),
            school=FakeSchool(),
            user=FakeUser(is_staff=True),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=True,
        ), mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.render"
        ) as render_mock:
            render_mock.return_value = mock.MagicMock(status_code=200)
            TenantStudioDay1Act2View.as_view()(request)
            ctx = render_mock.call_args.args[2]
            self.assertEqual(len(ctx["variations"]), 3)
            self.assertEqual(
                {v["tone"] for v in ctx["variations"]},
                {"classic", "warm", "vibrant"},
            )


class Day1Act3LockViewTests(_ViewTestsWithDbBase):
    def test_act3_locks_chosen_variation(self):
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1Act3LockView

        school = FakeSchool(primary_color="#114488")
        variations = Day1MagicService.generate_variations(school)
        chosen = variations[0]

        request = self._attach(
            self.factory.post(
                "/siteconfig/studio/day1/act3/lock/",
                {"variation_id": chosen.id},
                HTTP_ACCEPT="application/json",
            ),
            school=school,
            user=FakeUser(is_staff=True),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=True,
        ), mock.patch(
            "apps.siteconfig.tenant_studio_day1._mirror_to_site_settings"
        ):
            resp = TenantStudioDay1Act3LockView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertIn("palette_locked_at", school.branding_metadata)

    def test_act3_rejects_cross_tenant_variation_id(self):
        """A variation_id minted for another school must NOT lock here."""
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1Act3LockView

        other_school = FakeSchool(pk="other-pk", slug="other")
        their_variations = Day1MagicService.generate_variations(other_school)

        my_school = FakeSchool(pk="my-pk", slug="mine")
        request = self._attach(
            self.factory.post(
                "/siteconfig/studio/day1/act3/lock/",
                {"variation_id": their_variations[0].id},
                HTTP_ACCEPT="application/json",
            ),
            school=my_school,
            user=FakeUser(is_staff=True),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=True,
        ):
            resp = TenantStudioDay1Act3LockView.as_view()(request)
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn("palette_locked_at", my_school.branding_metadata)


class Day1ResetViewTests(_ViewTestsWithDbBase):
    def test_reset_requires_staff_or_admin(self):
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1ResetView

        request = self._attach(
            self.factory.post("/siteconfig/studio/day1/reset/"),
            school=FakeSchool(
                branding_metadata={"palette_locked_at": "2026-05-20T00:00:00Z"}
            ),
            user=FakeUser(is_staff=False, role="STUDENT"),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=True,
        ):
            resp = TenantStudioDay1ResetView.as_view()(request)
        self.assertEqual(resp.status_code, 403)

    def test_reset_succeeds_for_staff(self):
        from apps.siteconfig.views_tenant_studio_hub import TenantStudioDay1ResetView

        school = FakeSchool(
            branding_metadata={"palette_locked_at": "2026-05-20T00:00:00Z"},
        )
        request = self._attach(
            self.factory.post("/siteconfig/studio/day1/reset/"),
            school=school,
            user=FakeUser(is_staff=True),
        )
        with mock.patch(
            "apps.siteconfig.views_tenant_studio_hub.tenant_operator_hub_eligible",
            return_value=True,
        ), mock.patch(
            "apps.siteconfig.views_tenant_studio_hub._siteconfig_reverse",
            return_value="/siteconfig/studio/day1/act1/",
        ), mock.patch(
            "apps.siteconfig.views_tenant_studio_hub._tenant_reverse",
            return_value="/school/studio/",
        ):
            resp = TenantStudioDay1ResetView.as_view()(request)
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("palette_locked_at", school.branding_metadata)
