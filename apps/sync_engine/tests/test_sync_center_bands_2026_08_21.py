"""The Sync Center rebuild: one fact, one place — and a strip that cannot lie.

TWO THINGS ARE UNDER TEST HERE, and only one of them is new behaviour.

The first is the WEEK PLAN — ``week_plan`` / ``longest_gap`` / ``next_runs`` /
``dst_note_for_rule``. These are new, pure, and the panel draws directly from them, so
they are tested the way the rest of ``schedule.py`` is: with a frozen clock and a real
timezone, asserting instants rather than prose.

The second is a REGRESSION SEAL, and it is the reason this file exists at all. The page
was long because five separate facts rendered twice — last sync, next sync, recent cycles,
pushed/pulled and the conflict count — and one of those pairs (the two "next"s) could
legitimately DISAGREE, because one was the next occurrence of a schedule RULE and the
other was the next moment CADENCE was due. Nothing on screen said so. That class of
duplication is invisible in review: each copy looks correct on its own, and the second one
is usually added by somebody who could not find the first. So the seal asserts the
NEGATIVE — that the retired duplicate hooks are gone and the surviving ones appear exactly
once — because a count is the only thing that catches a third copy being added later.
"""
from __future__ import annotations

import datetime as dt
import os
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.sync_engine.schedule import (
    MODE_AT_TIMES,
    MODE_INTERVAL,
    Rule,
    dst_note_for_rule,
    longest_gap,
    next_runs,
    week_plan,
)

_ACCRA = ZoneInfo("Africa/Accra")        # no DST, ever
_LONDON = ZoneInfo("Europe/London")      # DST, both directions
# A Monday, so weekday indexing in the assertions is readable.
_MONDAY = dt.datetime(2026, 8, 17, 0, 0, tzinfo=dt.timezone.utc)

_TERM = Rule(
    mode=MODE_INTERVAL,
    days=frozenset({0, 1, 2, 3, 4}),
    window_start=dt.time(6, 0),
    window_end=dt.time(18, 0),
    interval_minutes=30,
    label="Term time",
)
_NIGHTLY = Rule(
    mode=MODE_AT_TIMES,
    days=frozenset(range(7)),
    times=(dt.time(22, 0),),
    label="Nightly catch-up",
)


class WeekPlanTests(SimpleTestCase):
    """What the strip draws, asserted as data rather than as pixels."""

    def test_01_a_week_is_seven_days_of_twenty_four_hours(self):
        plan = week_plan([_TERM, _NIGHTLY], start=_MONDAY, tz=_ACCRA)
        self.assertEqual(len(plan["days"]), 7)
        for day in plan["days"]:
            self.assertEqual(len(day["hours"]), 24, day["date"])

    def test_02_the_total_is_every_occurrence_not_every_busy_hour(self):
        """25 firings a day Mon-Fri (06:00..18:00 inclusive, every 30m) plus 7 nightly."""
        plan = week_plan([_TERM, _NIGHTLY], start=_MONDAY, tz=_ACCRA)
        self.assertEqual(plan["total"], 25 * 5 + 7)

    def test_03_overlapping_rules_raise_the_level_of_the_hour_they_share(self):
        """Two rules in one hour must be DARKER than one, or the strip cannot show overlap."""
        clash = Rule(
            mode=MODE_AT_TIMES,
            days=frozenset({0}),
            times=(dt.time(6, 15),),
            label="Extra",
        )
        plan = week_plan([_TERM, clash], start=_MONDAY, tz=_ACCRA)
        hour = plan["days"][0]["hours"][6]
        self.assertEqual(hour["count"], 3)  # 06:00, 06:15, 06:30
        self.assertEqual(sorted(hour["rules"]), [0, 1])
        self.assertGreater(hour["level"], plan["days"][0]["hours"][7]["level"])

    def test_04_level_is_clamped_so_a_five_minute_rule_still_shows_shape(self):
        """Without the clamp a frequent rule paints every hour solid and overlap vanishes."""
        dense = Rule(
            mode=MODE_INTERVAL,
            days=frozenset({0}),
            window_start=dt.time(0, 0),
            window_end=dt.time(23, 59),
            interval_minutes=5,
            label="Dense",
        )
        plan = week_plan([dense], start=_MONDAY, tz=_ACCRA)
        hour = plan["days"][0]["hours"][3]
        self.assertEqual(hour["count"], 12)
        self.assertEqual(hour["level"], 4)

    def test_05_an_overnight_rule_fills_both_sides_of_midnight(self):
        """A 22:00-02:00 window is ONE window. Bucketing by the day whose window OPENED
        would leave a phantom gap in Tuesday's early hours."""
        overnight = Rule(
            mode=MODE_INTERVAL,
            days=frozenset({0}),
            window_start=dt.time(22, 0),
            window_end=dt.time(2, 0),
            interval_minutes=60,
            label="Overnight",
        )
        plan = week_plan([overnight], start=_MONDAY, tz=_ACCRA)
        self.assertEqual(plan["days"][0]["hours"][22]["count"], 1)
        for hour in (0, 1, 2):
            self.assertEqual(plan["days"][1]["hours"][hour]["count"], 1, hour)

    def test_06_no_rules_is_an_empty_grid_not_an_error(self):
        plan = week_plan([], start=_MONDAY, tz=_ACCRA)
        self.assertEqual(plan["total"], 0)
        self.assertEqual(plan["rule_count"], 0)
        self.assertEqual(len(plan["days"]), 7)

    def test_07_an_aware_start_is_required(self):
        with self.assertRaises(ValueError):
            week_plan([_TERM], start=dt.datetime(2026, 8, 17), tz=_ACCRA)


