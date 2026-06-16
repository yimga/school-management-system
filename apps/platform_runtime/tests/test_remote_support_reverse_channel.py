"""Remote Support P4 — reverse channel: models, service, views (no DB)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from apps.platform_runtime import remote_support_reverse_channel as svc
from apps.platform_runtime import views_remote_support_reverse as views
from apps.platform_runtime.models_remote_support import (
    OperatorIntent,
    TenantConnectivityHeartbeat,
)

K = OperatorIntent.Kind
ST = OperatorIntent.Status
rf = RequestFactory()


class _School:
    id = 1
    pk = 1


class _U:
    is_authenticated = True
    is_superuser = False
    id = 7
    pk = 7


# ---- model logic (pure) -----------------------------------------------------
class OperatorIntentModelTests(SimpleTestCase):
    def test_pending_is_live(self):
        self.assertTrue(OperatorIntent(kind=K.MESSAGE, status=ST.PENDING).is_live())

    def test_acknowledged_not_live(self):
        self.assertFalse(
            OperatorIntent(kind=K.MESSAGE, status=ST.ACKNOWLEDGED).is_live()
        )

    def test_expired_not_live(self):
        i = OperatorIntent(
            kind=K.MESSAGE,
            status=ST.PENDING,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(i.is_live())

    def test_mark_delivered_then_acknowledged(self):
        i = OperatorIntent(kind=K.MESSAGE, status=ST.PENDING)
        i.mark_delivered()
        self.assertEqual(i.status, ST.DELIVERED)
        self.assertIsNotNone(i.delivered_at)
        i.mark_acknowledged(note="applied")
        self.assertEqual(i.status, ST.ACKNOWLEDGED)
        self.assertEqual(i.ack_note, "applied")


class HeartbeatModelTests(SimpleTestCase):
    def test_recent_is_online(self):
        hb = TenantConnectivityHeartbeat(
            school_id=1, last_seen_at=timezone.now()
        )
        self.assertTrue(hb.is_online())

    def test_stale_is_offline(self):
        hb = TenantConnectivityHeartbeat(
            school_id=1, last_seen_at=timezone.now() - timedelta(hours=2)
        )
        self.assertFalse(hb.is_online())


# ---- service ----------------------------------------------------------------
class ReverseChannelServiceTests(SimpleTestCase):
    def test_queue_creates_pending_intent(self):
        with mock.patch.object(
            OperatorIntent.objects, "create"
        ) as create, mock.patch.object(svc, "_audit_intent"):
            create.return_value = OperatorIntent(kind=K.MESSAGE, status=ST.PENDING)
            svc.queue_operator_intent(
                school=_School(), created_by=_U(), kind=K.MESSAGE, payload={"x": 1}
            )
        self.assertTrue(create.called)
        self.assertEqual(create.call_args.kwargs["status"], ST.PENDING)

    @mock.patch.object(OperatorIntent, "save")
    def test_fetch_marks_pending_delivered(self, save):
        i = OperatorIntent(kind=K.MESSAGE, status=ST.PENDING)
        qs = mock.Mock()
        qs.order_by.return_value = [i]
        with mock.patch.object(OperatorIntent.objects, "filter", return_value=qs):
            out = svc.fetch_pending_intents(school=_School())
        self.assertEqual(len(out), 1)
        self.assertEqual(i.status, ST.DELIVERED)
        self.assertTrue(save.called)

    @mock.patch.object(OperatorIntent, "save")
    def test_acknowledge_sets_status(self, save):
        i = OperatorIntent(kind=K.MESSAGE, status=ST.DELIVERED)
        with mock.patch.object(svc, "_audit_intent"):
            svc.acknowledge_intent(intent=i, actor=_U(), note="done")
        self.assertEqual(i.status, ST.ACKNOWLEDGED)
        self.assertTrue(save.called)

    def test_record_heartbeat_upserts(self):
        hb = TenantConnectivityHeartbeat(school_id=1, last_seen_at=timezone.now())
        with mock.patch.object(
            TenantConnectivityHeartbeat.objects,
            "update_or_create",
            return_value=(hb, True),
        ) as uoc:
            out = svc.record_heartbeat(school=_School(), profile="edge")
        self.assertTrue(uoc.called)
        self.assertIs(out, hb)

    def test_config_version_from_updated_at(self):
        s = mock.Mock(updated_at=timezone.now())
        self.assertTrue(svc.config_version_for(s))


# ---- views ------------------------------------------------------------------
class ReverseChannelViewTests(SimpleTestCase):
    _UC = "config.tenant_urls"

    def test_routes_reverse(self):
        for name in (
            "remote_support_queue_intent",
            "remote_support_pending_intents",
            "remote_support_heartbeat",
            "remote_support_config_version",
        ):
            self.assertTrue(
                reverse(f"platform_runtime:{name}", urlconf=self._UC), name
            )

    def test_pending_requires_tenant_context(self):
        req = rf.get("/x/pending/")
        req.user = _U()
        self.assertEqual(views.pending_intents(req).status_code, 400)

    def test_queue_rejects_invalid_kind(self):
        req = rf.post("/x/queue/", {"kind": "bogus"})
        req.user = _U()
        self.assertEqual(views.queue_intent(req).status_code, 400)

    def test_queue_denies_unauthorized_operator(self):
        req = rf.post("/x/queue/", {"kind": K.MESSAGE, "school_id": "1"})
        req.user = _U()
        with mock.patch.object(
            views, "get_object_or_404", return_value=_School()
        ), mock.patch.object(
            views, "operator_can_remote_support", return_value=False
        ):
            with self.assertRaises(PermissionDenied):
                views.queue_intent(req)

    def test_heartbeat_records_and_reports_online(self):
        req = rf.post("/x/heartbeat/", {"profile": "edge"})
        req.user = _U()
        req.school = _School()
        hb = mock.Mock()
        hb.is_online.return_value = True
        with mock.patch.object(views.svc, "record_heartbeat", return_value=hb):
            resp = views.heartbeat(req)
        self.assertEqual(resp.status_code, 200)
