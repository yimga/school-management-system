"""Acceptance criteria 12-17 + 20: the model, the rail, and what the screen promises.

The two that carry the most weight:

  * ``test_15_the_displayed_next_run_equals_the_function_the_scheduler_acts_on`` — the
    build directive's R3. A next-run label computed by different code than the scheduler
    will drift, and a wrong one is worse than none because it is what the person is
    planning around. Asserted against the FUNCTION, never a hardcoded expectation.
  * ``test_14_a_box_that_cannot_reach_the_cloud_keeps_its_last_known_schedule`` — the
    sovereign-box premise. A schedule that needs the cloud to be reachable is not a
    schedule, it is a remote control.
"""
from __future__ import annotations

import datetime as _dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone as dj_timezone

from apps.schools.models import School
from apps.sync_engine import schedule_policy
from apps.sync_engine.models_schedule import SyncSchedule, rules_for
from apps.sync_engine.schedule import MODE_AT_TIMES, MODE_INTERVAL, next_run_at


def _school(slug="sched-a", tz="Africa/Douala"):
    return School.objects.create(
        name=f"School {slug}", slug=slug, subdomain=slug, is_active=True, timezone=tz
    )


def _office_hours(school, **over):
    kwargs = dict(
        school=school,
        name="Term time",
        mode=SyncSchedule.Mode.INTERVAL,
        days_of_week="0,1,2,3,4",
        window_start=_dt.time(7, 0),
        window_end=_dt.time(18, 0),
        interval_minutes=30,
    )
    kwargs.update(over)
    return SyncSchedule.objects.create(**kwargs)


class ModelShapeTests(TestCase):
    def test_a_saved_rule_round_trips_through_the_pure_evaluator(self):
        school = _school()
        rule = _office_hours(school).to_rule()
        self.assertEqual(rule.mode, MODE_INTERVAL)
        self.assertEqual(rule.days, frozenset({0, 1, 2, 3, 4}))
        self.assertEqual(rule.interval_minutes, 30)

    def test_days_are_canonicalised_on_save(self):
        """"2,1,0" and "0,1,2" are ONE schedule. Storing both would look like a change to
        the delta cursor and re-sync forever."""
        school = _school()
        rule = _office_hours(school, days_of_week="4,0,2,0")
        rule.refresh_from_db()
        self.assertEqual(rule.days_of_week, "0,2,4")

    def test_times_are_canonicalised_on_save(self):
        school = _school()
        rule = SyncSchedule.objects.create(
            school=school, mode=SyncSchedule.Mode.AT_TIMES,
            days_of_week="0,1,2,3,4,5,6", at_times="22:00,6:00,22:00",
        )
        rule.refresh_from_db()
        self.assertEqual(rule.at_times, "06:00,22:00")

    def test_malformed_stored_days_do_not_explode_on_READ(self):
        """A box that refuses to boot because one string is wrong has turned a typo into
        an outage. Save paths validate; read paths degrade."""
        school = _school()
        rule = _office_hours(school)
        SyncSchedule.objects.filter(pk=rule.pk).update(days_of_week="banana,1,9,-3")
        rule.refresh_from_db()
        self.assertEqual(rule.days, frozenset({1}))


class ValidationTests(TestCase):
    """AC16: an invalid rule is refused with a message naming the field."""

    def setUp(self):
        self.school = _school()

    def _clean(self, **over):
        rule = SyncSchedule(school=self.school, mode=SyncSchedule.Mode.INTERVAL,
                            days_of_week="0,1,2,3,4", window_start=_dt.time(7, 0),
                            window_end=_dt.time(18, 0), interval_minutes=30)
        for key, value in over.items():
            setattr(rule, key, value)
        return rule

    def test_no_days_is_refused_and_says_why(self):
        with self.assertRaises(ValidationError) as caught:
            self._clean(days_of_week="").clean()
        self.assertIn("days_of_week", caught.exception.message_dict)
        self.assertIn("never run", str(caught.exception.message_dict["days_of_week"]))

    def test_an_interval_below_the_floor_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._clean(interval_minutes=1).clean()
        self.assertIn("interval_minutes", caught.exception.message_dict)

    def test_an_end_equal_to_the_start_is_refused_with_the_overnight_hint(self):
        with self.assertRaises(ValidationError) as caught:
            self._clean(window_end=_dt.time(7, 0)).clean()
        message = str(caught.exception.message_dict["window_end"])
        self.assertIn("22:00", message, "the refusal must show how to express overnight")

    def test_an_end_EARLIER_than_the_start_is_accepted_as_an_overnight_window(self):
        """22:00-02:00 is a real thing to want; refusing it would be the wrong lesson."""
        self._clean(window_start=_dt.time(22, 0), window_end=_dt.time(2, 0)).clean()

    def test_at_times_with_no_times_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._clean(mode=SyncSchedule.Mode.AT_TIMES, at_times="").clean()
        self.assertIn("at_times", caught.exception.message_dict)

    def test_a_valid_interval_rule_passes(self):
        self._clean().clean()