class LongestGapTests(SimpleTestCase):
    """The audit question, reduced to one number."""

    def test_08_the_weekend_hole_is_found(self):
        """Term time is Mon-Fri; the only weekend sync is 22:00 nightly, so the longest
        silence is Friday 22:00 to Saturday 22:00."""
        gap = longest_gap([_TERM, _NIGHTLY], start=_MONDAY, tz=_ACCRA)
        self.assertFalse(gap["unbounded"])
        self.assertEqual(gap["minutes"], 24 * 60)

    def test_09_a_single_weekly_run_reports_a_week_not_zero(self):
        """Without the wrap, one occurrence has no consecutive pair and reports 0 — which
        would tell a school with ONE weekly sync that it has no gap at all."""
        solo = Rule(mode=MODE_AT_TIMES, days=frozenset({0}), times=(dt.time(6, 0),))
        gap = longest_gap([solo], start=_MONDAY, tz=_ACCRA)
        self.assertEqual(gap["minutes"], 7 * 24 * 60)

    def test_10_no_rules_is_unbounded_and_that_is_not_a_fault(self):
        """A tenant with no rules is on the adaptive cadence BY CHOICE — the
        zero-configuration default. Reporting that as a seven-day hole would cry wolf."""
        gap = longest_gap([], start=_MONDAY, tz=_ACCRA)
        self.assertTrue(gap["unbounded"])
        self.assertIsNone(gap["minutes"])

    def test_11_a_dense_rule_has_a_gap_of_its_own_interval(self):
        every_hour = Rule(
            mode=MODE_INTERVAL,
            days=frozenset(range(7)),
            window_start=dt.time(0, 0),
            window_end=dt.time(23, 0),
            interval_minutes=60,
        )
        gap = longest_gap([every_hour], start=_MONDAY, tz=_ACCRA)
        self.assertEqual(gap["minutes"], 60)


class NextRunsTests(SimpleTestCase):
    """Five, not one — because one cannot show that a schedule is armed WRONG."""

    def test_12_it_returns_five_ascending_instants(self):
        runs = next_runs([_TERM, _NIGHTLY], after=_MONDAY, tz=_ACCRA)
        self.assertEqual(len(runs), 5)
        stamps = [dt.datetime.fromisoformat(r["at"]) for r in runs]
        self.assertEqual(stamps, sorted(stamps))

    def test_13_each_entry_names_the_rule_that_owns_it(self):
        runs = next_runs([_TERM, _NIGHTLY], after=_MONDAY, tz=_ACCRA)
        self.assertEqual(runs[0]["label"], "Term time")
        labels = {r["label"] for r in runs}
        self.assertTrue(labels.issubset({"Term time", "Nightly catch-up"}), labels)

    def test_14_no_rules_returns_an_empty_list_never_a_fabricated_time(self):
        self.assertEqual(next_runs([], after=_MONDAY, tz=_ACCRA), [])

    def test_15_it_agrees_with_the_scheduler_rather_than_re_deriving(self):
        """The first entry must be exactly what next_run_at would decide, or the panel is
        promising a moment the box will not keep."""
        from apps.sync_engine.schedule import next_run_at

        runs = next_runs([_TERM, _NIGHTLY], after=_MONDAY, tz=_ACCRA)
        expected = next_run_at([_TERM, _NIGHTLY], after=_MONDAY, tz=_ACCRA)
        self.assertEqual(dt.datetime.fromisoformat(runs[0]["at"]), expected)


