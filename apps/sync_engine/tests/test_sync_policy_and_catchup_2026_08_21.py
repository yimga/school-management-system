"""The two judgement calls, closed: a visible DST decision and a tenant-owned ceiling.

Plus the gap the audit found underneath them: ``missed_run()`` was correct, tested, and
called by NOTHING except the status panel — so the Sync Center would say "a scheduled
sync was missed" while the box quietly waited for the NEXT scheduled time. The sentence
that motivates the whole feature ("it should have synced at 6, it was off, it synced when
I turned it on") was documented in three places and implemented in none.

NOTE ON ASSERTIONS. ``config/settings_test.py`` calls ``logging.disable(CRITICAL)``, so
``assertLogs`` sees nothing here. Where behaviour is only observable through a log, patch
the module logger and assert on the CALL.
"""
from __future__ import annotations

import datetime as _dt
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.sync_engine import cadence, schedule_policy
from apps.sync_engine.models_policy import (
    DEFAULT_IDLE_CEILING_MINUTES,
    MAX_IDLE_CEILING_MINUTES,
    MIN_IDLE_CEILING_MINUTES,
    SINGLETON_ANCHOR,
    ResolvedPolicy,
)
from apps.sync_engine.schedule import (
    MODE_AT_TIMES,
    Rule,
    describe_dst,
    next_dst_transition,
    next_run_at,
)

UTC = _dt.timezone.utc


# --------------------------------------------------------------------- DST visible --
class DstIsVisibleNotJustDecidedTests(SimpleTestCase):
    """The behaviour was always right; what was missing is that nobody could SEE it."""

    def test_01_finds_the_next_spring_forward(self):
        tz = ZoneInfo("Australia/Sydney")  # southern hemisphere: forward in October
        found = next_dst_transition(tz, after=_dt.datetime(2026, 8, 21, tzinfo=UTC))
        self.assertIsNotNone(found)
        self.assertEqual(found["direction"], "forward")
        self.assertEqual(found["shift_minutes"], 60)

    def test_02_finds_the_next_fall_back(self):
        tz = ZoneInfo("America/New_York")
        found = next_dst_transition(tz, after=_dt.datetime(2026, 8, 21, tzinfo=UTC))
        self.assertIsNotNone(found)
        self.assertEqual(found["direction"], "back")
        self.assertEqual(found["shift_minutes"], -60)

    def test_03_a_zone_without_dst_says_so_rather_than_guessing(self):
        for name in ("Africa/Douala", "UTC"):
            note = describe_dst(ZoneInfo(name), after=_dt.datetime(2026, 8, 21, tzinfo=UTC))
            self.assertFalse(note["observes"], name)
            self.assertEqual(note["note"], "")

    def test_04_the_note_names_the_date_and_what_will_happen(self):
        note = describe_dst(
            ZoneInfo("Europe/London"), after=_dt.datetime(2026, 8, 21, tzinfo=UTC)
        )
        self.assertTrue(note["observes"])
        self.assertIn("2026", note["note"])
        # The promise the engine actually keeps, in the words a non-engineer reads.
        self.assertIn("once", note["note"])

    def test_05_the_transition_instant_is_when_the_offset_really_changes(self):
        tz = ZoneInfo("America/New_York")
        found = next_dst_transition(tz, after=_dt.datetime(2026, 8, 21, tzinfo=UTC))
        at = found["at"]
        before = (at - _dt.timedelta(hours=2)).astimezone(tz).utcoffset()
        after = (at + _dt.timedelta(hours=2)).astimezone(tz).utcoffset()
        self.assertNotEqual(before, after)

    def test_06_a_broken_timezone_never_takes_the_panel_down(self):
        # describe_dst is called on a status render; it must degrade, not raise.
        self.assertEqual(
            describe_dst(object(), after=_dt.datetime(2026, 8, 21, tzinfo=UTC)),
            {"observes": False, "note": ""},
        )

    def test_07_spring_forward_keeps_the_run_just_past_the_gap(self):
        """The decision itself, re-asserted here because it is now also DISPLAYED.

        The guarantee is "never dropped, never drifts by more than the gap" — NOT "fires
        at exactly 03:00". A skipped 02:30 keeps its absolute moment: 02:30 EST and
        03:30 EDT are the same instant, so the run lands the other side of the gap.
        This test previously asserted the docstring's wording rather than the engine's
        behaviour and caught the two disagreeing; the docs were corrected to match.
        """
        tz = ZoneInfo("America/New_York")
        # 2026-03-08: 02:00 -> 03:00. A 02:30 rule has no 02:30 that day.
        rule = Rule(mode=MODE_AT_TIMES, days=frozenset(range(7)), times=(_dt.time(2, 30),))
        got = next_run_at(
            [rule], after=_dt.datetime(2026, 3, 8, 5, 0, tzinfo=UTC), tz=tz
        )
        self.assertIsNotNone(got, "a skipped wall time must never drop the run")
        local = got.astimezone(tz)
        self.assertEqual(local.date(), _dt.date(2026, 3, 8), "same day, not deferred")
        # Past the gap, and by no more than the gap itself.
        self.assertGreaterEqual((local.hour, local.minute), (3, 0))
        self.assertLessEqual((local.hour, local.minute), (3, 30))

    def test_08_fall_back_fires_once_not_twice(self):
        tz = ZoneInfo("America/New_York")
        # 2026-11-01: 02:00 -> 01:00, so 01:30 happens twice.
        rule = Rule(mode=MODE_AT_TIMES, days=frozenset(range(7)), times=(_dt.time(1, 30),))
        first = next_run_at(
            [rule], after=_dt.datetime(2026, 11, 1, 0, 0, tzinfo=UTC), tz=tz
        )
        second = next_run_at([rule], after=first, tz=tz)
        self.assertEqual(first.astimezone(tz).date(), _dt.date(2026, 11, 1))
        # The next firing is the FOLLOWING day, not the repeated 01:30 an hour later.
        self.assertEqual(second.astimezone(tz).date(), _dt.date(2026, 11, 2))


