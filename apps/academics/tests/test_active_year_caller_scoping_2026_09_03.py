"""Every get_active_year_and_term caller must pass school= (swept 2026-09-03).

An unscoped call resolves whichever school's active year sorts first, which
either leaks another school's data (dashboard events) or silently empties a
page (a teacher's rows filtered by a foreign year). The sweep scoped all 33
callers; the ratchet below keeps the set closed and self-cleans its own
allowlist.
"""

from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

BARE_CALL = "get_active_year_and_term" + "()"

# Files still allowed to contain a bare call. Every entry must actually
# contain one, so fixing a file forces its removal here (no stale exemptions).
# Closed 2026-09-03. The last exemption was _teacher_org_tree in
# apps/accounts/views.py: it takes a user rather than a request, and User has
# no school column, so the scope now comes from TeacherProfile.school (the
# profile is resolved from that user, so it names exactly one school) with the
# user's primary non-suspended SchoolMembership as the fallback.
#
# Kept as set() rather than {} on purpose: an empty brace literal is a DICT,
# and the `ALLOWED_BARE - set(offenders)` staleness check below would raise
# TypeError instead of asserting.
ALLOWED_BARE: set[str] = set()


class BareCallerRatchetTests(SimpleTestCase):
    def test_no_bare_active_year_calls_outside_allowlist(self):
        apps_root = Path(settings.BASE_DIR) / "apps"
        offenders = {}
        scanned = 0
        for path in sorted(apps_root.rglob("*.py")):
            scanned += 1
            rel = path.relative_to(settings.BASE_DIR).as_posix()
            text = path.read_bytes().decode("utf-8", "replace")
            hits = [
                i + 1
                for i, line in enumerate(text.splitlines())
                if BARE_CALL in line and not line.lstrip().startswith("#")
            ]
            if hits:
                offenders[rel] = hits
        self.assertGreater(scanned, 500, "walk found too few files - wrong root?")
        unexpected = {k: v for k, v in offenders.items() if k not in ALLOWED_BARE}
        stale = ALLOWED_BARE - set(offenders)
        self.assertFalse(
            unexpected,
            "Bare get_active_year_and_term calls (pass school=...): %r" % unexpected,
        )
        self.assertFalse(
            stale,
            "Allowlist entries with no bare call left - delete them: %r" % stale,
        )


class SchoolThreadingTests(SimpleTestCase):
    def test_classrooms_queryset_threads_school_to_year_lookup(self):
        from apps.siteconfig import views as siteconfig_views

        school = object()
        with mock.patch.object(
            siteconfig_views, "get_active_year_and_term", return_value=(None, None)
        ) as helper:
            siteconfig_views._get_classrooms_queryset(school=school)
        helper.assert_called_once_with(school=school)

    def test_sidebar_cache_wrapper_threads_request_school(self):
        from apps.siteconfig import portal_sidebar_items as sidebar

        school = object()
        request = mock.Mock()
        request.school = school
        user = mock.Mock()
        user.pk = None  # forces the direct, uncached path
        with mock.patch.object(
            sidebar, "_sidebar_badge_counts", return_value=(0, 0, 0)
        ) as inner:
            sidebar._cached_sidebar_badge_counts(user, "TEACHER", True, request=request)
        inner.assert_called_once_with(user, "TEACHER", True, school=school)

    def test_certification_ca_marks_scopes_term_by_session_school(self):
        from apps.academics import services as academics_services
        from apps.academics.services_certification import (
            compute_ca_marks_for_candidate,
        )

        candidate = mock.Mock()
        with mock.patch.object(
            academics_services, "get_active_year_and_term", return_value=(None, None)
        ) as helper:
            result = compute_ca_marks_for_candidate(
                candidate, academic_year=mock.Mock(), term=None
            )
        helper.assert_called_once_with(school=candidate.session.school)
        self.assertEqual(result, {"error": "No active term"})
