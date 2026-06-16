"""Remote Support P1 — RemoteSupportSession lifecycle (pure, no DB)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.models_remote_support import RemoteSupportSession

S = RemoteSupportSession.Status


class RemoteSupportSessionLifecycleTests(SimpleTestCase):
    def _session(self, **kw):
        return RemoteSupportSession(school_id=1, **kw)

    def test_is_open_for_open_statuses(self):
        for st in (S.REQUESTED, S.ACCEPTED, S.ACTIVE):
            self.assertTrue(self._session(status=st).is_open, st)
        for st in (S.ENDED, S.DECLINED, S.EXPIRED, S.CANCELLED):
            self.assertFalse(self._session(status=st).is_open, st)

    def test_consent_required_but_not_granted_is_unsatisfied(self):
        s = self._session(requires_consent=True)
        self.assertFalse(s.consent_satisfied)

    def test_consent_not_required_is_satisfied(self):
        s = self._session(requires_consent=False)
        self.assertTrue(s.consent_satisfied)

    def test_grant_consent_satisfies(self):
        s = self._session(requires_consent=True)
        s.grant_consent(by_user=None)
        self.assertTrue(s.consent_satisfied)
        self.assertIsNotNone(s.consent_granted_at)

    def test_can_go_active_requires_accepted_and_consent(self):
        # Accepted + consent met -> can go active.
        s = self._session(status=S.ACCEPTED, requires_consent=False)
        self.assertTrue(s.can_go_active())
        # Still requested -> cannot.
        self.assertFalse(
            self._session(status=S.REQUESTED, requires_consent=False).can_go_active()
        )
        # Accepted but consent required & not granted -> cannot.
        self.assertFalse(
            self._session(status=S.ACCEPTED, requires_consent=True).can_go_active()
        )

    def test_mark_accepted_sets_operator_and_timestamp(self):
        s = self._session()
        s.mark_accepted(operator=None)
        self.assertEqual(s.status, S.ACCEPTED)
        self.assertIsNotNone(s.accepted_at)

    def test_mark_ended_records_reason_and_summary(self):
        s = self._session(status=S.ACTIVE)
        s.mark_ended(reason="resolved", summary="Fixed the import wizard.")
        self.assertEqual(s.status, S.ENDED)
        self.assertIsNotNone(s.ended_at)
        self.assertEqual(s.ended_reason, "resolved")
        self.assertEqual(s.summary, "Fixed the import wizard.")
        self.assertFalse(s.is_open)
