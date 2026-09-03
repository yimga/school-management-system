"""Field-bound + idempotency contracts for three landers (2026-09-01 closeout).

Three defects were found by READING and are pinned here by RUNNING.

1. ``hostel_lander`` clipped ``HostelRoom.name`` to 64 against a
   ``max_length=60`` column and ``Hostel.name`` to 128 against 120.
2. ``structure_lander._get_or_create_term`` looked a ``Term`` up by the
   UNCLIPPED name and created it with ``name[:20]``, so a long term label
   never matched its own stored row on a re-import.
3. ``athletics_teams_lander`` assigns a possibly-``None`` ``roster_cap`` into
   a NOT NULL column. This one did NOT reproduce (``filter_to_model_fields``
   drops the ``None`` before it reaches the DB, so the column default lands);
   the tests below are a REGRESSION GUARD on that behaviour, not a fix.

**Engine honesty.** SQLite does not enforce ``max_length`` -- it stores an
over-length value without complaint, and only PostgreSQL raises ``value too
long for type character varying(60)``. A test that expected an exception would
therefore pass on SQLite for the wrong reason and prove nothing. Every length
assertion here instead asserts the PROPERTY the lander controls: the value it
writes is within the column's own declared ``max_length``, read from
``_meta.get_field(...)``. That is true on both engines. The PostgreSQL failure
itself is NOT reproduced in this suite.
"""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase

from apps.academics.models import AcademicYear, Term
from apps.athletics.constants import DEFAULT_ROSTER_CAP
from apps.athletics.models import Season, Sport, Team
from apps.migration_cloud.landers import athletics_teams_lander as ath_mod
from apps.migration_cloud.landers.athletics_teams_lander import AthleticsTeamsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.hostel_lander import HostelLander
from apps.migration_cloud.landers.structure_lander import StructureLander
from apps.school_events.models import EventVenue
from apps.schoolops.models import Hostel, HostelRoom
from apps.schools.models import School


def _max_length(model, field: str) -> int:
    """The column's own declared width -- never a literal restated in a test."""
    width = model._meta.get_field(field).max_length
    assert width, f"{model.__name__}.{field} declares no max_length"
    return width


def _ctx(school, *, dry_run: bool = False) -> LanderContext:
    return LanderContext(
        school=school,
        schema_name="",
        bundle_id=None,
        artifact_id=None,
        dry_run=dry_run,
    )


def _school(tag: str) -> School:
    # An explicit subdomain per school: a BLANK subdomain is unique, so a second
    # School.objects.create() taking the default would collide.
    return School.objects.create(
        name=f"Bounds {tag}", slug=f"bounds-{tag}", subdomain=f"bounds-{tag}"
    )


class HostelLanderFieldBoundsTests(TestCase):
    """Bug 1 -- the clip must be the column's width, not a neighbouring literal."""

    def setUp(self):
        self.school = _school("hostel")

    def _row(self, **over):
        row = {
            "hostel": "H" * (_max_length(Hostel, "name") + 8),
            "room": "R" * (_max_length(HostelRoom, "name") + 4),
            "capacity": "4",
        }
        row.update(over)
        return row

    def test_hostel_name_written_within_its_column(self):
        row = self._row()
        result = HostelLander().land(canonical_rows=iter([row]), ctx=_ctx(self.school))
        self.assertEqual(result.quarantined, 0, result.errors)

        cap = _max_length(Hostel, "name")
        hostel = Hostel.objects.get(school=self.school)
        self.assertLessEqual(
            len(hostel.name),
            cap,
            f"Hostel.name stored at {len(hostel.name)} chars against "
            f"max_length={cap}: PostgreSQL would refuse this INSERT",
        )
        self.assertEqual(hostel.name, row["hostel"][:cap])

    def test_room_name_written_within_its_column(self):
        row = self._row()
        result = HostelLander().land(canonical_rows=iter([row]), ctx=_ctx(self.school))
        self.assertEqual(result.quarantined, 0, result.errors)

        cap = _max_length(HostelRoom, "name")
        room = HostelRoom.objects.get(hostel__school=self.school)
        self.assertLessEqual(
            len(room.name),
            cap,
            f"HostelRoom.name stored at {len(room.name)} chars against "
            f"max_length={cap}: PostgreSQL would refuse this INSERT",
        )
        self.assertEqual(room.name, row["room"][:cap])

    def test_over_length_names_re_import_without_duplicating(self):
        """The lookup clip and the create clip must be the same value."""
        first = HostelLander().land(
            canonical_rows=iter([self._row()]), ctx=_ctx(self.school)
        )
        second = HostelLander().land(
            canonical_rows=iter([self._row()]), ctx=_ctx(self.school)
        )
        self.assertEqual(first.created, 1)
        self.assertEqual((second.created, second.quarantined), (0, 0), second.errors)
        self.assertEqual(Hostel.objects.filter(school=self.school).count(), 1)
        self.assertEqual(
            HostelRoom.objects.filter(hostel__school=self.school).count(), 1
        )

    def test_explicit_zero_capacity_is_not_rewritten_to_one(self):
        """``coerce_int(...) or 1`` folded a declared 0 into an invented bed."""
        HostelLander().land(
            canonical_rows=iter([self._row(room="Z-1", capacity="0")]),
            ctx=_ctx(self.school),
        )
        room = HostelRoom.objects.get(name="Z-1")
        self.assertEqual(room.capacity, 0)

    def test_missing_capacity_takes_the_column_default(self):
        HostelLander().land(
            canonical_rows=iter([self._row(room="D-1", capacity="")]),
            ctx=_ctx(self.school),
        )
        room = HostelRoom.objects.get(name="D-1")
        self.assertIsNotNone(room.capacity)
        self.assertEqual(room.capacity, HostelRoom._meta.get_field("capacity").default)


