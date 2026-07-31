"""Phase 2: live auto-detection progress for the tenant upload path.

The tenant drops a file and the pipeline profiles/classifies/maps it (async on
the Celery worker, or inline on a broker outage). Before this, the review page
just showed a static "auto-detecting…" placeholder with no live feedback. These
tests lock the new behaviour:

* ``_is_detecting`` is true only while the bundle is still pre-MAPPED, so the
  widget shows + keeps polling exactly while there is work to watch.
* ``_progress_payload`` returns the plain flags the poller needs (``detecting`` /
  ``done`` / ``failed``) and never 500s the poller when the snapshot fails.
* The tenant-scoped progress route resolves on the tenant urlconf.
* ``_migration_status_card`` (Workflow Center sidebar) is operator ⟂ tenant safe:
  it returns ``None`` with no bound school and when the connector namespace isn't
  mounted on the active urlconf (the manager host), so it never leaks or 500s.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse

from apps.migration_cloud.models import BundleStatus
from apps.migration_cloud.views_tenant_upload import (
    _is_detecting,
    _progress_payload,
)


class _FakeArtifactManager:
    def __init__(self, artifacts):
        self._artifacts = artifacts

    def all(self):
        return list(self._artifacts)


def _fake_bundle(status, artifacts=None):
    return SimpleNamespace(
        pk=7,
        status=status,
        get_status_display=lambda: f"{status} label",
        progress_snapshot={"stages": []},
        # Real MigrationCloudBundle carries a size_summary JSONField (models.py);
        # the progress payload reads bundle.size_summary for advance_error, so
        # the fake must supply it too (else AttributeError on a namespace stub).
        size_summary={},
        artifacts=_FakeArtifactManager(artifacts or []),
    )


class IsDetectingTests(SimpleTestCase):
    def test_pre_mapped_statuses_are_detecting(self):
        for s in (
            BundleStatus.PENDING,
            BundleStatus.INGESTING,
            BundleStatus.PROFILED,
            BundleStatus.CLASSIFIED,
        ):
            self.assertTrue(_is_detecting(SimpleNamespace(status=s)), s)

    def test_mapped_onward_and_failed_not_detecting(self):
        for s in (
            BundleStatus.MAPPED,
            BundleStatus.READY,
            BundleStatus.APPLYING,
            BundleStatus.APPLIED,
            BundleStatus.RECONCILED,
            BundleStatus.FAILED,
            BundleStatus.ABORTED,
        ):
            self.assertFalse(_is_detecting(SimpleNamespace(status=s)), s)


class ProgressPayloadTests(SimpleTestCase):
    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_detecting_payload_flags(self, refresh):
        refresh.return_value = {"stages": [], "current_status": "PROFILED"}
        payload = _progress_payload(_fake_bundle(BundleStatus.PROFILED))
        self.assertTrue(payload["detecting"])
        self.assertFalse(payload["done"])
        self.assertFalse(payload["failed"])
        self.assertEqual(payload["bundle_id"], 7)
        self.assertEqual(payload["snapshot"], {"stages": [], "current_status": "PROFILED"})

    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_done_when_mapped(self, refresh):
        refresh.return_value = {"stages": []}
        payload = _progress_payload(_fake_bundle(BundleStatus.MAPPED))
        self.assertFalse(payload["detecting"])
        self.assertTrue(payload["done"])
        self.assertFalse(payload["failed"])

    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_failed_flag(self, refresh):
        refresh.return_value = {"stages": []}
        payload = _progress_payload(_fake_bundle(BundleStatus.FAILED))
        self.assertTrue(payload["failed"])
        # A FAILED bundle is terminal but NOT "done": done means "finished
        # successfully — reload to reveal results" and deliberately excludes
        # _FAILED_STATUSES. The poller (bundle_review.html) stops on the
        # separate `failed` branch, not `done`.
        self.assertFalse(payload["done"])

    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_snapshot_failure_degrades_not_raises(self, refresh):
        # A snapshot error must NOT 500 the poller — it falls back to the last
        # saved snapshot on the bundle and still returns usable flags.
        refresh.side_effect = RuntimeError("boom")
        payload = _progress_payload(_fake_bundle(BundleStatus.PROFILED))
        self.assertEqual(payload["snapshot"], {"stages": []})
        self.assertTrue(payload["detecting"])

    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_detected_domains_surface_early_signal(self, refresh):
        refresh.return_value = {"stages": []}
        art = SimpleNamespace(
            filename="students.csv",
            inferred_domain=[{"domain": "students", "confidence": 0.9}],
        )
        payload = _progress_payload(_fake_bundle(BundleStatus.CLASSIFIED, [art]))
        self.assertEqual(payload["detected"], [{"filename": "students.csv", "domain": "students"}])


class ProgressRouteTests(SimpleTestCase):
    def test_progress_route_resolves_on_tenant_urlconf(self):
        url = reverse(
            "migration_cloud_connector:bundle-progress",
            kwargs={"bundle_id": 7},
            urlconf="config.tenant_urls",
        )
        self.assertTrue(url.endswith("/bundle/7/progress/"))


class MigrationStatusCardTests(SimpleTestCase):
    def test_none_without_school(self):
        from apps.accounts.views_workflow import _migration_status_card

        req = SimpleNamespace(school=None, tenant=None)
        self.assertIsNone(_migration_status_card(req))

    def test_none_when_connector_namespace_absent(self):
        # Manager host: a school is bound but the tenant connector namespace is
        # not on the active (root) urlconf, so reverse() fails → no card, no 500.
        # Operator ⟂ tenant isolation: the operator never gets a tenant card.
        from apps.accounts.views_workflow import _migration_status_card

        req = SimpleNamespace(school=SimpleNamespace(pk=123), tenant=None)
        self.assertIsNone(_migration_status_card(req))
