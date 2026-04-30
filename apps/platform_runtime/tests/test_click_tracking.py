"""Click measurement: ingest, aggregation, tenant isolation, insufficient-sample gates."""

from __future__ import annotations

import json
import uuid

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.click_tracking import (
    PHASE_BASELINE,
    PHASE_CURRENT,
    TRACKED_TASK_CODES,
    get_conversion_measurement_bundle,
    get_median_clicks_before_after,
    record_click_event,
)
from apps.platform_runtime.models import ClickTrackEvent
from apps.platform_runtime.views_click_tracking import record_click_event as record_click_event_view
from apps.schools.models import School


def _seed_completed_session(
    *,
    school_id: int,
    user_id: int | None,
    task_code: str,
    phase: str,
    session_run_id: str,
    click_count: int,
):
    K = ClickTrackEvent.Kind
    ClickTrackEvent.objects.create(
        kind=K.TASK_START,
        task_code=task_code,
        session_run_id=session_run_id,
        phase=phase,
        school_id=school_id,
        user_id=user_id,
        path="/",
    )
    for _ in range(click_count):
        ClickTrackEvent.objects.create(
            kind=K.CLICK,
            task_code=task_code,
            session_run_id=session_run_id,
            phase=phase,
            school_id=school_id,
            user_id=user_id,
            path="/",
        )
    ClickTrackEvent.objects.create(
        kind=K.TASK_COMPLETE,
        task_code=task_code,
        session_run_id=session_run_id,
        phase=phase,
        school_id=school_id,
        user_id=user_id,
        path="/",
    )


class ClickTrackingServiceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Click A",
            slug="click-a",
            subdomain="click-a",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Click B",
            slug="click-b",
            subdomain="click-b",
            is_active=True,
        )
        cls.user = User.objects.create_user(
            username="click_meas_user",
            password="x" * 8,
        )

    def test_record_click_event_persists(self):
        rid = str(uuid.uuid4())
        record_click_event(
            school_id=self.school_a.id,
            user_id=self.user.id,
            kind=ClickTrackEvent.Kind.CLICK,
            task_code="teacher_marks_entry",
            session_run_id=rid,
            phase=PHASE_CURRENT,
            action_code="save_row",
            path="/marks/",
        )
        self.assertEqual(ClickTrackEvent.objects.filter(session_run_id=rid).count(), 1)

    @override_settings(FIFTY_PCT_REDUCTION_CLAIM_ALLOWED=True)
    def test_task_completion_enables_session_for_median(self):
        tc = "teacher_marks_entry"
        for i in range(8):
            _seed_completed_session(
                school_id=self.school_a.id,
                user_id=self.user.id,
                task_code=tc,
                phase=PHASE_BASELINE,
                session_run_id=str(uuid.uuid4()),
                click_count=10,
            )
        for i in range(8):
            _seed_completed_session(
                school_id=self.school_a.id,
                user_id=self.user.id,
                task_code=tc,
                phase=PHASE_CURRENT,
                session_run_id=str(uuid.uuid4()),
                click_count=5,
            )
        stats = get_median_clicks_before_after(self.school_a.id, task_code=tc, min_sessions=8)
        row = stats["per_task"][tc]
        self.assertFalse(row["insufficient_data"])
        self.assertEqual(row["baseline_median_clicks"], 10.0)
        self.assertEqual(row["current_median_clicks"], 5.0)
        self.assertEqual(row["reduction_pct"], 50.0)
        self.assertTrue(row["fifty_pct_reduction_claim_allowed"])

    def test_median_calculation_odd_sessions(self):
        tc = "attendance_export"
        for n in (3, 5, 7):
            _seed_completed_session(
                school_id=self.school_a.id,
                user_id=self.user.id,
                task_code=tc,
                phase=PHASE_BASELINE,
                session_run_id=str(uuid.uuid4()),
                click_count=n,
            )
        for i in range(8):
            _seed_completed_session(
                school_id=self.school_a.id,
                user_id=self.user.id,
                task_code=tc,
                phase=PHASE_CURRENT,
                session_run_id=str(uuid.uuid4()),
                click_count=1,
            )
        stats = get_median_clicks_before_after(self.school_a.id, task_code=tc, min_sessions=8)
        row = stats["per_task"][tc]
        self.assertTrue(row["insufficient_data"])
        self.assertEqual(stats["verdict"], "insufficient_data")
        self.assertFalse(stats["fifty_pct_reduction_claim_allowed"])

    def test_insufficient_data_gate(self):
        tc = "parent_payment"
        _seed_completed_session(
            school_id=self.school_a.id,
            user_id=self.user.id,
            task_code=tc,
            phase=PHASE_BASELINE,
            session_run_id=str(uuid.uuid4()),
            click_count=4,
        )
        stats = get_median_clicks_before_after(self.school_a.id, task_code=tc, min_sessions=8)
        self.assertTrue(stats["insufficient_data"])

    def test_conversion_measurement_bundle_includes_clicks_and_funnel(self):
        bundle = get_conversion_measurement_bundle(self.school_a.id, task_code="teacher_marks_entry")
        self.assertIn("clicks", bundle)
        self.assertIn("funnel", bundle)
        self.assertIn("insufficient_data", bundle["clicks"])
        self.assertIn("event_counts", bundle["funnel"])
        self.assertIn("time_to_first_value_seconds", bundle["funnel"])
        self.assertIn("activation_rate", bundle["funnel"])
        self.assertIn("conversion_rate", bundle["funnel"])

    def test_tenant_isolation(self):
        tc = "report_generation"
        _seed_completed_session(
            school_id=self.school_a.id,
            user_id=self.user.id,
            task_code=tc,
            phase=PHASE_BASELINE,
            session_run_id=str(uuid.uuid4()),
            click_count=2,
        )
        _seed_completed_session(
            school_id=self.school_b.id,
            user_id=self.user.id,
            task_code=tc,
            phase=PHASE_BASELINE,
            session_run_id=str(uuid.uuid4()),
            click_count=99,
        )
        sa = get_median_clicks_before_after(self.school_a.id, task_code=tc)
        sb = get_median_clicks_before_after(self.school_b.id, task_code=tc)
        self.assertEqual(sa["per_task"][tc]["baseline_completed_sessions"], 1)
        self.assertEqual(sb["per_task"][tc]["baseline_completed_sessions"], 1)


@override_settings(ALLOWED_HOSTS=["testserver"])
class ClickTrackingHttpTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.school = School.objects.create(
            name="HTTP Click",
            slug="http-click",
            subdomain="http-click",
            is_active=True,
        )
        self.user = User.objects.create_user(username="http_click_u", password="x" * 8)
        self.factory = RequestFactory()

    def test_view_requires_school(self):
        req = self.factory.post(
            "/api/internal/click-tracking/",
            data=json.dumps(
                {
                    "kind": "click",
                    "task_code": TRACKED_TASK_CODES[0],
                    "session_run_id": str(uuid.uuid4()),
                    "phase": "current",
                }
            ),
            content_type="application/json",
        )
        req.user = self.user
        resp = record_click_event_view(req)
        self.assertEqual(resp.status_code, 400)

    def test_view_records_when_school_attached(self):
        req = self.factory.post(
            "/api/internal/click-tracking/",
            data=json.dumps(
                {
                    "kind": "click",
                    "task_code": "teacher_marks_entry",
                    "session_run_id": str(uuid.uuid4()),
                    "phase": "current",
                    "action": "go",
                }
            ),
            content_type="application/json",
        )
        req.user = self.user
        req.school = self.school
        resp = record_click_event_view(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("ok"))
