"""Per-role first-run zero-state (no DB).

Locks the gating contract: a welcome card appears ONLY for a supported role, on a
known role-home landing, while the tenant is still in first-run — and never else.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.dashboard import first_run_zero_state as frz
from apps.dashboard.context_processors import first_run_zero_state as frz_ctx

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _req(*, authed=True, role="ADMIN", view_name="accounts:backend_dashboard"):
    return SimpleNamespace(
        user=SimpleNamespace(is_authenticated=authed, role=role),
        resolver_match=SimpleNamespace(view_name=view_name),
    )


class ZeroStateForRoleTests(SimpleTestCase):
    def test_each_supported_role_maps_to_a_card(self):
        for role in ("ADMIN", "PRINCIPAL", "TEACHER", "PARENT", "STUDENT", "BURSAR"):
            card = frz.zero_state_for_role(role)
            self.assertIsNotNone(card, role)
            self.assertTrue(card["headline"])
            self.assertTrue(card["message"])
            self.assertTrue(card["primary_url_name"])

    def test_admin_and_finance_point_at_setup_wizards(self):
        self.assertEqual(
            frz.zero_state_for_role("ADMIN")["primary_url_name"],
            "setup_studio:tenant_wizard_index",
        )
        self.assertEqual(
            frz.zero_state_for_role("BURSAR")["primary_url_name"],
            "setup_studio:tenant_wizard_index",
        )

    def test_case_insensitive(self):
        self.assertIsNotNone(frz.zero_state_for_role("teacher"))

    def test_unsupported_role_returns_none(self):
        self.assertIsNone(frz.zero_state_for_role("SUPERHERO"))
        self.assertIsNone(frz.zero_state_for_role(""))
        self.assertIsNone(frz.zero_state_for_role(None))


class BuildFirstRunZeroStateTests(SimpleTestCase):
    def test_happy_path_returns_render_ready_card(self):
        with mock.patch.object(frz, "_tenant_is_first_run", return_value=True), \
                mock.patch.object(frz, "reverse", return_value="/school/studio/wizards/"):
            card = frz.build_first_run_zero_state(_req(role="ADMIN"))
        self.assertIsNotNone(card)
        self.assertEqual(card["primary_url"], "/school/studio/wizards/")
        self.assertTrue(card["primary_label"])
        self.assertEqual(card["illustration"], "first_run")

    def test_anonymous_user_gets_nothing(self):
        with mock.patch.object(frz, "_tenant_is_first_run", return_value=True):
            self.assertIsNone(frz.build_first_run_zero_state(_req(authed=False)))

    def test_non_landing_view_gets_nothing(self):
        with mock.patch.object(frz, "_tenant_is_first_run", return_value=True):
            self.assertIsNone(
                frz.build_first_run_zero_state(_req(view_name="portal:teacher_attendance"))
            )

    def test_unsupported_role_gets_nothing(self):
        with mock.patch.object(frz, "_tenant_is_first_run", return_value=True):
            self.assertIsNone(frz.build_first_run_zero_state(_req(role="SUPERHERO")))

    def test_established_tenant_gets_nothing(self):
        with mock.patch.object(frz, "_tenant_is_first_run", return_value=False):
            self.assertIsNone(frz.build_first_run_zero_state(_req(role="ADMIN")))

    def test_admin_backend_setup_surface_suppresses_duplicate_welcome(self):
        with mock.patch.object(frz, "_tenant_is_first_run", return_value=True), \
                mock.patch.object(frz, "_admin_setup_surface_active", return_value=True):
            self.assertIsNone(frz.build_first_run_zero_state(_req(role="ADMIN")))

    def test_unreversible_cta_drops_the_button_but_keeps_the_message(self):
        from django.urls import NoReverseMatch

        with mock.patch.object(frz, "_tenant_is_first_run", return_value=True), \
                mock.patch.object(frz, "reverse", side_effect=NoReverseMatch):
            card = frz.build_first_run_zero_state(_req(role="TEACHER"))
        self.assertIsNotNone(card)
        self.assertIsNone(card["primary_url"])
        self.assertIsNone(card["primary_label"])
        self.assertTrue(card["headline"])  # message still shown

    def test_never_raises_on_malformed_request(self):
        self.assertIsNone(frz.build_first_run_zero_state(SimpleNamespace()))


class ContextProcessorTests(SimpleTestCase):
    def test_returns_payload_when_present(self):
        with mock.patch.object(frz, "build_first_run_zero_state", return_value={"headline": "Hi"}):
            self.assertEqual(frz_ctx(_req()), {"first_run_zero_state": {"headline": "Hi"}})

    def test_returns_empty_when_absent(self):
        with mock.patch.object(frz, "build_first_run_zero_state", return_value=None):
            self.assertEqual(frz_ctx(_req()), {})

    def test_never_raises(self):
        with mock.patch.object(frz, "build_first_run_zero_state", side_effect=RuntimeError):
            self.assertEqual(frz_ctx(_req()), {})


class CacheInvalidationTests(SimpleTestCase):
    def test_cache_key_is_stable_and_pk_scoped(self):
        self.assertEqual(
            frz._first_run_cache_key(SimpleNamespace(pk=42)),
            "rmc:first_run_zero_state:42",
        )

    def test_cache_key_is_none_without_pk(self):
        self.assertIsNone(frz._first_run_cache_key(SimpleNamespace()))

    def test_invalidate_deletes_the_scoped_key(self):
        with mock.patch.object(frz, "cache") as cache_mock:
            frz.invalidate_first_run_zero_state(SimpleNamespace(pk=7))
        cache_mock.delete.assert_called_once_with("rmc:first_run_zero_state:7")

    def test_invalidate_is_a_noop_without_pk(self):
        with mock.patch.object(frz, "cache") as cache_mock:
            frz.invalidate_first_run_zero_state(SimpleNamespace())
        cache_mock.delete.assert_not_called()

    def test_invalidate_never_raises(self):
        with mock.patch.object(frz, "cache") as cache_mock:
            cache_mock.delete.side_effect = RuntimeError("cache down")
            frz.invalidate_first_run_zero_state(SimpleNamespace(pk=1))  # must not raise

    def test_launch_path_invalidates_the_card(self):
        # execute_launch must drop the cached first-run flag so the card vanishes
        # the instant the tenant goes live.
        src = (_REPO_ROOT / "apps" / "setup_studio" / "services.py").read_text(encoding="utf-8")
        self.assertIn("invalidate_first_run_zero_state", src)


class WiringTests(SimpleTestCase):
    def test_context_processor_registered_in_settings(self):
        settings_src = (_REPO_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertIn(
            "apps.dashboard.context_processors.first_run_zero_state",
            settings_src,
        )

    def test_portal_base_renders_the_gated_card(self):
        tpl = (_REPO_ROOT / "templates" / "portal_base.html").read_text(encoding="utf-8")
        self.assertIn("{% if first_run_zero_state %}", tpl)
        self.assertIn("first_run_zero_state.headline", tpl)
        self.assertIn("components/rmc_empty_state.html", tpl)
