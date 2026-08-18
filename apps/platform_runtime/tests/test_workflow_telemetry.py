"""Record-level workflow telemetry — Decimal math, tenant rooms, serialize, sockets."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from apps.platform_runtime.workflow_telemetry import (
    LOG_HISTORY_CAP,
    TASK_EOY_ROLLOVER,
    append_log_history,
    compute_percent_complete,
    enqueue_background_job,
    update_and_broadcast_progress,
    workflow_telemetry_room_name,
)


class WorkflowTelemetryMathTests(SimpleTestCase):
    def test_percent_is_decimal_never_float(self):
        pct = compute_percent_complete(1, 3)
        self.assertIsInstance(pct, Decimal)
        self.assertNotIsInstance(pct, float)
        self.assertEqual(pct, Decimal("33.33"))

    def test_percent_caps_at_one_hundred(self):
        self.assertEqual(compute_percent_complete(12, 10), Decimal("100.00"))

    def test_zero_expected_does_not_divide_by_zero(self):
        self.assertEqual(compute_percent_complete(0, 0), Decimal("0.00"))
        self.assertEqual(compute_percent_complete(1, 0), Decimal("100.00"))

    def test_log_history_caps_at_ten(self):
        history = []
        for index in range(14):
            history = append_log_history(history, f"line {index}")
        self.assertEqual(len(history), LOG_HISTORY_CAP)
        self.assertTrue(history[0].endswith("line 4"))
        self.assertTrue(history[-1].endswith("line 13"))


class WorkflowTelemetryRoomTests(SimpleTestCase):
    def test_rooms_differ_by_school_id(self):
        self.assertEqual(workflow_telemetry_room_name(11), "school-11-workflow-telemetry")
        self.assertNotEqual(
            workflow_telemetry_room_name(11),
            workflow_telemetry_room_name(22),
        )


class WorkflowTelemetrySerializeTests(SimpleTestCase):
    def test_serialize_prefers_telemetry_percent(self):
        from apps.platform_runtime.workflow_tracker import serialize_workflow_run

        run = SimpleNamespace(
            pk=41,
            workflow_key="accounts-rollover",
            workflow_label="Academic year rollover",
            current_step_ordinal=1,
            current_step_name="place_students",
            total_steps=2,
            started_at=None,
            expected_duration_seconds=30,
            tenant_schema="demo",
            school_id="7",
            suggested_remediation={},
            payload_summary={
                "telemetry": {
                    "records_expected": 10,
                    "records_processed": 4,
                    "percent_complete": "40.00",
                    "task_type": TASK_EOY_ROLLOVER,
                    "log_history": ["[12:00:00] Processed student record 4 of 10"],
                }
            },
        )
        with (
            mock.patch(
                "apps.platform_runtime.workflow_degrading.resolve_display_status",
                return_value="running",
            ),
            mock.patch(
                "apps.platform_runtime.workflow_status_taxonomy.status_meta",
                return_value={"label": "Running"},
            ),
            mock.patch(
                "apps.platform_runtime.workflow_sla.sla_meta_for_run",
                return_value={},
            ),
        ):
            payload = serialize_workflow_run(run)
        self.assertEqual(payload["progress_percent"], 40)
        self.assertEqual(payload["records_processed"], 4)
        self.assertEqual(payload["records_expected"], 10)
        self.assertEqual(payload["percent_complete"], "40.00")
        self.assertEqual(payload["task_type"], TASK_EOY_ROLLOVER)


class WorkflowTelemetryBroadcastTests(SimpleTestCase):
    def test_frame_percent_is_string_not_float(self):
        with (
            mock.patch(
                "apps.platform_runtime.workflow_telemetry._persist_telemetry"
            ),
            mock.patch(
                "apps.platform_runtime.workflow_telemetry._broadcast",
                return_value=1,
            ),
            mock.patch(
                "apps.platform_runtime.workflow_tracker.active_workflow_run",
                return_value=None,
            ),
        ):
            frame = update_and_broadcast_progress(
                processed=2,
                expected=8,
                log_message="Processed row 2 of 8",
                school_id="3",
                task_type=TASK_EOY_ROLLOVER,
            )
        percent = frame["payload"]["percent_complete"]
        self.assertIsInstance(percent, str)
        self.assertNotIsInstance(percent, float)
        self.assertEqual(percent, "25.00")
        self.assertEqual(frame["payload"]["current_status"], "running")


class WorkflowTelemetryConsumerTests(SimpleTestCase):
    def test_room_comes_from_scope_not_client(self):
        from apps.api import consumers

        consumer = consumers.WorkflowTelemetryConsumer()
        consumer.scope = {
            "school_access_denied": False,
            "school_id": "91",
            "user": SimpleNamespace(is_authenticated=True),
        }
        self.assertEqual(
            consumer.resolve_room_group_name(),
            workflow_telemetry_room_name("91"),
        )
        consumer.scope["school_id"] = "92"
        self.assertEqual(
            consumer.resolve_room_group_name(),
            workflow_telemetry_room_name("92"),
        )

    def test_unauthenticated_connect_closes_4401(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")

        async def _run():
            consumer = consumers.WorkflowTelemetryConsumer()
            consumer.scope = {
                "user": AnonymousUser(),
                "school_id": "1",
                "school_access_denied": False,
            }
            consumer.close = AsyncMock()
            consumer.channel_layer = mock.Mock()
            consumer.channel_name = "test.chan"
            await consumer.connect()
            consumer.close.assert_awaited_once_with(code=4401)

        asyncio.run(_run())

    def test_denied_scope_resolves_none(self):
        from apps.api import consumers

        consumer = consumers.WorkflowTelemetryConsumer()
        consumer.scope = {
            "school_access_denied": True,
            "school_id": "1",
            "user": SimpleNamespace(is_authenticated=True),
        }
        self.assertIsNone(consumer.resolve_room_group_name())

    def test_handler_forwards_progress_frame(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")

        async def _run():
            consumer = consumers.WorkflowTelemetryConsumer()
            consumer.send = AsyncMock()
            await consumer.workflow_progress_update(
                {
                    "event_type": "WORKFLOW_PROGRESS_UPDATE",
                    "emitted_at": "2026-08-17T12:00:00+00:00",
                    "payload": {"processed_count": 1, "expected_count": 2},
                }
            )
            frame = json.loads(consumer.send.await_args.kwargs["text_data"])
            self.assertEqual(frame["event_type"], "WORKFLOW_PROGRESS_UPDATE")
            self.assertEqual(frame["payload"]["processed_count"], 1)

        asyncio.run(_run())


class WorkflowTelemetryJobHookTests(SimpleTestCase):
    def test_migration_emit_fans_telemetry(self):
        from apps.migration_cloud import progress as progress_mod

        bundle = SimpleNamespace(school_id=44)
        qs = mock.Mock()
        qs.only.return_value.first.return_value = bundle
        with (
            mock.patch.object(progress_mod.MigrationProgressEvent.objects, "create"),
            mock.patch.object(
                progress_mod.MigrationBundle.objects, "filter", return_value=qs
            ),
            mock.patch(
                "apps.platform_runtime.workflow_telemetry.update_and_broadcast_progress"
            ) as broadcast,
        ):
            progress_mod.emit(
                bundle_id=9,
                kind="stage_finished",
                stage="INGESTING",
                message="Ingest complete",
                detail={"rows": 40, "expected": 80},
            )
        broadcast.assert_called_once()
        kwargs = broadcast.call_args.kwargs
        self.assertEqual(kwargs["school_id"], "44")
        self.assertEqual(kwargs["processed"], 40)
        self.assertEqual(kwargs["expected"], 80)
        self.assertEqual(kwargs["workflow_key"], "migration_bundle_apply")

    def test_procurement_scan_empty_inventory_still_broadcasts(self):
        from apps.schoolops.procurement_loop import run_school_procurement_scan

        school = SimpleNamespace(pk=5)
        empty_qs = mock.Mock()
        empty_qs.order_by.return_value = []
        with (
            mock.patch(
                "apps.schoolops.models.InventoryItem.objects.filter",
                return_value=empty_qs,
            ),
            mock.patch(
                "apps.platform_runtime.workflow_tracker.ensure_workflow_run"
            ) as ensure,
            mock.patch(
                "apps.platform_runtime.workflow_telemetry.update_and_broadcast_progress"
            ) as broadcast,
        ):
            ensure.return_value.__enter__ = mock.Mock(return_value=None)
            ensure.return_value.__exit__ = mock.Mock(return_value=False)
            summary = run_school_procurement_scan(school)
        self.assertEqual(summary["scanned"], 0)
        broadcast.assert_called()
        self.assertEqual(broadcast.call_args.kwargs["status"], "succeeded")

    def test_sync_rollover_and_ortools_accept_progress_hooks(self):
        import ast
        from inspect import signature

        from apps.academics.scheduling_solver import (
            _solve_with_ortools,
            generate_timetable_with_solver,
        )

        self.assertIn("on_progress", signature(generate_timetable_with_solver).parameters)
        self.assertIn("on_progress", signature(_solve_with_ortools).parameters)
        tree = ast.parse(
            (
                Path(__file__).resolve().parents[3]
                / "apps"
                / "accounts"
                / "views_rollover.py"
            ).read_text(encoding="utf-8")
        )
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertIn("update_and_broadcast_progress", names)
        self.assertIn("ensure_workflow_run", names)

    def test_enqueue_falls_back_to_apply(self):
        task = mock.Mock()
        task.apply_async.side_effect = RuntimeError("broker down")
        task.apply.return_value = SimpleNamespace(ready=lambda: True)
        result = enqueue_background_job(task, 7, use_ortools=True)
        task.apply.assert_called_once()
        self.assertTrue(result.ready())

    def test_http_jobs_queue_background_work(self):
        import ast

        root = Path(__file__).resolve().parents[3]
        timetable = ast.parse(
            (root / "apps" / "academics" / "views_timetable.py").read_text(
                encoding="utf-8"
            )
        )
        inventory = ast.parse(
            (root / "apps" / "schoolops" / "views_tenant_ops.py").read_text(
                encoding="utf-8"
            )
        )
        timetable_names = {
            node.id for node in ast.walk(timetable) if isinstance(node, ast.Name)
        }
        inventory_names = {
            node.id for node in ast.walk(inventory) if isinstance(node, ast.Name)
        }
        self.assertIn("enqueue_background_job", timetable_names)
        self.assertIn("run_scheduling_solver_task", timetable_names)
        self.assertIn("run_procurement_scan_task", inventory_names)