# ------------------------------------------------------------------ idle ceiling --
class _FakeSchool:
    pk = 4242
    timezone = "UTC"


class IdleCeilingIsTheTenantsNumberTests(SimpleTestCase):
    """It used to be an env var on a host the school cannot see. Now it is theirs."""

    def setUp(self):
        self._policy = mock.patch(
            "apps.sync_engine.models_policy.policy_for", return_value=ResolvedPolicy()
        )

    def test_09_default_when_nothing_is_configured(self):
        with mock.patch.dict("os.environ", {}, clear=False) as _env:
            import os

            os.environ.pop("RMC_EDGE_SYNC_IDLE_CEILING_SECONDS", None)
            self.assertEqual(
                schedule_policy.idle_ceiling_seconds(), DEFAULT_IDLE_CEILING_MINUTES * 60
            )

    def test_10_the_operator_pin_outranks_the_tenant(self):
        """Somebody debugging a box in front of them must be able to hold it still."""
        import os

        with mock.patch.dict(
            os.environ, {"RMC_EDGE_SYNC_IDLE_CEILING_SECONDS": "120"}, clear=False
        ):
            with mock.patch(
                "apps.sync_engine.models_policy.policy_for",
                return_value=ResolvedPolicy(idle_ceiling_minutes=720),
            ):
                self.assertEqual(
                    schedule_policy.idle_ceiling_seconds(_FakeSchool()), 120
                )

    def test_11_the_tenants_row_beats_the_default(self):
        import os

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RMC_EDGE_SYNC_IDLE_CEILING_SECONDS", None)
            with mock.patch(
                "apps.sync_engine.models_policy.policy_for",
                return_value=ResolvedPolicy(idle_ceiling_minutes=180),
            ):
                self.assertEqual(
                    schedule_policy.idle_ceiling_seconds(_FakeSchool()), 180 * 60
                )

    def test_12_a_junk_env_pin_falls_through_instead_of_crashing(self):
        import os

        with mock.patch.dict(
            os.environ, {"RMC_EDGE_SYNC_IDLE_CEILING_SECONDS": "soon"}, clear=False
        ):
            self.assertEqual(
                schedule_policy.idle_ceiling_seconds(), DEFAULT_IDLE_CEILING_MINUTES * 60
            )

    def test_13_a_policy_read_that_explodes_degrades_to_the_default(self):
        import os

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RMC_EDGE_SYNC_IDLE_CEILING_SECONDS", None)
            with mock.patch(
                "apps.sync_engine.models_policy.policy_for",
                side_effect=RuntimeError("no database"),
            ):
                self.assertEqual(
                    schedule_policy.idle_ceiling_seconds(_FakeSchool()),
                    DEFAULT_IDLE_CEILING_MINUTES * 60,
                )