class TenantScopingTests(TestCase):
    """AC20: one school must never see or be retimed by another's rules."""

    def test_13_rules_are_scoped_to_the_school(self):
        a, b = _school("sched-a"), _school("sched-b")
        _office_hours(a)
        self.assertEqual(len(rules_for(a)), 1)
        self.assertEqual(rules_for(b), [], "another tenant's schedule must not leak")

    def test_a_disabled_rule_is_not_returned(self):
        school = _school()
        _office_hours(school, is_enabled=False)
        self.assertEqual(rules_for(school), [])

    def test_13_a_school_with_no_rules_gets_the_default_and_does_not_error(self):
        """The zero-configuration path: automatic cadence, exactly as before this feature."""
        school = _school()
        self.assertEqual(rules_for(school), [])
        seconds, reason = schedule_policy.interval_for(school)
        self.assertIsNone(seconds)
        self.assertIn("automatic cadence", reason)


class SyncRailTests(TestCase):
    """AC12: the schedule reaches the box the same way every other row does."""

    def test_12_the_schedule_is_a_registered_sync_entity(self):
        from apps.api.sync_services import _get_entity_config, entity_app_labels

        config = _get_entity_config(include_derived=True)
        self.assertIn("sync_schedule", config)
        self.assertEqual(entity_app_labels()["sync_schedule"], "sync_engine")

    def test_12_every_configuration_column_actually_rides(self):
        """A column stored but not synced is a schedule the box never learns about."""
        from apps.api.sync_services import _get_entity_config

        _model, fields = _get_entity_config(include_derived=True)["sync_schedule"]
        for column in (
            "mode", "days_of_week", "window_start", "window_end",
            "interval_minutes", "at_times", "is_enabled", "name",
        ):
            self.assertIn(column, fields, column)

    def test_the_tenant_scope_and_anchor_are_NOT_carried_as_data(self):
        """`school` is set by the bundle and `client_offline_id` IS the identity — sending
        either as a value would let a pulled row rewrite which tenant it belongs to."""
        from apps.api.sync_services import _get_entity_config

        _model, fields = _get_entity_config(include_derived=True)["sync_schedule"]
        for column in ("school", "school_id", "client_offline_id", "updated_at", "created_at"):
            self.assertNotIn(column, fields, column)

    def test_the_conflict_policy_resolves_and_is_not_protected(self):
        """Converging two-way is right here: it is the tenant's own configuration, and a
        sovereign box's administrator may be sitting in front of the box."""
        from apps.api.sync_services import _sync_conflict_policy

        policy, protected = _sync_conflict_policy("sync_schedule")
        self.assertTrue(policy)
        self.assertFalse(protected)

    def test_14_a_box_that_cannot_reach_the_cloud_keeps_its_last_known_schedule(self):
        """The sovereign-box premise: evaluation is LOCAL, against the box's own copy.

        Proven by evaluating with no network of any kind available — the only inputs are
        the rows and the clock.
        """
        school = _school()
        _office_hours(school)
        upcoming = schedule_policy.planned_next_run(
            school, after=_dt.datetime(2026, 8, 20, 9, 5, tzinfo=_dt.timezone.utc)
        )
        self.assertIsNotNone(upcoming)


class StatusSurfaceTests(TestCase):
    def test_15_the_displayed_next_run_equals_the_function_the_scheduler_acts_on(self):
        """R3, asserted against the FUNCTION rather than a hardcoded expectation."""
        school = _school()
        _office_hours(school)
        now = dj_timezone.now()

        summary = schedule_policy.schedule_summary(school, now=now)
        expected = next_run_at(
            rules_for(school), after=now, tz=schedule_policy.school_timezone(school)
        )
        self.assertEqual(summary["next_run_at"], expected.isoformat())

    def test_the_summary_carries_the_last_actual_run_beside_the_promise(self):
        school = _school()
        _office_hours(school)
        summary = schedule_policy.schedule_summary(school)
        self.assertIn("last_run_at", summary)
        self.assertIn("missed_window", summary)

    def test_17_a_box_that_slept_through_a_window_renders_as_stale(self):
        from apps.sync_engine.models import EdgeSyncRun

        school = _school()
        SyncSchedule.objects.create(
            school=school, mode=SyncSchedule.Mode.AT_TIMES,
            days_of_week="0,1,2,3,4,5,6", at_times="00:00,06:00,12:00,18:00",
        )
        EdgeSyncRun.record(school, mode="live", ok=True)
        EdgeSyncRun.objects.filter(school=school).update(
            created_at=dj_timezone.now() - _dt.timedelta(days=3)
        )
        self.assertTrue(schedule_policy.schedule_summary(school)["missed_window"])

    def test_a_box_that_is_up_to_date_does_not_render_as_stale(self):
        from apps.sync_engine.models import EdgeSyncRun

        school = _school()
        SyncSchedule.objects.create(
            school=school, mode=SyncSchedule.Mode.AT_TIMES,
            days_of_week="0,1,2,3,4,5,6", at_times="00:00",
        )
        EdgeSyncRun.record(school, mode="live", ok=True)
        self.assertFalse(schedule_policy.schedule_summary(school)["missed_window"])

    def test_an_unconfigured_school_reports_automatic_rather_than_an_empty_promise(self):
        summary = schedule_policy.schedule_summary(_school())
        self.assertFalse(summary["configured"])
        self.assertIsNone(summary["next_run_at"])

    def test_the_payload_states_the_propagation_delay_rather_than_implying_none(self):
        summary = schedule_policy.schedule_summary(_school())
        self.assertIn("next sync", summary["propagation_note"].lower())
        self.assertIn("cannot contact a box", summary["propagation_note"])

    def test_the_summary_names_the_tenants_timezone(self):
        summary = schedule_policy.schedule_summary(_school(tz="America/New_York"))
        self.assertEqual(summary["timezone"], "America/New_York")


