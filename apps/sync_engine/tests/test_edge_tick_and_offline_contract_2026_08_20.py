"""The tick nothing was driving, and the PIN dialog that blamed the browser.

TWO defects, both measured on the sovereign box at 10.10.20.137 on 2026-08-20.

**1. Nothing drove the periodic tick.** ``EdgeAutosyncMiddleware`` exists to run the
in-process scheduler from ordinary page loads, because a LAN box has nothing pinging
``/health/``. Its own docstring said so — and it was in no ``MIDDLEWARE`` list, so it
had never run. Combined with ``inprocess_scheduler: false`` (the box stands the
in-process scheduler down for a Celery beat that could not run) and a compose file whose
only healthcheck was on ``db``, four independent drivers of the tick were dead at once.

**2. "Local access could not be enabled on this browser."** The offline capability vault
derives its PIN key with ``crypto.subtle``, which browsers expose ONLY in a secure
context. ``http://10.10.20.137:10000`` is not one, so the call threw and a bare ``catch``
blamed the browser. Chrome implements WebCrypto correctly; the ORIGIN does not qualify,
and changing browsers can never help.

The JavaScript assertions here are static contract checks (the pattern
``test_login_front_door_12_contract`` already uses). They cannot execute the browser
path, but they do pin the specific properties whose absence caused the outage.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR)
STATIC_JS = REPO_ROOT / "static" / "js"

MIDDLEWARE_PATH = "apps.sync_engine.middleware_edge_autosync.EdgeAutosyncMiddleware"


def _js(name: str) -> str:
    return (STATIC_JS / name).read_text(encoding="utf-8")


class EdgeAutosyncMiddlewareRegistrationTests(SimpleTestCase):
    def test_the_middleware_is_actually_installed(self):
        """THE BUG. It was written for this failure and never registered."""
        self.assertIn(MIDDLEWARE_PATH, settings.MIDDLEWARE)

    def test_it_runs_before_the_gate_middlewares_that_can_short_circuit(self):
        """A login redirect must still advance the tick.

        If this sat at the end of the list, every request that an auth gate or a host
        redirect answered early would skip the tick entirely — which on a box that only
        ever shows a login page is most of them.
        """
        index = settings.MIDDLEWARE.index(MIDDLEWARE_PATH)
        for later in (
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "apps.accounts.middleware.RequireMFAMiddleware",
        ):
            if later in settings.MIDDLEWARE:
                self.assertLess(index, settings.MIDDLEWARE.index(later), later)

    def test_it_runs_after_whitenoise_so_static_requests_never_reach_it(self):
        whitenoise = "whitenoise.middleware.WhiteNoiseMiddleware"
        if whitenoise in settings.MIDDLEWARE:
            self.assertGreater(
                settings.MIDDLEWARE.index(MIDDLEWARE_PATH),
                settings.MIDDLEWARE.index(whitenoise),
            )

    def test_it_is_inert_under_tests(self):
        """The scheduler must never fire from a test request."""
        from apps.sync_engine.middleware_edge_autosync import EdgeAutosyncMiddleware

        calls = []
        middleware = EdgeAutosyncMiddleware(lambda _r: calls.append("response") or "resp")

        class _Req:
            headers = {"Sec-Fetch-Dest": "document"}

        self.assertEqual(middleware(_Req()), "resp")
        self.assertEqual(calls, ["response"], "the response must still be produced")

    def test_a_broken_scheduler_never_breaks_a_page(self):
        from apps.sync_engine.middleware_edge_autosync import EdgeAutosyncMiddleware

        middleware = EdgeAutosyncMiddleware(lambda _r: "resp")

        class _Req:
            @property
            def headers(self):
                raise RuntimeError("boom")

        self.assertEqual(middleware(_Req()), "resp")


class SelfHostHealthcheckTests(SimpleTestCase):
    """On Render the platform's probe drives /health/ for free. On a LAN box nothing
    does, and the compose file only ever health-checked the database."""

    def test_the_web_service_has_a_healthcheck_that_hits_health(self):
        compose = (REPO_ROOT / "deploy" / "selfhost" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("/health/", compose)
        # Not just present — it must belong to the web service, which is the only one
        # that can drive the tick.
        web_block = compose.split("  web:", 1)[1].split("\n  worker:", 1)[0]
        self.assertIn("healthcheck", web_block)
        self.assertIn("/health/", web_block)

    def test_the_beat_service_is_checked_on_publishing_not_on_being_alive(self):
        """A beat process that is up and publishing nothing is exactly what broke this
        box, so checking the process would have proved nothing."""
        compose = (REPO_ROOT / "deploy" / "selfhost" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        beat_block = compose.split("  beat:", 1)[1]
        self.assertIn("check_beat_publishing", beat_block)


class OfflineVaultSecureContextTests(SimpleTestCase):
    def test_the_vault_exposes_an_availability_check(self):
        self.assertIn("function availability()", _js("rmc-offline-auth-vault.js"))

    def test_both_crypto_entry_points_assert_availability_first(self):
        source = _js("rmc-offline-auth-vault.js")
        for fn in ("async function sealCapability", "async function openCapability"):
            body = source.split(fn, 1)[1][:220]
            self.assertIn("assertAvailable()", body, fn)

    def test_the_insecure_context_reason_names_https_not_the_browser(self):
        source = _js("rmc-offline-auth-vault.js")
        self.assertIn("insecure-context", source)
        self.assertIn("secure (HTTPS) connection", source)

    def test_enrollment_no_longer_offers_a_pin_it_cannot_use(self):
        """Asking someone to choose and confirm a PIN and only THEN telling them it
        cannot work is the worst possible order — and it is what shipped."""
        source = _js("rmc-offline-auth-enrollment.js")
        self.assertIn("availability()", source)
        # The capability check must precede the dialog being shown.
        self.assertLess(source.index("availability()"), source.index("showModal()"))

    def test_the_enrollment_failure_is_no_longer_swallowed_silently(self):
        """The bare `catch (_error)` is why this was opaque for so long."""
        source = _js("rmc-offline-auth-enrollment.js")
        self.assertIn("console.warn", source)
        self.assertNotIn("catch (_error) { status.textContent", source)

    def test_the_unlock_path_distinguishes_a_bad_origin_from_a_bad_pin(self):
        source = _js("rmc-offline-login-unlock.js")
        self.assertIn("rmcReason", source)

    def test_the_passkey_message_names_the_origin_when_the_context_is_insecure(self):
        source = _js("rmc-auth-login-immersive.js")
        self.assertIn("window.isSecureContext === false", source)
        self.assertIn("secure (HTTPS) connection", source)