# ------------------------------------------------------------------------ policy --
class SyncPolicyRowTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Ceiling High", slug="ceiling-high", subdomain="ceiling-high"
        )

    def test_14_absence_means_the_documented_defaults(self):
        from apps.sync_engine.models_policy import policy_for

        resolved = policy_for(self.school)
        self.assertEqual(resolved.idle_ceiling_minutes, DEFAULT_IDLE_CEILING_MINUTES)
        self.assertTrue(resolved.catch_up_missed)
        self.assertEqual(resolved.source, "default")

    def test_15_the_anchor_is_deterministic_so_the_row_converges(self):
        """Both sides mint the same anchor, so the rail UPDATES rather than INSERTing.

        A random anchor would make the cloud's row and the box's row look like two
        different rows to the rail, which would then insert the far side's straight into
        the one-per-school constraint, on every cycle, forever.
        """
        from apps.sync_engine.models_policy import SyncPolicy

        row = SyncPolicy.objects.create(school=self.school, idle_ceiling_minutes=180)
        self.assertEqual(row.client_offline_id, SINGLETON_ANCHOR)

    def test_16_out_of_range_rows_are_clamped_on_read(self):
        """A row from an older build must not put this box outside the bounds."""
        from apps.sync_engine.models_policy import SyncPolicy, policy_for

        SyncPolicy.objects.create(school=self.school, idle_ceiling_minutes=1)
        self.assertEqual(
            policy_for(self.school).idle_ceiling_minutes, MIN_IDLE_CEILING_MINUTES
        )
        SyncPolicy.objects.filter(school=self.school).update(
            idle_ceiling_minutes=MAX_IDLE_CEILING_MINUTES * 99
        )
        self.assertEqual(
            policy_for(self.school).idle_ceiling_minutes, MAX_IDLE_CEILING_MINUTES
        )

    def test_17_validation_refuses_a_ceiling_that_makes_the_box_unreachable(self):
        from django.core.exceptions import ValidationError

        from apps.sync_engine.models_policy import SyncPolicy

        row = SyncPolicy(school=self.school, idle_ceiling_minutes=MAX_IDLE_CEILING_MINUTES + 1)
        with self.assertRaises(ValidationError) as ctx:
            row.clean()
        self.assertIn("idle_ceiling_minutes", ctx.exception.error_dict)

    def test_18_it_rides_the_rail_as_a_converging_settings_row(self):
        from apps.api import sync_services as ss

        self.assertIn(
            ("sync_policy", "sync_engine", "SyncPolicy"), ss._DERIVED_ENTITY_SPECS
        )
        # Two-way LWW, not protected: the worst a stale write can do is check in on the
        # wrong cadence, which the next edit corrects.
        self.assertEqual(ss._sync_conflict_policy("sync_policy"), ("causal_lww", False))

    def test_19_only_the_two_settings_ride_not_the_plumbing(self):
        from django.apps import apps as django_apps

        from apps.api import sync_services as ss

        model = django_apps.get_model("sync_engine", "SyncPolicy")
        self.assertEqual(
            sorted(ss._derive_sync_fields(model)),
            ["catch_up_missed", "idle_ceiling_minutes"],
        )


