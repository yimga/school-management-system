"""Support co-pilot risk-signal producer — TenantRiskAlert + TenantInterventionSuggestion.

Regression guard for the dormant-feature fix: the two models the support co-pilot
reads had no writer anywhere in the repo, so risk/intervention suggestions could
never appear. sync_tenant_risk_signals derives them from the already-computed
health dimensions; these tests pin the firing bands, idempotency, the
recovery/auto-resolve loop, actionable links, and the ensure_health_score_record
integration.
"""

from django.test import TestCase
from django.utils import timezone

from apps.customersuccess.models import (
    TenantInterventionSuggestion,
    TenantRiskAlert,
)
from apps.customersuccess.services import (
    ensure_health_score_record,
    get_support_copilot_suggestions,
    sync_tenant_risk_signals,
)
from apps.schools.models import School


def _school(slug):
    return School.objects.create(
        name=slug,
        slug=slug,
        subdomain=slug,
        is_active=True,
        created_at=timezone.now(),
    )


class SyncTenantRiskSignalsTests(TestCase):
    def test_red_band_creates_alert_and_intervention(self):
        school = _school("red-band")
        result = sync_tenant_risk_signals(
            school, {"activity": 20, "workflows": 20, "adoption": 20}
        )
        self.assertEqual(result["alerts_created"], 3)
        self.assertEqual(result["interventions_created"], 3)
        self.assertEqual(
            TenantRiskAlert.objects.filter(
                school=school, severity=TenantRiskAlert.Severity.RED
            ).count(),
            3,
        )
        # Paired interventions carry priority 1 (highest) for RED.
        self.assertEqual(
            TenantInterventionSuggestion.objects.filter(
                school=school, priority=1
            ).count(),
            3,
        )

    def test_amber_band(self):
        school = _school("amber-band")
        sync_tenant_risk_signals(school, {"activity": 40, "workflows": 100, "adoption": 100})
        self.assertEqual(
            TenantRiskAlert.objects.filter(
                school=school, severity=TenantRiskAlert.Severity.AMBER
            ).count(),
            1,
        )
        self.assertEqual(TenantInterventionSuggestion.objects.filter(school=school).count(), 1)

    def test_healthy_dimensions_create_nothing(self):
        school = _school("healthy")
        result = sync_tenant_risk_signals(
            school, {"activity": 100, "workflows": 100, "adoption": 100}
        )
        self.assertEqual(result["alerts_created"], 0)
        self.assertEqual(result["interventions_created"], 0)
        self.assertEqual(TenantRiskAlert.objects.filter(school=school).count(), 0)

    def test_idempotent_no_duplicates_while_open(self):
        school = _school("idempotent")
        sync_tenant_risk_signals(school, {"activity": 20, "workflows": 20, "adoption": 20})
        # Second run with the same firing signals must not duplicate open rows.
        result = sync_tenant_risk_signals(
            school, {"activity": 20, "workflows": 20, "adoption": 20}
        )
        self.assertEqual(result["alerts_created"], 0)
        self.assertEqual(result["interventions_created"], 0)
        self.assertEqual(TenantRiskAlert.objects.filter(school=school).count(), 3)
        self.assertEqual(TenantInterventionSuggestion.objects.filter(school=school).count(), 3)

    def test_recovery_auto_resolves_open_rows(self):
        school = _school("recovery")
        sync_tenant_risk_signals(school, {"activity": 20, "workflows": 20, "adoption": 20})
        # Signals all healthy again -> open rows auto-resolve (system, no actor).
        result = sync_tenant_risk_signals(
            school, {"activity": 100, "workflows": 100, "adoption": 100}
        )
        self.assertEqual(result["alerts_resolved"], 3)
        self.assertEqual(result["interventions_resolved"], 3)
        self.assertEqual(
            TenantRiskAlert.objects.filter(
                school=school, acknowledged_at__isnull=True
            ).count(),
            0,
        )
        self.assertEqual(
            TenantInterventionSuggestion.objects.filter(
                school=school, dismissed_at__isnull=True
            ).count(),
            0,
        )
        # System resolution leaves the actor null (distinguishable from manual).
        self.assertIsNone(
            TenantRiskAlert.objects.filter(school=school).first().acknowledged_by_id
        )

    def test_missing_dimension_resolves_then_silent(self):
        school = _school("missing-dim")
        # adoption absent -> not firing -> nothing for that signal.
        result = sync_tenant_risk_signals(school, {"activity": 100, "workflows": 100})
        self.assertEqual(result["alerts_created"], 0)
        self.assertEqual(result["alerts_resolved"], 0)

    def test_acknowledged_alert_can_recur(self):
        school = _school("recur")
        sync_tenant_risk_signals(school, {"activity": 20, "workflows": 100, "adoption": 100})
        TenantRiskAlert.objects.filter(school=school).update(
            acknowledged_at=timezone.now()
        )
        # Once acknowledged, a still-firing signal raises a fresh alert.
        result = sync_tenant_risk_signals(
            school, {"activity": 20, "workflows": 100, "adoption": 100}
        )
        self.assertEqual(result["alerts_created"], 1)
        self.assertEqual(TenantRiskAlert.objects.filter(school=school).count(), 2)

    def test_non_dict_dimensions_safe(self):
        school = _school("nondict")
        self.assertEqual(
            sync_tenant_risk_signals(school, None),
            {
                "alerts_created": 0,
                "interventions_created": 0,
                "alerts_resolved": 0,
                "interventions_resolved": 0,
            },
        )

    def test_ensure_health_score_record_drives_signals(self):
        # A brand-new school has no last_activity -> activity dimension = 10 (RED),
        # so the create path must surface at least the dormant-activity alert.
        school = _school("integration")
        record = ensure_health_score_record(school)
        self.assertIsNotNone(record)
        self.assertTrue(
            TenantRiskAlert.objects.filter(
                school=school, payload__signal_key="activity_dormant"
            ).exists()
        )

    def test_sweep_task_produces_signals_end_to_end(self):
        # Seal the real production entry path: the beat-scheduled sweep task must
        # drive the producer, not just the service helper. An inactive school
        # (activity dimension RED) must end up with a risk alert after the sweep.
        from apps.customersuccess.tasks import sweep_tenant_health_scores

        school = _school("sweep-path")
        result = sweep_tenant_health_scores()
        self.assertGreaterEqual(result.get("updated", 0), 1)
        self.assertTrue(
            TenantRiskAlert.objects.filter(
                school=school, payload__signal_key="activity_dormant"
            ).exists()
        )

    def test_support_copilot_surfaces_actionable_link(self):
        school = _school("links")
        sync_tenant_risk_signals(school, {"activity": 100, "workflows": 100, "adoption": 20})
        suggestions = get_support_copilot_suggestions(school)
        # The low-adoption intervention must carry a resolvable "Open" link.
        adoption_items = [
            s for s in suggestions if s.get("link") and "onboarding" in s["link"]
        ]
        self.assertTrue(adoption_items, suggestions)