class StructureLanderTermIdempotencyTests(TestCase):
    """Bug 2 -- a lookup that cannot match what the create wrote."""

    # Deliberately longer than Term.name's column so the clip is exercised.
    LONG_TERM = "FIRST-SEMESTER-EXTENDED-2025"

    def setUp(self):
        self.school = _school("structure")
        self.assertGreater(len(self.LONG_TERM), _max_length(Term, "name"))

    def _row(self, **over):
        row = {
            "academic_year": "2025/2026",
            "year_start": "2025-09-01",
            "year_end": "2026-07-01",
            "year_is_active": "true",
            "term": self.LONG_TERM,
            "term_label": "",
            "term_position": "1",
            "term_start": "2025-09-01",
            "term_end": "2025-12-15",
            "department": "Science",
            "classroom": "Form 4A",
            "specialty": "General",
            "subject": "Mathematics",
            "coefficient": "1",
            "teacher_ref": "j.doe",
            "teacher_first_name": "Jane",
            "teacher_last_name": "Doe",
            "teacher_email": "jane@example.com",
        }
        row.update(over)
        return row

    def test_term_name_written_within_its_column(self):
        result = StructureLander().land(
            canonical_rows=iter([self._row()]), ctx=_ctx(self.school)
        )
        self.assertEqual(result.quarantined, 0, result.errors)
        cap = _max_length(Term, "name")
        term = Term.objects.get(academic_year__school=self.school)
        self.assertLessEqual(len(term.name), cap)
        self.assertEqual(term.name, self.LONG_TERM[:cap])

    def test_term_custom_label_written_within_its_column(self):
        cap = _max_length(Term, "custom_label")
        label = "L" * (cap + 6)
        StructureLander().land(
            canonical_rows=iter([self._row(term_label=label)]), ctx=_ctx(self.school)
        )
        term = Term.objects.get(academic_year__school=self.school)
        self.assertLessEqual(len(term.custom_label), cap)
        self.assertEqual(term.custom_label, label[:cap])

    def test_re_importing_a_long_term_name_is_a_no_op(self):
        """The whole defect: the second pass must MATCH, not try to create."""
        first = StructureLander().land(
            canonical_rows=iter([self._row()]), ctx=_ctx(self.school)
        )
        self.assertEqual((first.created, first.quarantined), (1, 0), first.errors)

        second = StructureLander().land(
            canonical_rows=iter([self._row()]), ctx=_ctx(self.school)
        )
        self.assertEqual(
            second.quarantined,
            0,
            f"re-import held the row instead of matching it: {second.errors}",
        )
        self.assertEqual(second.created, 0)
        self.assertEqual(second.skipped, 1)
        self.assertEqual(
            Term.objects.filter(academic_year__school=self.school).count(), 1
        )

    def test_a_failing_row_does_not_take_the_next_row_down(self):
        """The per-row quarantine only works inside a SAVEPOINT.

        An IntegrityError raised inside the apply transaction marks the
        connection ``needs_rollback``; without a savepoint the NEXT row's first
        query raises ``TransactionManagementError`` and every good row in the
        bundle is held alongside the one bad one.
        """
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
        )
        # Occupies position 1 for this year, so a DIFFERENT term claiming
        # position 1 hits ``unique_term_position_per_year``.
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name="EXISTING",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        rows = [
            self._row(term="BRAND-NEW", term_position="1"),
            self._row(term="EXISTING", term_position="1", subject="Physics"),
        ]
        result = StructureLander().land(
            canonical_rows=iter(rows), ctx=_ctx(self.school)
        )
        self.assertEqual(
            result.quarantined,
            1,
            f"expected exactly the bad row to be held, got {result.errors}",
        )
        self.assertEqual(result.created, 1, result.errors)
        # The rolled-back row left nothing behind.
        self.assertFalse(Term.objects.filter(name="BRAND-NEW").exists())


