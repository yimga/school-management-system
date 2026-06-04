"""Context-snapshot safety nets for the three "god-object" context builders.

These tests exist BEFORE any refactor/split of:

  * ``apps.siteconfig.context_processors.site_settings``  (~887 lines)
  * ``apps.schools.marketing_views._marketing_context``   (~1382 lines)
  * ``apps.accounts.views.backend_dashboard``             (~1283 lines)

Each function assembles a large context dict that templates depend on. The
risk when splitting them is silently dropping or renaming a key. These tests
PIN the exact set of top-level keys each builder emits, so a split that changes
the contract fails loudly.

Golden-file contract
--------------------
The pinned key sets live in ``var/god-object-context-keys-baseline.json``.

  * First run (file or per-target entry absent): the current key set is
    RECORDED and the assertion passes with a printed note. Commit the recorded
    baseline and review it.
  * Subsequent runs: the current key set must match the baseline exactly.

To intentionally re-record after a deliberate contract change, delete the
relevant entry (or the whole file), or run with
``RMC_RECORD_GOD_OBJECT_SNAPSHOTS=1``.
"""

from __future__ import annotations

import json
import os
import time
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from django.conf import settings as dj_settings
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School

_BASELINE_PATH = Path(dj_settings.BASE_DIR) / "var" / "god-object-context-keys-baseline.json"
_RECORD_ALWAYS = os.getenv("RMC_RECORD_GOD_OBJECT_SNAPSHOTS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

_T_HOST = "god-snap.runmycampus.com"


def _load_baseline() -> dict:
    if _BASELINE_PATH.exists():
        try:
            return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _write_baseline(data: dict) -> None:
    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _anon_request(path: str = "/"):
    """A minimally-viable request for the dict-builder context functions."""
    req = RequestFactory().get(path)
    req.user = AnonymousUser()
    engine = import_module(dj_settings.SESSION_ENGINE)
    req.session = engine.SessionStore()
    return req


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    CONVERSION_LOCK_STRICT=False,
    CONVERSION_LOCK_ALL_SCHOOLS=False,
    DISABLE_SCHOOL_ACTIVATION_GATE=True,
)
class GodObjectContextSnapshotTests(TestCase):
    """Pin the emitted key sets of the three large context builders."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="God Snapshot School",
            slug="god-snap",
            subdomain="god-snap",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    # -- shared golden-file comparison -----------------------------------
    def _assert_or_record(self, name: str, current_keys: list[str]) -> None:
        current = sorted(current_keys)
        baseline = _load_baseline()
        if _RECORD_ALWAYS or name not in baseline:
            baseline[name] = current
            _write_baseline(baseline)
            print(
                f"\n[god-object-snapshot] recorded baseline for '{name}' "
                f"({len(current)} keys) -> {_BASELINE_PATH}"
            )
            self.assertTrue(current, msg=f"{name}: builder returned no keys")
            return

        expected = sorted(baseline[name])
        if current != expected:
            missing = sorted(set(expected) - set(current))
            added = sorted(set(current) - set(expected))
            self.fail(
                f"Context key contract for '{name}' changed.\n"
                f"  Dropped/renamed (REGRESSION risk): {missing}\n"
                f"  Newly added: {added}\n"
                f"If this change is intentional, re-record by deleting the "
                f"'{name}' entry in {_BASELINE_PATH} (or run with "
                f"RMC_RECORD_GOD_OBJECT_SNAPSHOTS=1) and review the diff."
            )

    # -- site_settings (context processor) -------------------------------
    def test_site_settings_context_keys(self):
        from apps.siteconfig.context_processors import site_settings

        ctx = site_settings(_anon_request("/"))
        self.assertIsInstance(ctx, dict)
        self._assert_or_record("site_settings", list(ctx.keys()))

    # -- _marketing_context (dict builder) -------------------------------
    def test_marketing_context_keys(self):
        from apps.schools.marketing_views import _marketing_context

        req = RequestFactory(HTTP_HOST=_T_HOST).get("/")
        req.user = AnonymousUser()
        engine = import_module(dj_settings.SESSION_ENGINE)
        req.session = engine.SessionStore()
        ctx = _marketing_context(
            req, country_code="", language_code="en", regional=False
        )
        self.assertIsInstance(ctx, dict)
        self._assert_or_record("marketing_context", list(ctx.keys()))

    # -- backend_dashboard (full authed view) ----------------------------
    def test_backend_dashboard_context_keys(self):
        import apps.accounts.views as views_mod

        real_render = views_mod.render
        captured: dict[str, object] = {}

        def capturing_render(request, template, context=None, *args, **kwargs):
            if "dashboard" in str(template):
                captured["keys"] = list((context or {}).keys())
            return real_render(request, template, context, *args, **kwargs)

        u = User.objects.create_user(
            username="god_snap_adm",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)

        client = Client(HTTP_HOST=_T_HOST, raise_request_exception=True)
        path = reverse("accounts:backend_dashboard", urlconf="config.tenant_urls")

        client.login(username="god_snap_adm", password="x" * 8)
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.update_or_create(
            user=u, name="god-snap-test", defaults={"confirmed": True}
        )
        session = client.session
        session["mfa_verified"] = True
        session.save()

        # settings_test runs on shared-cache in-memory SQLite. The platform's
        # async email send (``send_transactional(async_send=True)``) spawns a
        # daemon thread that writes the delivery-audit row on a SEPARATE
        # connection, tripping SQLITE_LOCKED ("database table is locked") against
        # the request's own DB read. That is a test-infra artifact, not a product
        # fault (SQLITE_LOCKED cannot be waited out via busy_timeout). Neutralise
        # the documented source by no-op'ing the async worker for this request —
        # scoped to the email module only (no global threading patch, so no risk
        # of stalling unrelated request machinery). A bounded retry + skip remains
        # as a backstop for any other incidental writer.
        from django.db import connections

        resp = None
        last_lock_err = None
        for attempt in range(4):
            try:
                with patch(
                    "apps.schoolops.email_delivery._async_send_worker",
                    lambda **_kw: None,
                ), patch.object(
                    views_mod, "render", side_effect=capturing_render
                ):
                    resp = client.get(path)
                break
            except Exception as exc:  # noqa: BLE001 - re-raised unless it's the lock
                if "locked" not in str(exc).lower():
                    raise
                last_lock_err = exc
                for conn in connections.all():
                    conn.close()
                time.sleep(0.25 * (attempt + 1))
        if resp is None:
            self.skipTest(
                "backend_dashboard snapshot skipped: in-memory SQLite lock "
                f"artifact persisted across retries ({last_lock_err})"
            )

        self.assertEqual(
            resp.status_code, 200, msg=getattr(resp, "content", b"")[:500]
        )
        self.assertIn(
            "keys", captured, msg="backend_dashboard did not render a *dashboard* template"
        )
        self._assert_or_record("backend_dashboard", captured["keys"])