class RuleLevelDstNoteTests(SimpleTestCase):
    """The clock-change note belongs to the rule it affects, not to the page."""

    def setUp(self):
        from apps.sync_engine.schedule import next_dst_transition

        self.after = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
        self.transition = next_dst_transition(_LONDON, after=self.after)
        self.weekday = self.transition["at"].astimezone(_LONDON).date().weekday()

    def test_16_a_rule_inside_the_skipped_hour_gets_the_note(self):
        inside = Rule(
            mode=MODE_AT_TIMES,
            days=frozenset({self.weekday}),
            times=(dt.time(1, 30),),
        )
        note = dst_note_for_rule(inside, _LONDON, after=self.after)
        self.assertIn("clocks go forward", note)
        self.assertIn("never dropped", note)

    def test_17_a_rule_outside_the_band_gets_nothing(self):
        outside = Rule(
            mode=MODE_AT_TIMES,
            days=frozenset({self.weekday}),
            times=(dt.time(9, 0),),
        )
        self.assertEqual(dst_note_for_rule(outside, _LONDON, after=self.after), "")

    def test_18_a_rule_on_another_weekday_gets_nothing(self):
        other = Rule(
            mode=MODE_AT_TIMES,
            days=frozenset({(self.weekday + 1) % 7}),
            times=(dt.time(1, 30),),
        )
        self.assertEqual(dst_note_for_rule(other, _LONDON, after=self.after), "")

    def test_19_a_zone_without_dst_never_produces_a_note(self):
        """Telling a school in Accra about clock changes is noise, every day of the year."""
        inside = Rule(
            mode=MODE_AT_TIMES,
            days=frozenset(range(7)),
            times=(dt.time(1, 30),),
        )
        self.assertEqual(dst_note_for_rule(inside, _ACCRA, after=self.after), "")

    def test_20_an_interval_window_spanning_the_band_is_affected(self):
        window = Rule(
            mode=MODE_INTERVAL,
            days=frozenset({self.weekday}),
            window_start=dt.time(0, 0),
            window_end=dt.time(6, 0),
            interval_minutes=30,
        )
        self.assertNotEqual(dst_note_for_rule(window, _LONDON, after=self.after), "")


class GapThresholdTests(SimpleTestCase):
    """A gap is REPORTED always and PAINTED as a problem only past the threshold."""

    def test_21_the_threshold_is_a_multiple_of_the_check_in_floor(self):
        from apps.sync_engine import schedule_policy

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RMC_EDGE_SYNC_GAP_FLAG_MULTIPLE", None)
            self.assertEqual(schedule_policy._gap_flag_multiple(), 4)

    def test_22_an_operator_can_pin_the_multiple(self):
        """A deployment with a deliberately sparse schedule must be able to stop the panel
        crying wolf without a code change and without touching the tenant's data."""
        from apps.sync_engine import schedule_policy

        with mock.patch.dict(os.environ, {"RMC_EDGE_SYNC_GAP_FLAG_MULTIPLE": "12"}):
            self.assertEqual(schedule_policy._gap_flag_multiple(), 12)

    def test_23_a_nonsense_pin_falls_back_rather_than_raising(self):
        from apps.sync_engine import schedule_policy

        for bad in ("banana", "0", "-3", ""):
            with mock.patch.dict(os.environ, {"RMC_EDGE_SYNC_GAP_FLAG_MULTIPLE": bad}):
                self.assertEqual(schedule_policy._gap_flag_multiple(), 4, bad)