class AthleticsTeamsRosterCapTests(TestCase):
    """Bug 3 -- did NOT reproduce. These lock in the behaviour that saves it."""

    def setUp(self):
        self.school = _school("athletics")

    def _row(self, **over):
        row = {
            "sport": "Football",
            "season": "2025-2026 Fall",
            "team_name": "Senior Boys 1st XI",
        }
        row.update(over)
        return row

    def _land(self, *rows):
        return AthleticsTeamsLander().land(
            canonical_rows=iter(list(rows)), ctx=_ctx(self.school)
        )

    def test_missing_roster_cap_lands_with_the_column_default(self):
        result = self._land(self._row())
        self.assertEqual(
            (result.created, result.quarantined),
            (1, 0),
            f"a row without roster_cap must land, not hold: {result.errors}",
        )
        team = Team.objects.get(school=self.school)
        self.assertIsNotNone(team.roster_cap)
        self.assertEqual(team.roster_cap, DEFAULT_ROSTER_CAP)

    def test_unparseable_roster_cap_lands_with_the_column_default(self):
        result = self._land(self._row(roster_cap="not-a-number"))
        self.assertEqual((result.created, result.quarantined), (1, 0), result.errors)
        self.assertEqual(
            Team.objects.get(school=self.school).roster_cap, DEFAULT_ROSTER_CAP
        )

    def test_explicit_zero_roster_cap_is_preserved(self):
        """A closed squad is not the same as an unstated cap.

        ``coerce_int(...) or 1`` -- the pattern an auditor flagged in the hostel
        lander -- would fold this to a truthy default and silently reopen the
        squad. Do not let anyone "fix" bug 3 that way.
        """
        self._land(self._row(roster_cap="0"))
        self.assertEqual(Team.objects.get(school=self.school).roster_cap, 0)

    def test_re_import_without_a_cap_does_not_reset_an_operator_value(self):
        self._land(self._row(roster_cap="11"))
        self._land(self._row())
        self.assertEqual(Team.objects.get(school=self.school).roster_cap, 11)


class LanderClipWidthConstantsTest(SimpleTestCase):
    """Every remaining clip literal in these landers, against its own column.

    A width restated as a module constant is only safe while somebody checks it.
    This is that check; it needs no DB and is honest on any engine.
    """

    def test_athletics_teams_caps_match_their_columns(self):
        self.assertEqual(ath_mod._NAME_CAP, _max_length(Team, "name"))
        self.assertEqual(ath_mod._NAME_CAP, _max_length(Season, "name"))
        self.assertEqual(ath_mod._LEVEL_CAP, _max_length(Team, "level"))
        self.assertEqual(ath_mod._SLUG_CAP, _max_length(Sport, "code"))
        self.assertEqual(ath_mod._SPORT_NAME_CAP, _max_length(Sport, "name"))
        self.assertEqual(ath_mod._VENUE_NAME_CAP, _max_length(EventVenue, "name"))

    def test_team_gender_and_status_values_fit_their_columns(self):
        for value in ath_mod._VALID_GENDERS:
            self.assertLessEqual(len(value), _max_length(Team, "gender"), value)
        for value in ath_mod._VALID_STATUSES:
            self.assertLessEqual(len(value), _max_length(Team, "status"), value)