# ---------------------------------------------------------------------- catch-up --
class _CatchUpBase(TestCase):
    def setUp(self):
        cache.clear()
        cadence.reset()
        from apps.schools.models import School
        from apps.sync_engine.models_schedule import SyncSchedule

        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Catch Up High",
            slug="catchup-high",
            subdomain="catchup-high",
            is_active=True,
            timezone="UTC",
        )
        # 06:00 every day. Simple enough that the missed moment is unambiguous.
        SyncSchedule.objects.create(
            school=self.school,
            name="Daily",
            mode=SyncSchedule.Mode.AT_TIMES,
            days_of_week="0,1,2,3,4,5,6",
            at_times="06:00",
            client_offline_id="rule-1",
        )

    def tearDown(self):
        cache.clear()
        cadence.reset()

    def _record_run_at(self, when):
        from apps.sync_engine.models import EdgeSyncRun

        run = EdgeSyncRun.record(self.school, mode="live", ok=True)
        EdgeSyncRun.objects.filter(pk=run.pk).update(created_at=when)
        return run


class CatchUpIsActuallyWiredTests(_CatchUpBase):
    """``missed_run`` was only ever read by the status panel. Now it drives a cycle."""

    def test_20_a_slept_through_time_is_offered_as_a_catch_up(self):
        # Last ran at 05:00; 06:00 passed while the box was off; it is now 09:00.
        self._record_run_at(_dt.datetime(2026, 8, 20, 5, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        moment = schedule_policy.should_catch_up(self.school, now=now)
        self.assertIsNotNone(moment)
        self.assertEqual(moment.astimezone(UTC).hour, 6)

    def test_21_it_is_claimed_exactly_once_even_if_the_run_fails(self):
        """One catch-up per missed moment, not one per tick.

        Claimed through the cache rather than inferred from "a run happened", because a
        cycle that dies before writing its run row would otherwise catch up forever.
        """
        self._record_run_at(_dt.datetime(2026, 8, 20, 5, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        self.assertIsNotNone(schedule_policy.should_catch_up(self.school, now=now))
        self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))
        self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))

    def test_22_a_weekend_outage_produces_one_run_not_forty_eight(self):
        self._record_run_at(_dt.datetime(2026, 8, 15, 5, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)  # five missed 06:00s
        claimed = [
            schedule_policy.should_catch_up(self.school, now=now) for _ in range(6)
        ]
        self.assertEqual(len([c for c in claimed if c is not None]), 1)

    def test_23_nothing_missed_means_nothing_to_catch_up(self):
        self._record_run_at(_dt.datetime(2026, 8, 20, 7, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))

    def test_24_a_tenant_who_turned_catch_up_off_does_not_get_one(self):
        from apps.sync_engine.models_policy import SyncPolicy

        SyncPolicy.objects.create(school=self.school, catch_up_missed=False)
        self._record_run_at(_dt.datetime(2026, 8, 20, 5, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))

    def test_25_backoff_outranks_catch_up(self):
        """A box catching up into a cloud that is down is the schedule hammering it."""
        self._record_run_at(_dt.datetime(2026, 8, 20, 5, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        with mock.patch.object(cadence, "current_state", return_value=cadence.BACKOFF):
            self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))

    def test_26_no_schedule_means_no_catch_up(self):
        from apps.sync_engine.models_schedule import SyncSchedule

        SyncSchedule.objects.filter(school=self.school).delete()
        self._record_run_at(_dt.datetime(2026, 8, 20, 5, 0, tzinfo=UTC))
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))

    def test_27_a_box_that_never_ran_is_not_retro_caught_up(self):
        now = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        self.assertIsNone(schedule_policy.should_catch_up(self.school, now=now))