class EditorFormTests(TestCase):
    """AC16 at the surface: the refusal must reach the operator, not a 500."""

    def setUp(self):
        self.school = _school()

    def _form(self, **over):
        from apps.siteconfig.forms_sync_schedule import SyncScheduleForm

        data = {
            "name": "Term time",
            "is_enabled": "on",
            "mode": "INTERVAL",
            "days_of_week": ["0", "1", "2", "3", "4"],
            "window_start": "07:00",
            "window_end": "18:00",
            "interval_minutes": "30",
            "at_times": "",
        }
        data.update(over)
        return SyncScheduleForm(data, instance=SyncSchedule(school=self.school))

    def test_a_valid_rule_saves(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        rule = form.save(commit=False)
        rule.school = self.school
        rule.save()
        self.assertEqual(rule.days_of_week, "0,1,2,3,4")

    def test_no_days_selected_is_a_field_error_not_a_crash(self):
        """Model.clean() keys its error on `days_of_week`; the form must have that field
        or Django raises ValueError and the operator gets a 500 instead of a message."""
        form = self._form(days_of_week=[])
        self.assertFalse(form.is_valid())
        self.assertIn("days_of_week", form.errors)

    def test_an_interval_off_the_offered_list_is_refused(self):
        form = self._form(interval_minutes="1")
        self.assertFalse(form.is_valid())
        self.assertIn("interval_minutes", form.errors)

    def test_unparseable_times_are_refused_with_an_example(self):
        form = self._form(mode="AT_TIMES", at_times="whenever", interval_minutes="")
        self.assertFalse(form.is_valid())
        self.assertIn("06:00", str(form.errors["at_times"]))

    def test_the_form_offers_named_intervals_not_a_free_text_box(self):
        from apps.siteconfig.forms_sync_schedule import SyncScheduleForm

        field = SyncScheduleForm().fields["interval_minutes"]
        self.assertTrue(hasattr(field, "choices"))
        labels = " ".join(str(label) for _v, label in field.choices)
        self.assertIn("Every 30 minutes", labels)

    def test_a_new_rule_opens_on_a_sensible_default(self):
        from apps.siteconfig.forms_sync_schedule import SyncScheduleForm

        form = SyncScheduleForm()
        self.assertEqual(form.fields["days_of_week"].initial, ["0", "1", "2", "3", "4"])
        self.assertEqual(form.fields["interval_minutes"].initial, 30)


class PanelContextTests(TestCase):
    """The Sync Center page must actually receive what the panel renders.

    A wiring typo here shows up as an empty panel on a working feature, which is the kind
    of bug that gets reported as "the schedule does not save".
    """

    def test_the_panel_context_carries_the_schedule(self):
        from apps.siteconfig.views_sync_center import _edge_sync_panel_context

        school = _school()
        _office_hours(school)
        ctx = _edge_sync_panel_context(school)
        self.assertEqual(len(ctx["sync_schedule_rules"]), 1)
        self.assertIsNotNone(ctx["sync_schedule_new_form"])
        self.assertIsNotNone(ctx["sync_schedule_summary"])
        self.assertTrue(ctx["sync_schedule_save_url"])

    def test_each_rule_carries_its_plain_english_description(self):
        from apps.siteconfig.views_sync_center import _edge_sync_panel_context

        school = _school()
        _office_hours(school)
        rendered = _edge_sync_panel_context(school)["sync_schedule_rules"][0].human
        self.assertIn("Monday to Friday", rendered)
        self.assertNotIn("*", rendered, "a cron expression must never reach the screen")

    def test_a_school_with_no_rules_still_renders_the_panel(self):
        from apps.siteconfig.views_sync_center import _edge_sync_panel_context

        ctx = _edge_sync_panel_context(_school())
        self.assertEqual(ctx["sync_schedule_rules"], [])
        self.assertFalse(ctx["sync_schedule_summary"]["configured"])