_HOST = "sync-bands.runmycampus.com"
# Its own host, because request.school is resolved from the SUBDOMAIN. Sharing a host
# across two classes with two schools means the second one's requests never reach the
# view at all.
_PREVIEW_HOST = "sync-preview.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST])
class SyncCenterPageTests(TestCase):
    """The seal. What renders, what does NOT, and how many times."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import Permission as FeaturePermission, User
        from apps.schools.models import School, SchoolMembership

        cls.school = School.objects.create(
            name="Sync Bands School",
            slug="sync-bands",
            subdomain="sync-bands",
            is_active=True,
        )
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )
        cls.admin = User.objects.create_user(
            username="sync_bands_admin", password="x" * 12, role=User.Role.ADMIN
        )
        cls.admin.feature_permissions.add(perm)
        SchoolMembership.objects.create(
            user=cls.admin, school=cls.school, role=User.Role.ADMIN, is_primary=True
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_HOST)
        self.client.login(username="sync_bands_admin", password="x" * 12)

    def _page(self):
        resp = self.client.get(reverse("siteconfig:sync_center"))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode("utf-8")

    def test_24_every_band_renders(self):
        body = self._page()
        for hook in (
            'data-rmc-sc-verdict="1"',
            'data-rmc-sc-flow="1"',
            "data-rmc-sync-schedule-panel",
            'data-rmc-sc-activity="1"',
        ):
            self.assertIn(hook, body, hook)

    def test_25_the_facts_that_used_to_render_twice_render_once(self):
        """The whole point of the rebuild, expressed as a count.

        A third copy of any of these is the exact regression this file exists to catch,
        and it is invisible in review because each copy looks correct on its own.
        """
        body = self._page()
        for hook in (
            'data-rmc-sc-last="1"',
            'data-rmc-sc-next="1"',
            'data-rmc-sc-timeline="1"',
            'data-rmc-sc-spark="1"',
        ):
            self.assertEqual(body.count(hook), 1, f"{hook} rendered {body.count(hook)}x")

    def test_26_the_retired_duplicate_hooks_are_gone(self):
        """Each of these was the SECOND rendering of a fact the page already showed."""
        body = self._page()
        for retired in (
            "data-rmc-schedule-last",      # duplicated the live panel's last-sync age
            "data-rmc-sync-last-age",      # ...and vice versa
            "data-rmc-sync-next-due",      # the second, contradictory "next"
            "data-rmc-sync-recent",        # the server-rendered recent-cycles list
            "data-rmc-sync-history",       # the JS-polled recent-cycles table
            "data-rmc-sync-stat-pending",  # the third conflict count
        ):
            self.assertNotIn(retired, body, retired)

    def test_27_only_one_poller_is_loaded(self):
        """Two pollers hit the same endpoint and painted different halves of it, which is
        how five facts ended up rendered twice in two formats."""
        body = self._page()
        self.assertNotIn("siteconfig__sync_center_live.js", body)
        self.assertEqual(body.count("rmc-sync-center.js"), 1)

    def test_28_the_conflicts_table_is_not_on_this_page(self):
        body = self._page()
        self.assertNotIn('id="sync-conflicts-table"', body)
        self.assertNotIn("data-rmc-bulk-table", body)

    def test_29_but_the_page_that_owns_it_is_linked(self):
        """An attention row without the page that RESOLVES it is a dead end."""
        from apps.siteconfig.models import SyncConflict

        SyncConflict.objects.create(
            school=self.school,
            entity_type="attendance",
            entity_id=1,
            status=SyncConflict.Status.PENDING,
        )
        body = self._page()
        self.assertIn(reverse("siteconfig:sync_conflicts"), body)

    def test_30_the_work_queue_is_absent_when_nothing_needs_a_person(self):
        """An empty 'boxes waiting to pair' panel on every school's page is chrome."""
        from apps.siteconfig.models import SyncConflict

        SyncConflict.objects.filter(school=self.school).delete()
        body = self._page()
        self.assertNotIn('id="sync-needs-you"', body)
        self.assertIn("Nothing needs your attention", body)

    def test_31_and_present_when_something_does(self):
        from apps.siteconfig.models import SyncConflict

        SyncConflict.objects.create(
            school=self.school,
            entity_type="attendance",
            entity_id=2,
            status=SyncConflict.Status.PENDING,
        )
        body = self._page()
        self.assertIn('id="sync-needs-you"', body)

    def test_32_the_conflicts_page_carries_the_table_and_the_way_back(self):
        from apps.siteconfig.models import SyncConflict

        # With nothing pending the page correctly renders its empty state instead of a
        # table -- so the row is what makes this an assertion about the table.
        SyncConflict.objects.create(
            school=self.school,
            entity_type="attendance",
            entity_id=9,
            status=SyncConflict.Status.PENDING,
        )
        resp = self.client.get(reverse("siteconfig:sync_conflicts"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn('id="sync-conflicts-table"', body)
        self.assertIn("data-rmc-bulk-table", body)
        self.assertIn(reverse("siteconfig:sync_center"), body)

    def test_33_resolving_a_conflict_returns_to_the_page_that_owns_conflicts(self):
        from apps.siteconfig.models import SyncConflict

        conflict = SyncConflict.objects.create(
            school=self.school,
            entity_type="attendance",
            entity_id=3,
            status=SyncConflict.Status.PENDING,
        )
        resp = self.client.post(
            reverse("siteconfig:sync_center_resolve", args=[conflict.pk]),
            data={"resolution": "discard"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("siteconfig:sync_conflicts"))

    def test_34_but_running_a_sync_still_returns_to_the_sync_center(self):
        """The over-broad half of that retarget would have sent 'Sync now' to a conflict
        table, which is not where the person who pressed it is looking."""
        resp = self.client.post(reverse("siteconfig:sync_center_request_resync"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("siteconfig:sync_center"))


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _PREVIEW_HOST]
)
class SchedulePreviewEndpointTests(TestCase):
    """The preview exists so the browser never re-implements the scheduler."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import Permission as FeaturePermission, User
        from apps.schools.models import School, SchoolMembership

        cls.school = School.objects.create(
            name="Preview School",
            slug="sync-preview",
            subdomain="sync-preview",
            is_active=True,
        )
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )
        cls.admin = User.objects.create_user(
            username="sync_preview_admin", password="x" * 12, role=User.Role.ADMIN
        )
        cls.admin.feature_permissions.add(perm)
        SchoolMembership.objects.create(
            user=cls.admin, school=cls.school, role=User.Role.ADMIN, is_primary=True
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_PREVIEW_HOST)
        self.client.login(username="sync_preview_admin", password="x" * 12)
        self.url = reverse("siteconfig:sync_schedule_preview")

    def test_35_a_candidate_is_costed_without_being_saved(self):
        """A preview that wrote would retime the box every time somebody typed."""
        from apps.sync_engine.models_schedule import SyncSchedule

        resp = self.client.post(
            self.url,
            data={
                "name": "Preview only",
                "mode": "INTERVAL",
                "is_enabled": "on",
                "window_start": "06:00",
                "window_end": "18:00",
                "interval_minutes": "30",
                "days_of_week": ["0", "1", "2", "3", "4"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["valid"])
        self.assertTrue(body["coverage"]["available"])
        self.assertGreater(body["coverage"]["week"]["total"], 0)
        self.assertEqual(SyncSchedule.objects.filter(school=self.school).count(), 0)

    def test_36_an_invalid_candidate_reports_the_field_not_a_500(self):
        resp = self.client.post(
            self.url,
            data={
                "name": "Broken",
                "mode": "INTERVAL",
                "is_enabled": "on",
                "days_of_week": [],
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["valid"])
        self.assertTrue(body["errors"])

    def test_37_the_next_five_ride_inside_coverage_so_they_describe_one_rule_set(self):
        resp = self.client.post(
            self.url,
            data={
                "name": "Nightly",
                "mode": "AT_TIMES",
                "is_enabled": "on",
                "at_times": "22:00",
                "days_of_week": ["0", "1", "2", "3", "4", "5", "6"],
            },
        )
        body = resp.json()
        self.assertIn("next_runs", body["coverage"])
        self.assertEqual(len(body["coverage"]["next_runs"]), 5)

    def test_38_pausing_a_saved_rule_previews_without_it(self):
        from apps.sync_engine.models_schedule import SyncSchedule

        rule = SyncSchedule.objects.create(
            school=self.school,
            name="Saved",
            mode="AT_TIMES",
            at_times="22:00",
            days_of_week="0,1,2,3,4,5,6",
            is_enabled=True,
        )
        with_rule = self.client.post(self.url, data={}).json()
        without = self.client.post(self.url, data={"paused_ids": str(rule.pk)}).json()
        self.assertGreater(with_rule["coverage"]["week"]["total"], 0)
        self.assertEqual(without["coverage"]["week"]["total"], 0)

    def test_39_each_rule_editor_gets_its_own_field_ids(self):
        """A tenant may hold several rules, and the panel renders an editor for each.

        With Django's default ``id_%s`` every ``<label for="id_mode">`` on the page points
        at the FIRST rule's control, so clicking the third rule's label focuses the first
        rule and a screen reader announces the wrong one. Only the IDS are namespaced --
        the field NAMES must stay untouched, because the save view reads
        ``request.POST["mode"]``.
        """
        from apps.siteconfig.forms_sync_schedule import SyncScheduleForm
        from apps.sync_engine.models_schedule import SyncSchedule

        first = SyncSchedule.objects.create(
            school=self.school, name="A", mode="AT_TIMES",
            at_times="06:00", days_of_week="0", is_enabled=True,
        )
        second = SyncSchedule.objects.create(
            school=self.school, name="B", mode="AT_TIMES",
            at_times="18:00", days_of_week="0", is_enabled=True,
        )
        form_a = SyncScheduleForm(instance=first)
        form_b = SyncScheduleForm(instance=second)
        blank = SyncScheduleForm(instance=SyncSchedule(school=self.school))
        ids = {
            form_a["mode"].id_for_label,
            form_b["mode"].id_for_label,
            blank["mode"].id_for_label,
        }
        self.assertEqual(len(ids), 3, ids)
        # ...and the names are still what the view reads.
        for form in (form_a, form_b, blank):
            self.assertEqual(form["mode"].html_name, "mode")

    def test_40_it_refuses_a_caller_with_no_school(self):
        from apps.accounts.models import User

        stranger = User.objects.create_user(
            username="sync_preview_nobody", password="x" * 12, role=User.Role.TEACHER
        )
        stranger.feature_permissions.clear()
        client = Client(HTTP_HOST=_PREVIEW_HOST)
        client.login(username="sync_preview_nobody", password="x" * 12)
        resp = client.post(self.url, data={})
        self.assertIn(resp.status_code, (302, 403))


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST])
class HourlyHistoryTests(TestCase):
    """The sparkline's data. Zeros are the point."""

    @classmethod
    def setUpTestData(cls):
        from apps.schools.models import School

        cls.school = School.objects.create(
            name="Spark School",
            slug="sync-spark",
            subdomain="sync-spark",
            is_active=True,
        )

    def test_41_every_hour_in_the_window_gets_a_slot(self):
        """Returning only the hours that HAVE runs would draw a continuous healthy line
        over a box that was off all night — the silence would be compressed out."""
        from django.utils import timezone

        from apps.siteconfig.views_sync_center import _STATUS_WINDOW_HOURS, _hourly_history
        from apps.sync_engine.models import EdgeSyncRun

        EdgeSyncRun.record(self.school, ok=True, mode="live")
        now = timezone.now()
        window = EdgeSyncRun.objects.filter(school=self.school)
        history = _hourly_history(window, now=now)
        self.assertEqual(len(history), _STATUS_WINDOW_HOURS)
        self.assertEqual(sum(row["runs"] for row in history), 1)
        self.assertGreater(sum(1 for row in history if row["runs"] == 0), 0)

    def test_42_a_failure_is_carried_separately_from_the_count(self):
        from django.utils import timezone

        from apps.siteconfig.views_sync_center import _hourly_history
        from apps.sync_engine.models import EdgeSyncRun

        EdgeSyncRun.record(self.school, ok=False, error="boom", mode="live")
        window = EdgeSyncRun.objects.filter(school=self.school)
        history = _hourly_history(window, now=timezone.now())
        self.assertEqual(sum(row["failed"] for row in history), 1)
