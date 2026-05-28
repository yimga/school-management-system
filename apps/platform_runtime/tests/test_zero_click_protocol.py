"""Wave U (v3.99.0 — 2026-05-27) — Protocol Zero-Click-Intuition tests.

Covers the four pure-Python kernels that compose the protocol:
spacing_grid, table_grammar, empty_state, action_hub.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.action_hub_kernel import (
    HubAction,
    PERSONA_PARENT,
    build_parent_hub,
    build_student_hub,
    build_teacher_hub,
    build_tenant_admin_hub,
    empty_hub,
)
from apps.platform_runtime.empty_state_kernel import (
    EmptyStateCard,
    get_empty_state,
    list_registered_domains,
    list_registered_pairs,
)
from apps.platform_runtime.empty_state_kernel import PERSONA_TENANT_ADMIN as ES_ADMIN
from apps.platform_runtime.spacing_grid_kernel import (
    ALLOWED_VALUES_PX,
    SPACING_BASE_PX,
    list_allowed_pixel_values,
    snap_to_grid,
    validate_many,
    validate_spacing_value,
)
from apps.platform_runtime.table_grammar_kernel import (
    Column,
    MAX_PRIMARY_COLUMNS,
    PERSONA_PARENT as TG_PARENT,
    PERSONA_TEACHER as TG_TEACHER,
    PRIORITY_DRAWER_ONLY,
    PRIORITY_IDENTITY,
    PRIORITY_STATUS,
    build_columns_from_dicts,
    classify_column_priority,
    truncate_columns,
)


# ============== Spacing grid kernel ====================================== #


class SpacingGridTests(SimpleTestCase):
    def test_base_unit_is_8px(self) -> None:
        self.assertEqual(SPACING_BASE_PX, 8)

    def test_zero_is_allowed(self) -> None:
        self.assertTrue(validate_spacing_value(0).ok)
        self.assertTrue(validate_spacing_value("0px").ok)

    def test_canonical_values_accepted(self) -> None:
        for px in (8, 16, 24, 32, 48, 64):
            self.assertTrue(
                validate_spacing_value(px).ok,
                f"{px}px should be on the grid",
            )

    def test_string_px_accepted(self) -> None:
        result = validate_spacing_value("24px")
        self.assertTrue(result.ok)
        self.assertEqual(result.canonical_px, 24)

    def test_off_grid_rejected_with_nearest(self) -> None:
        result = validate_spacing_value("13px")
        self.assertFalse(result.ok)
        self.assertIn("16", result.reason)

    def test_negative_rejected(self) -> None:
        self.assertFalse(validate_spacing_value("-8px").ok)
        self.assertFalse(validate_spacing_value(-1).ok)

    def test_non_numeric_rejected(self) -> None:
        self.assertFalse(validate_spacing_value("auto").ok)
        self.assertFalse(validate_spacing_value("").ok)
        self.assertFalse(validate_spacing_value(None).ok)

    def test_snap_to_grid_rounds_up_on_tie(self) -> None:
        # 12px is equidistant between 8 and 16; pick 16 (more generous).
        self.assertEqual(snap_to_grid(12), 16)

    def test_snap_to_grid_clamps(self) -> None:
        # Beyond the largest allowed multiplier (128px), snap to that.
        biggest = max(ALLOWED_VALUES_PX)
        self.assertEqual(snap_to_grid(9999), biggest)
        self.assertEqual(snap_to_grid(-10), 0)

    def test_validate_many_returns_one_per_input(self) -> None:
        results = validate_many(["8px", "13px", "32px"])
        self.assertEqual([r.ok for r in results], [True, False, True])

    def test_list_allowed_pixel_values_sorted(self) -> None:
        values = list_allowed_pixel_values()
        self.assertEqual(values, sorted(values))
        self.assertIn(8, values)
        self.assertIn(16, values)


# ============== Table grammar kernel ===================================== #


class TableGrammarTests(SimpleTestCase):
    def test_max_primary_columns_is_5(self) -> None:
        # Protocol fixture.
        self.assertEqual(MAX_PRIMARY_COLUMNS, 5)

    def test_empty_input_returns_empty(self) -> None:
        result = truncate_columns([])
        self.assertEqual(result.visible_columns, ())
        self.assertEqual(result.drawer_columns, ())
        self.assertTrue(result.fits_without_drawer)

    def test_under_cap_renders_all_visible(self) -> None:
        cols = build_columns_from_dicts([
            {"key": "name"}, {"key": "status"}, {"key": "balance"},
        ])
        result = truncate_columns(cols)
        self.assertEqual(len(result.visible_columns), 3)
        self.assertEqual(result.drawer_columns, ())
        self.assertTrue(result.fits_without_drawer)

    def test_over_cap_overflows_to_drawer(self) -> None:
        cols = build_columns_from_dicts([
            {"key": "name"}, {"key": "status"}, {"key": "balance"},
            {"key": "class"}, {"key": "submitted"}, {"key": "notes"},
            {"key": "guardian"}, {"key": "phone"},
        ])
        result = truncate_columns(cols)
        self.assertEqual(len(result.visible_columns), 5)
        self.assertGreater(len(result.drawer_columns), 0)
        self.assertFalse(result.fits_without_drawer)

    def test_drawer_only_column_never_visible(self) -> None:
        cols = build_columns_from_dicts([
            {"key": "name"},
            {"key": "audit_log", "always_drawer": True},
        ])
        result = truncate_columns(cols)
        visible_keys = [c.key for c in result.visible_columns]
        self.assertIn("name", visible_keys)
        self.assertNotIn("audit_log", visible_keys)
        drawer_keys = [c.key for c in result.drawer_columns]
        self.assertIn("audit_log", drawer_keys)

    def test_classify_identity_for_name_keys(self) -> None:
        self.assertEqual(
            classify_column_priority(Column(key="student_name", label="Name")),
            PRIORITY_IDENTITY,
        )

    def test_classify_status_for_status_keys(self) -> None:
        self.assertEqual(
            classify_column_priority(Column(key="status", label="Status")),
            PRIORITY_STATUS,
        )

    def test_classify_drawer_only_for_audit_keys(self) -> None:
        self.assertEqual(
            classify_column_priority(Column(key="raw_audit_payload", label="Raw")),
            PRIORITY_DRAWER_ONLY,
        )

    def test_persona_override_hoists_column(self) -> None:
        col = Column(
            key="balance",
            label="Balance",
            priority=4,
            persona_overrides={TG_PARENT: 0},
        )
        self.assertEqual(classify_column_priority(col, persona=TG_PARENT), 0)
        # Without persona override, the base priority applies.
        self.assertEqual(classify_column_priority(col, persona=TG_TEACHER), 4)

    def test_explicit_priority_wins_over_heuristic(self) -> None:
        # Even though "status" hints at PRIORITY_STATUS, explicit beats hint.
        col = Column(key="status", label="Status", priority=PRIORITY_DRAWER_ONLY)
        self.assertEqual(classify_column_priority(col), PRIORITY_DRAWER_ONLY)

    def test_invalid_max_visible_raises(self) -> None:
        with self.assertRaises(ValueError):
            truncate_columns(build_columns_from_dicts([{"key": "a"}]), max_visible=0)

    def test_build_columns_requires_key(self) -> None:
        with self.assertRaises(ValueError):
            build_columns_from_dicts([{"label": "no key"}])

    def test_overflow_count_excludes_always_drawer(self) -> None:
        cols = build_columns_from_dicts([
            {"key": "name"},
            {"key": "notes", "always_drawer": True},
        ])
        result = truncate_columns(cols)
        # ``notes`` going to drawer is intentional, not an overflow.
        self.assertEqual(result.overflow_count, 0)


# ============== Empty-state kernel ======================================= #


class EmptyStateTests(SimpleTestCase):
    def test_card_requires_headline(self) -> None:
        with self.assertRaises(ValueError):
            EmptyStateCard(headline="", body="x")

    def test_card_rejects_unknown_severity(self) -> None:
        with self.assertRaises(ValueError):
            EmptyStateCard(headline="h", body="b", severity="catastrophic")

    def test_card_rejects_dual_cta_target(self) -> None:
        with self.assertRaises(ValueError):
            EmptyStateCard(
                headline="h",
                body="b",
                cta_label="X",
                cta_wizard_slug="some_slug",
                cta_url_name="some:name",
            )

    def test_admin_students_routes_to_csv_wizard(self) -> None:
        card = get_empty_state("students", persona=ES_ADMIN)
        self.assertIsNotNone(card)
        self.assertIn("import", card.cta_label.lower())
        self.assertTrue(card.cta_wizard_slug)

    def test_parent_invoices_celebrates_clear_balance(self) -> None:
        card = get_empty_state("invoices", persona="parent")
        self.assertIsNotNone(card)
        self.assertEqual(card.severity, "success")

    def test_safeguarding_clear_inbox_is_success(self) -> None:
        card = get_empty_state("safeguarding_concerns", persona=ES_ADMIN)
        self.assertIsNotNone(card)
        self.assertEqual(card.severity, "success")

    def test_unknown_domain_returns_none(self) -> None:
        self.assertIsNone(get_empty_state("does_not_exist"))

    def test_persona_fallback_to_any(self) -> None:
        # No (students, parent) entry registered — should NOT 500.
        card = get_empty_state("students", persona="parent")
        # parent has no override; might return None (no ANY either) — but the
        # contract is "don't crash".
        self.assertTrue(card is None or isinstance(card, EmptyStateCard))

    def test_registry_diagnostic_helpers(self) -> None:
        domains = list_registered_domains()
        pairs = list_registered_pairs()
        self.assertGreater(len(domains), 5)
        self.assertGreater(len(pairs), 5)


# ============== Action hub kernel ======================================== #


class ActionHubTests(SimpleTestCase):
    def test_hub_action_requires_label(self) -> None:
        with self.assertRaises(ValueError):
            HubAction(key="k", label="", url_name="x")

    def test_hub_action_requires_target(self) -> None:
        with self.assertRaises(ValueError):
            HubAction(key="k", label="X")

    def test_hub_action_rejects_negative_count(self) -> None:
        with self.assertRaises(ValueError):
            HubAction(key="k", label="X", url_name="x", count=-1)

    def test_hub_action_rejects_unknown_severity(self) -> None:
        with self.assertRaises(ValueError):
            HubAction(key="k", label="X", url_name="x", severity="catastrophic")

    def test_tenant_admin_hub_orders_urgent_first(self) -> None:
        hub = build_tenant_admin_hub(
            pending_admissions=3,
            urgent_dsl_inbox=1,
            overdue_invoices=8,
        )
        # The danger-severity DSL action must come first.
        self.assertGreater(len(hub.actions), 0)
        self.assertEqual(hub.actions[0].severity, "danger")
        self.assertEqual(hub.actions[0].key, "safeguarding.urgent")

    def test_tenant_admin_hub_skips_zero_counts(self) -> None:
        hub = build_tenant_admin_hub()
        non_empty = hub.non_empty_actions
        self.assertEqual(non_empty, ())

    def test_teacher_hub_shows_all_clear_when_pending_zero(self) -> None:
        hub = build_teacher_hub(classes_today=3, attendance_pending_classes=0)
        keys = {a.key for a in hub.actions}
        self.assertIn("day.clear", keys)

    def test_teacher_hub_warns_on_pending_attendance(self) -> None:
        hub = build_teacher_hub(classes_today=4, attendance_pending_classes=2)
        keys = {a.key for a in hub.actions}
        self.assertIn("attendance.pending", keys)

    def test_parent_hub_balance_label_includes_currency(self) -> None:
        hub = build_parent_hub(
            outstanding_balance_currency="$",
            outstanding_balance_amount="120.00",
        )
        self.assertGreater(len(hub.actions), 0)
        balance = next(a for a in hub.actions if a.key == "finance.balance")
        self.assertIn("$", balance.label)
        self.assertIn("120", balance.label)

    def test_parent_hub_records_hold_is_danger(self) -> None:
        hub = build_parent_hub(records_hold_active=True)
        keys_by_sev = {a.key: a.severity for a in hub.actions}
        self.assertEqual(keys_by_sev.get("records.hold"), "danger")

    def test_parent_hub_zero_balance_omits_chip(self) -> None:
        hub = build_parent_hub(outstanding_balance_amount="0")
        keys = {a.key for a in hub.actions}
        self.assertNotIn("finance.balance", keys)

    def test_student_hub_warns_on_homework_due(self) -> None:
        hub = build_student_hub(homework_due_count=5)
        keys_by_sev = {a.key: a.severity for a in hub.actions}
        self.assertEqual(keys_by_sev.get("homework.due"), "warning")

    def test_has_urgent_flag(self) -> None:
        hub = build_tenant_admin_hub(urgent_dsl_inbox=2)
        self.assertTrue(hub.has_urgent)
        hub_clear = build_tenant_admin_hub()
        self.assertFalse(hub_clear.has_urgent)

    def test_total_count_aggregates(self) -> None:
        hub = build_tenant_admin_hub(
            pending_admissions=3, urgent_dsl_inbox=1, overdue_invoices=8,
        )
        self.assertEqual(hub.total_count, 12)

    def test_empty_hub_factory(self) -> None:
        hub = empty_hub(persona=PERSONA_PARENT)
        self.assertEqual(hub.persona, PERSONA_PARENT)
        self.assertEqual(hub.actions, ())
        self.assertEqual(hub.total_count, 0)

    def test_hub_is_immutable(self) -> None:
        hub = build_tenant_admin_hub(pending_admissions=1)
        with self.assertRaises(Exception):
            hub.actions = ()  # type: ignore[misc]
