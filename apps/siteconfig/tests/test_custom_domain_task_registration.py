"""Must-FIRE guard: the custom-domain @shared_tasks must be REGISTERED at startup.

``siteconfig.sweep_pending_custom_domains`` + ``siteconfig.verify_custom_domain``
live in ``apps/siteconfig/tasks_custom_domain.py`` (NOT ``tasks.py``), so
``config/celery.py``'s bare ``autodiscover_tasks()`` never imported them. The beat
entry ``siteconfig-sweep-pending-custom-domains`` therefore named an *unregistered*
task and was a silent no-op — a tenant's DNS-verified custom domain never activated.

``SiteconfigConfig.ready()`` now imports the module so both tasks register before the
beat scheduler reads the registry. This test asserts that EFFECT against the SAME
registry the beat-registry gate reads (``config.celery.app.tasks``).

It deliberately does NOT import ``tasks_custom_domain`` itself — doing so would register
the tasks as an import side effect and mask the very autodiscover-invisibility bug this
guards (a negative/indirect test can never detect a dead beat entry; only a must-FIRE
check of the live registry can).
"""

from __future__ import annotations

from django.test import SimpleTestCase


class CustomDomainTaskRegistrationTests(SimpleTestCase):
    def _registered_task_names(self) -> set[str]:
        # Same source of truth as scripts/verify_beat_task_registry.py.
        from config.celery import app

        return set(app.tasks.keys())

    def test_sweep_and_verify_tasks_registered_at_startup(self):
        registered = self._registered_task_names()
        self.assertIn("siteconfig.sweep_pending_custom_domains", registered)
        self.assertIn("siteconfig.verify_custom_domain", registered)

    def test_beat_entry_points_at_a_registered_task(self):
        from django.conf import settings

        beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        entry = beat.get("siteconfig-sweep-pending-custom-domains")
        self.assertIsNotNone(
            entry,
            "beat entry 'siteconfig-sweep-pending-custom-domains' is missing from "
            "CELERY_BEAT_SCHEDULE",
        )
        self.assertIn(entry["task"], self._registered_task_names())