@override_settings(RMC_EDGE_SYNC_ENABLED=True)
class TheSchedulerActuallyRunsTheCatchUpTests(_CatchUpBase):
    """THE gap this wave closes: the scheduler now acts on a missed time.

    Before, ``run_edge_sync_now`` asked ``cadence.due_now()`` and returned "skipped" —
    so a box that slept through 06:00 sat until the next scheduled time while the Sync
    Center displayed "a scheduled sync was missed".
    """

    def test_28_a_not_due_box_with_a_missed_time_runs_anyway(self):
        self._record_run_at(_dt.datetime(2026, 8, 20, 5, 0, tzinfo=UTC))
        # Not due on the cadence marker: the next slot is a long way off.
        cadence.schedule_next(3600)
        due, _why = cadence.due_now()
        self.assertFalse(due, "precondition: the box must not be due on the cadence")

        canned = {"enabled": True, "ok": True, "mode": "live", "pushed": 0, "pulled": 0}
        with mock.patch(
            "apps.sync_engine.schedule_policy.should_catch_up",
            return_value=_dt.datetime(2026, 8, 20, 6, 0, tzinfo=UTC),
        ):
            with mock.patch(
                "apps.sync_engine.sync_runner.run_sync_cycle", return_value=canned
            ) as run:
                from apps.sync_engine.edge_scheduler import run_edge_sync_now

                result = run_edge_sync_now()
        run.assert_called_once()
        self.assertTrue(result.get("ran"))
        self.assertEqual(result.get("trigger"), "catch-up")

    def test_29_a_not_due_box_with_nothing_missed_still_skips(self):
        cadence.schedule_next(3600)
        with mock.patch(
            "apps.sync_engine.schedule_policy.should_catch_up", return_value=None
        ):
            with mock.patch("apps.sync_engine.sync_runner.run_sync_cycle") as run:
                from apps.sync_engine.edge_scheduler import run_edge_sync_now

                result = run_edge_sync_now()
        run.assert_not_called()
        self.assertTrue(result.get("skipped"))

    def test_30_a_catch_up_check_that_explodes_never_breaks_the_tick(self):
        cadence.schedule_next(3600)
        with mock.patch(
            "apps.sync_engine.schedule_policy.should_catch_up",
            side_effect=RuntimeError("cache down"),
        ):
            with mock.patch("apps.sync_engine.sync_runner.run_sync_cycle") as run:
                from apps.sync_engine.edge_scheduler import run_edge_sync_now

                result = run_edge_sync_now()
        run.assert_not_called()
        self.assertTrue(result.get("skipped"))


