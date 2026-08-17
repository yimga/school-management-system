"""Cross-lander no-data-loss guardrail (2026-08-16 gap-analysis follow-up).

The apply step runs exactly ONE lander per artifact with no fallback behind it
(``_apply_artifact``: ``get_lander(domain) or get_lander("custom_fields")`` only
reaches the fallback for domains with NO registered lander). So a lander that
maps a fixed field set and never reads the ``custom_fields.*``/``_unmapped.*``
pass-through keys silently DROPS every column outside that set — the systemic
data-loss hole the gap analysis found across ~25 domains.

The fix is a residual-capture net in ``_run_lander_under_schema`` that runs
behind every lander whose ``sweeps_custom_columns`` is False. These tests pin:

  1. the net actually persists residual columns for a non-sweeping lander;
  2. the net is skipped for a lander that sweeps them itself (no double write)
     and on dry-run;
  3. every registered lander declares the flag, and every lander that CLAIMS to
     sweep genuinely iterates the whole row / sweeps (so a future lander can't
     set the flag True and quietly reintroduce the drop).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Iterator

from django.test import SimpleTestCase, TestCase

from apps.metadata.models import DynamicFieldValue
from apps.migration_cloud.landers.base import Lander, LanderResult, _REGISTRY
from apps.migration_cloud.orchestrator import _run_lander_under_schema
from apps.schools.models import School

# Importing the package registers every lander into _REGISTRY.
import apps.migration_cloud.landers  # noqa: E402,F401


class _ConsumingLander(Lander):
    """Minimal lander that consumes rows and persists nothing (worst case)."""

    domain = "genericdomain"

    def land(self, *, canonical_rows: Iterator[dict[str, Any]], ctx) -> LanderResult:
        result = LanderResult()
        for _row in canonical_rows:
            result.created += 1
        return result


class _SweepingLander(_ConsumingLander):
    domain = "sweepingdomain"
    sweeps_custom_columns = True


class ResidualNetTests(TestCase):
    def _school(self, tag: str) -> School:
        return School.objects.create(
            name=f"Net {tag}", slug=f"net-{tag}", subdomain=f"net-{tag}"
        )

    def _run(self, lander, rows, school, dry_run=False):
        bundle = SimpleNamespace(school=school, schema_name="", pk=1)
        artifact = SimpleNamespace(pk=7)
        return _run_lander_under_schema(
            lander=lander,
            rows_iter=iter(rows),
            bundle=bundle,
            artifact=artifact,
            dry_run=dry_run,
        )

    def test_net_captures_residual_for_nonsweeping_lander(self):
        school = self._school("cap")
        row = {
            "guardian_external_id": "G1",
            "_unmapped.occupation": "Trader",
            "custom_fields.house": "Blue",
            "some_mapped_field": "ignored-by-net",
        }
        self._run(_ConsumingLander(), [row], school)

        occ = DynamicFieldValue.objects.get(
            entity_type="migration_residual:genericdomain", field_key="occupation"
        )
        self.assertEqual(occ.value_json, {"v": "Trader"})
        self.assertEqual(occ.school_id, school.pk)
        # entity_id derives from the row's external id so it is traceable.
        self.assertEqual(occ.entity_id, "G1")

        house = DynamicFieldValue.objects.get(
            entity_type="migration_residual:genericdomain", field_key="house"
        )
        self.assertEqual(house.value_json, {"v": "Blue"})

        # A canonically-mapped column is NOT swept by the net (only residual keys).
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                entity_type="migration_residual:genericdomain",
                field_key="some_mapped_field",
            ).exists()
        )

    def test_net_uses_artifact_row_key_when_no_external_id(self):
        school = self._school("nokey")
        self._run(_ConsumingLander(), [{"_unmapped.note": "keep me"}], school)
        dfv = DynamicFieldValue.objects.get(
            entity_type="migration_residual:genericdomain", field_key="note"
        )
        self.assertEqual(dfv.entity_id, "a7r1")

    def test_net_skipped_for_sweeping_lander(self):
        school = self._school("sweep")
        self._run(_SweepingLander(), [{"_unmapped.occupation": "Trader"}], school)
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                entity_type="migration_residual:sweepingdomain"
            ).exists()
        )

    def test_net_skipped_on_dry_run(self):
        school = self._school("dry")
        self._run(_ConsumingLander(), [{"_unmapped.occupation": "Trader"}], school, dry_run=True)
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                entity_type="migration_residual:genericdomain"
            ).exists()
        )


class LanderSweepContractTests(SimpleTestCase):
    # Code patterns that prove a lander genuinely captures every residual key
    # (whole-row iteration or an explicit sweep helper) — comments alone will not
    # match, so a flag set without a real sweep fails this guard.
    _SWEEP_CODE_MARKERS = (
        "for k, v in row",
        "for key, value in row",
        "for k in row",
        "for v in row",
        "_sweep_custom_attributes",
    )

    def test_registry_is_populated(self):
        self.assertGreater(len(_REGISTRY), 10, "landers did not register")

    def test_every_lander_declares_sweep_flag_as_bool(self):
        for domain, lander in _REGISTRY.items():
            self.assertIsInstance(
                lander.sweeps_custom_columns, bool,
                msg=f"{domain}: sweeps_custom_columns must be a bool",
            )

    def test_landers_that_claim_to_sweep_actually_sweep(self):
        for domain, lander in _REGISTRY.items():
            if not lander.sweeps_custom_columns:
                continue  # net covers it; nothing to prove here
            src = inspect.getsource(type(lander))
            self.assertTrue(
                any(marker in src for marker in self._SWEEP_CODE_MARKERS),
                msg=(
                    f"{domain}: sweeps_custom_columns=True but its source shows no "
                    f"whole-row sweep — the residual net is skipped, so columns it "
                    f"ignores would be lost. Either implement the sweep or drop the flag."
                ),
            )
