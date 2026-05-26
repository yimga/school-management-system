"""Wave J (v3.95.0 — 2026-05-26) — MAT Group Hub aggregator tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.mat_group_hub import (
    MATGroup,
    MATGroupKPISnapshot,
    MATMember,
    aggregate_group_kpis,
    all_member_tenant_slugs,
    find_group_by_id,
    member_count,
    parse_mat_registry,
)


def _group(group_id: str, members: list[tuple[str, str]]) -> MATGroup:
    return MATGroup(
        group_id=group_id,
        display_name=group_id,
        members=tuple(MATMember(tenant_slug=s, display_name=n) for s, n in members),
    )


class RegistryParserTests(SimpleTestCase):

    def test_parses_complete_group(self):
        raw = {
            "trust-1": {
                "display_name": "Trust One",
                "operator_email": "ops@one.example",
                "region": "UK-North",
                "members": [
                    {"tenant_slug": "a-school", "display_name": "A School", "region": "UK-North"},
                    {"tenant_slug": "b-school", "display_name": "B School"},
                ],
            },
        }
        groups = parse_mat_registry(raw)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g.group_id, "trust-1")
        self.assertEqual(g.display_name, "Trust One")
        self.assertEqual(g.operator_email, "ops@one.example")
        self.assertEqual(len(g.members), 2)
        self.assertEqual(g.members[0].tenant_slug, "a-school")

    def test_drops_group_with_no_members(self):
        raw = {"trust-empty": {"display_name": "Empty", "members": []}}
        self.assertEqual(parse_mat_registry(raw), ())

    def test_drops_member_without_slug(self):
        raw = {"trust-1": {"members": [{"display_name": "no slug"}, {"tenant_slug": "ok"}]}}
        groups = parse_mat_registry(raw)
        self.assertEqual(len(groups[0].members), 1)
        self.assertEqual(groups[0].members[0].tenant_slug, "ok")

    def test_handles_invalid_top_level(self):
        self.assertEqual(parse_mat_registry(None), ())
        self.assertEqual(parse_mat_registry("not a dict"), ())
        self.assertEqual(parse_mat_registry([]), ())

    def test_handles_invalid_payload(self):
        raw = {"trust-bad": "not a dict"}
        self.assertEqual(parse_mat_registry(raw), ())

    def test_handles_invalid_members_list(self):
        raw = {"trust-1": {"members": "not a list"}}
        self.assertEqual(parse_mat_registry(raw), ())


class AggregatorTests(SimpleTestCase):

    def setUp(self):
        self.group = _group("trust-1", [
            ("school-a", "A"), ("school-b", "B"), ("school-c", "C"),
        ])

    def test_aggregates_three_members(self):
        per_member_data = {
            "school-a": {
                "students": 500, "staff": 40, "admissions_pipeline": 25,
                "fees_collected_minor": 5_000_000, "fees_outstanding_minor": 500_000,
                "attendance_rate_pct": 92.0, "pass_rate_pct": 78.0,
            },
            "school-b": {
                "students": 800, "staff": 60, "admissions_pipeline": 40,
                "fees_collected_minor": 9_000_000, "fees_outstanding_minor": 1_000_000,
                "attendance_rate_pct": 94.0, "pass_rate_pct": 82.0,
            },
            "school-c": {
                "students": 300, "staff": 25, "admissions_pipeline": 12,
                "fees_collected_minor": 3_000_000, "fees_outstanding_minor": 200_000,
                "attendance_rate_pct": 90.0, "pass_rate_pct": 75.0,
            },
        }

        def runner(slug, _member):
            return per_member_data[slug]

        snap = aggregate_group_kpis(self.group, tenant_scope_runner=runner)

        self.assertIsInstance(snap, MATGroupKPISnapshot)
        self.assertEqual(snap.group_id, "trust-1")
        self.assertEqual(snap.member_count, 3)
        self.assertEqual(snap.total_students, 1600)
        self.assertEqual(snap.total_staff, 125)
        self.assertEqual(snap.admissions_pipeline_count, 77)
        self.assertEqual(snap.fees_collected_minor, 17_000_000)
        self.assertEqual(snap.fees_outstanding_minor, 1_700_000)
        self.assertAlmostEqual(snap.attendance_rate_pct, 92.0)
        self.assertAlmostEqual(snap.pass_rate_pct, 78.33)
        self.assertEqual(len(snap.per_member), 3)
        self.assertEqual(snap.failed_members, [])

    def test_failed_member_does_not_abort_rollup(self):
        def runner(slug, _member):
            if slug == "school-b":
                raise RuntimeError("DB exploded")
            return {"students": 100, "staff": 10, "admissions_pipeline": 5,
                    "fees_collected_minor": 1_000_000,
                    "fees_outstanding_minor": 100_000,
                    "attendance_rate_pct": 90.0, "pass_rate_pct": 80.0}

        snap = aggregate_group_kpis(self.group, tenant_scope_runner=runner)
        self.assertEqual(snap.total_students, 200)  # a + c only
        self.assertEqual(snap.failed_members, ["school-b"])
        # b record still in per_member with error tag.
        b = next(m for m in snap.per_member if m["tenant_slug"] == "school-b")
        self.assertIn("DB exploded", b["error"])

    def test_missing_metric_keys_default_to_zero(self):
        def runner(_slug, _member):
            return {"students": 100}  # everything else missing

        snap = aggregate_group_kpis(self.group, tenant_scope_runner=runner)
        self.assertEqual(snap.total_students, 300)
        self.assertEqual(snap.total_staff, 0)
        self.assertEqual(snap.fees_collected_minor, 0)

    def test_zero_attendance_rate_excluded_from_average(self):
        # When a school's attendance_rate is 0, it shouldn't drag the
        # group average down — exclude from the mean.
        def runner(slug, _member):
            return {"attendance_rate_pct": 95.0 if slug != "school-c" else 0.0}

        snap = aggregate_group_kpis(self.group, tenant_scope_runner=runner)
        # Only school-a + school-b contribute.
        self.assertAlmostEqual(snap.attendance_rate_pct, 95.0)

    def test_empty_group_returns_zero_snapshot(self):
        empty = _group("empty-trust", [])
        snap = aggregate_group_kpis(empty, tenant_scope_runner=lambda *_a, **_k: {})
        self.assertEqual(snap.member_count, 0)
        self.assertEqual(snap.total_students, 0)
        self.assertEqual(snap.attendance_rate_pct, 0.0)


class HelpersTests(SimpleTestCase):

    def test_find_group_by_id(self):
        groups = (
            _group("g1", [("a", "A")]),
            _group("g2", [("b", "B")]),
        )
        self.assertEqual(find_group_by_id(groups, "g2").group_id, "g2")
        self.assertIsNone(find_group_by_id(groups, "missing"))

    def test_member_count(self):
        g = _group("g", [("a", "A"), ("b", "B"), ("c", "C")])
        self.assertEqual(member_count(g), 3)

    def test_all_member_tenant_slugs_dedupes(self):
        groups = (
            _group("g1", [("a", "A"), ("b", "B")]),
            _group("g2", [("b", "B"), ("c", "C")]),  # b duplicated
        )
        slugs = all_member_tenant_slugs(groups)
        self.assertEqual(slugs, ("a", "b", "c"))