# ----------------------------------------------------------------------- surface --
class SyncPolicySurfaceTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Surface High", slug="surface-high", subdomain="surface-high"
        )

    def test_31_the_form_offers_only_bounded_choices(self):
        from apps.siteconfig.forms_sync_policy import IDLE_CEILING_CHOICES

        for minutes, _label in IDLE_CEILING_CHOICES:
            self.assertGreaterEqual(minutes, MIN_IDLE_CEILING_MINUTES)
            self.assertLessEqual(minutes, MAX_IDLE_CEILING_MINUTES)

    def test_32_a_value_outside_the_bounds_is_refused_not_saved(self):
        from apps.siteconfig.forms_sync_policy import SyncPolicyForm
        from apps.sync_engine.models_policy import SyncPolicy

        form = SyncPolicyForm(
            {"idle_ceiling_minutes": str(MAX_IDLE_CEILING_MINUTES * 10),
             "catch_up_missed": "on"},
            instance=SyncPolicy(school=self.school),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("idle_ceiling_minutes", form.errors)

    def test_33_form_field_names_match_the_model_so_errors_can_land(self):
        """Django maps a model ValidationError dict onto form fields BY NAME."""
        from apps.siteconfig.forms_sync_policy import SyncPolicyForm

        form = SyncPolicyForm()
        for name in ("idle_ceiling_minutes", "catch_up_missed"):
            self.assertIn(name, form.fields)

    def test_34_the_summary_carries_the_ceiling_and_where_it_came_from(self):
        summary = schedule_policy.schedule_summary(self.school)
        self.assertIn("idle_ceiling_minutes", summary)
        self.assertIn("idle_ceiling_source", summary)
        self.assertIn("catch_up_missed", summary)

    def test_35_the_summary_carries_the_dst_decision(self):
        self.school.timezone = "America/New_York"
        self.school.save(update_fields=["timezone"])
        summary = schedule_policy.schedule_summary(self.school)
        self.assertIn("dst", summary)
        self.assertTrue(summary["dst"]["observes"])
        self.assertTrue(summary["dst"]["note"])

    def test_36_a_zone_without_dst_shows_no_clock_change_note(self):
        self.school.timezone = "Africa/Douala"
        self.school.save(update_fields=["timezone"])
        summary = schedule_policy.schedule_summary(self.school)
        self.assertFalse(summary["dst"]["observes"])


_POLICY_HOST = "sync-policy-perm.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _POLICY_HOST]
)
class SyncPolicySaveIsGatedTests(TestCase):
    """The endpoint retimes a box. Who may call it, and for WHICH school.

    ``apps/siteconfig/tests/test_sync_center_mutating_policy.py`` asserts this contract
    for ``sync_center_resolve`` by NAME, so it does not reach a new endpoint -- the
    permission gate on this one was unasserted until these tests.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import Permission as FeaturePermission
        from apps.schools.models import School

        cls.school = School.objects.create(
            name="Policy Perm School",
            slug="sync-policy-perm",
            subdomain="sync-policy-perm",
            is_active=True,
        )
        cls.other = School.objects.create(
            name="Someone Else",
            slug="sync-policy-other",
            subdomain="sync-policy-other",
            is_active=True,
        )
        FeaturePermission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )

    def setUp(self):
        from django.test import Client

        self.client = Client(HTTP_HOST=_POLICY_HOST, raise_request_exception=False)

    def _member(self, username, role):
        from apps.accounts.models import User
        from apps.schools.models import SchoolMembership

        user = User.objects.create_user(username=username, password="x" * 8, role=role)
        user.feature_permissions.clear()
        SchoolMembership.objects.create(
            user=user, school=self.school, role=role, is_primary=True
        )
        return user

    def test_37_a_teacher_without_settings_manage_cannot_retime_the_box(self):
        from django.urls import reverse

        from apps.accounts.models import User

        self._member("policy_noperm", User.Role.TEACHER)
        self.client.login(username="policy_noperm", password="x" * 8)
        resp = self.client.post(
            reverse("siteconfig:sync_policy_save"),
            data={"idle_ceiling_minutes": "60", "catch_up_missed": "on"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_38_get_is_refused_so_a_link_cannot_change_settings(self):
        from django.urls import reverse

        from apps.accounts.models import User

        self._member("policy_get", User.Role.ADMIN)
        self.client.login(username="policy_get", password="x" * 8)
        resp = self.client.get(reverse("siteconfig:sync_policy_save"))
        self.assertEqual(resp.status_code, 405)

    def test_39_a_school_id_in_the_post_body_cannot_retime_another_tenant(self):
        """An id in a request is an argument, not a claim."""
        from django.urls import reverse

        from apps.accounts.models import User
        from apps.sync_engine.models_policy import SyncPolicy

        user = self._member("policy_admin", User.Role.ADMIN)
        user.feature_permissions.add(
            __import__(
                "apps.accounts.models", fromlist=["Permission"]
            ).Permission.objects.get(code="settings.manage")
        )
        self.client.login(username="policy_admin", password="x" * 8)
        self.client.post(
            reverse("siteconfig:sync_policy_save"),
            data={
                "idle_ceiling_minutes": "180",
                "catch_up_missed": "on",
                # Ignored: the view resolves the school from the REQUEST.
                "school": str(self.other.pk),
                "school_id": str(self.other.pk),
            },
        )
        self.assertFalse(
            SyncPolicy.objects.filter(school=self.other).exists(),
            "a POSTed school id must never reach another tenant's box",
        )
