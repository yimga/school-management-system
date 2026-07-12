"""Privilege-audit flags must not pollute the DSL safeguarding-concern inbox.

The 6-hourly ``audit_privilege_context_task`` used to append ``{ts, kind, count}``
rows to ``School.settings["safeguarding"]["dsl_inbox"]`` — the SAME list the DSL
concern inbox uses. Those rows carry no ``entry_id`` and no ``acknowledged_at_iso``,
so ``list_unacknowledged`` counted them as open concerns forever and
``acknowledge_inbox_entry`` (matches on ``entry_id``) could never clear them —
lighting a red "Open safeguarding concern — DSL action required within KCSIE SLA"
operator banner on every tenant whose admin hadn't logged in for 24h, un-clearable.

The fix: (1) ``list_unacknowledged`` counts only real concern rows (has
``entry_id``); (2) the sweep writes flags to a dedicated ``privilege_audit_log``
bucket and relocates any legacy rows out of ``dsl_inbox``.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.safeguarding.dsl_notify import (
    acknowledge_inbox_entry,
    list_unacknowledged,
    notify_dsl_of_concern,
)


def _privilege_row(count: int = 3) -> dict:
    """The exact shape the privilege-audit sweep historically appended."""
    return {
        "ts": timezone.now().isoformat(),
        "kind": "privilege.stale_admin_login",
        "count": count,
    }


def _real_concern(inbox=None, *, concern_id="c1", is_urgent=True) -> list:
    return notify_dsl_of_concern(
        current_inbox=inbox,
        concern_id=concern_id,
        category_key="physical_abuse",
        category_label="Physical abuse",
        is_urgent=is_urgent,
        submitted_by_user_id=1,
        student_id=2,
    ).updated_inbox


class ListUnacknowledgedIgnoresPrivilegeRows(SimpleTestCase):
    def test_privilege_only_inbox_counts_zero(self):
        # The banner bug: an inbox of nothing but privilege noise must count 0.
        inbox = [_privilege_row(), _privilege_row(5)]
        self.assertEqual(list_unacknowledged(inbox), [])

    def test_privilege_rows_excluded_but_real_concern_counted(self):
        inbox = _real_concern()
        inbox = inbox + [_privilege_row()]
        unack = list_unacknowledged(inbox)
        self.assertEqual(len(unack), 1)
        self.assertEqual(unack[0]["concern_id"], "c1")

    def test_acknowledged_real_concern_still_excluded(self):
        inbox = _real_concern()
        entry_id = inbox[0]["entry_id"]
        inbox = acknowledge_inbox_entry(
            current_inbox=inbox, entry_id=entry_id, acknowledged_by_user_id=9
        )
        inbox = inbox + [_privilege_row()]
        self.assertEqual(list_unacknowledged(inbox), [])


class OperatorQueueBannerNotLitByPrivilegeNoise(SimpleTestCase):
    def test_privilege_only_inbox_does_not_light_dsl_banner(self):
        # Decisive: the operator-queue consumer that lights the KCSIE danger
        # banner must report 0 unacknowledged and no DSL state for privilege noise.
        from apps.platform_runtime.operator_queue_signals import (
            build_operator_queue_smart_link_context,
        )
        from apps.platform_runtime.smart_links_kernel import STATE_DSL_CONCERN_OPEN

        request = SimpleNamespace(
            school=SimpleNamespace(
                settings={"safeguarding": {"dsl_inbox": [_privilege_row(), _privilege_row()]}}
            )
        )
        ctx = build_operator_queue_smart_link_context(request)
        self.assertEqual(ctx["operator_queue_dsl_unacknowledged"], 0)
        self.assertNotEqual(ctx["operator_queue_smart_link_state"], STATE_DSL_CONCERN_OPEN)

    def test_real_concern_still_lights_dsl_banner(self):
        from apps.platform_runtime.operator_queue_signals import (
            build_operator_queue_smart_link_context,
        )
        from apps.platform_runtime.smart_links_kernel import STATE_DSL_CONCERN_OPEN

        request = SimpleNamespace(
            school=SimpleNamespace(
                settings={"safeguarding": {"dsl_inbox": _real_concern()}}
            )
        )
        ctx = build_operator_queue_smart_link_context(request)
        self.assertEqual(ctx["operator_queue_dsl_unacknowledged"], 1)
        self.assertEqual(ctx["operator_queue_smart_link_state"], STATE_DSL_CONCERN_OPEN)


class PrivilegeAuditTaskNamespacing(TestCase):
    def _school(self, *, safeguarding=None):
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        return School.objects.create(
            name=f"SG {uid}",
            slug=f"sg-{uid}",
            subdomain=f"sg-{uid}",
            is_active=True,
            settings={"safeguarding": safeguarding} if safeguarding else {},
        )

    def _reload_sg(self, school):
        school.refresh_from_db()
        return (school.settings or {}).get("safeguarding") or {}

    def test_task_relocates_legacy_privilege_rows_out_of_dsl_inbox(self):
        from apps.safeguarding.tasks import audit_privilege_context_task

        real = _real_concern(concern_id="keep-me")
        polluted = [_privilege_row()] + real + [_privilege_row(7)]
        school = self._school(safeguarding={"dsl_inbox": polluted})

        audit_privilege_context_task()

        sg = self._reload_sg(school)
        inbox = sg.get("dsl_inbox") or []
        # Only the real concern survives in the inbox.
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["concern_id"], "keep-me")
        # Both privilege rows relocated to the dedicated audit log.
        self.assertEqual(len(sg.get("privilege_audit_log") or []), 2)
        self.assertEqual(list_unacknowledged(inbox), inbox)

    def test_task_writes_new_stale_flag_to_audit_log_not_inbox(self):
        from django.contrib.auth import get_user_model

        from apps.schools.models import SchoolMembership
        from apps.safeguarding.tasks import audit_privilege_context_task

        User = get_user_model()
        school = self._school()
        admin = User.objects.create_user(username=f"a-{uuid.uuid4().hex[:6]}", password="pw")
        SchoolMembership.objects.create(user=admin, school=school, role="ADMIN")
        # Stale: last login well before the 24h cutoff.
        User.objects.filter(pk=admin.pk).update(
            last_login=timezone.now() - timedelta(days=3)
        )

        result = audit_privilege_context_task()
        self.assertGreaterEqual(result["schools_flagged"], 1)

        sg = self._reload_sg(school)
        # The stale-admin flag landed in the audit log, NOT the concern inbox.
        self.assertEqual(sg.get("dsl_inbox") or [], [])
        log = sg.get("privilege_audit_log") or []
        self.assertTrue(any(r.get("kind") == "privilege.stale_admin_login" for r in log))
