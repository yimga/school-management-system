"""The cron that rescues parked mail must not be the thing that destroys it.

On an edge box ``send_transactional`` parks outbound mail proactively in
``EmailDeadLetter`` rather than handing it to the console backend, so nothing is
lost at send time. That half works.

The drain is where it broke. ``redrive_dead_letters`` re-attempts delivery with
``allow_offline_queue=False``, and ``_get_connection_for_send`` builds that
connection from ``settings.EMAIL_BACKEND`` — which ``deploy/selfhost/.env.edge.example``
sets to ``console.EmailBackend``. So every parked message was printed to stdout,
marked ``redriven``, and delivered to nobody. The template even names this trap
eight lines above the line that configures it.

Two properties are pinned here:

1. A non-delivering backend blocks the drain BEFORE the row loop, so no row is
   touched and ``redrive_count`` is never bumped toward the ceiling (default 5).
   Attempting-and-failing would silently convert a queue that is merely waiting
   for configuration into ``exhausted`` rows nobody revisits.
2. The blocked count is reported, because an all-zero summary is exactly the
   shape of "the queue was empty" — the ambiguity ``drain_edge_outbox`` already
   has explicit error handling to avoid.

DB-free: the dead-letter model is faked so these run without a test database.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.schoolops.email_delivery import (
    _email_backend_can_deliver,
    redrive_dead_letters,
)

CONSOLE = "django.core.mail.backends.console.EmailBackend"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
DUMMY = "django.core.mail.backends.dummy.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


class BackendCanDeliverTests(SimpleTestCase):
    def test_smtp_can_deliver(self):
        with override_settings(EMAIL_BACKEND=SMTP):
            self.assertEqual(_email_backend_can_deliver(), (True, ""))

    def test_every_django_development_backend_is_rejected(self):
        for backend, token in ((CONSOLE, "console"), (LOCMEM, "locmem"), (DUMMY, "dummy")):
            with self.subTest(backend=backend), override_settings(EMAIL_BACKEND=backend):
                can, kind = _email_backend_can_deliver()
                self.assertFalse(can)
                self.assertEqual(kind, token)

    def test_an_anymail_backend_can_deliver(self):
        # The recommended relay for a box with intermittent internet.
        with override_settings(EMAIL_BACKEND="anymail.backends.mailgun.EmailBackend"):
            self.assertTrue(_email_backend_can_deliver()[0])

    def test_an_unset_backend_is_not_treated_as_undeliverable(self):
        # Absence is a different finding; this predicate answers one question only.
        with override_settings(EMAIL_BACKEND=""):
            self.assertTrue(_email_backend_can_deliver()[0])


class _FakeRow:
    """A parked row that records whether the drain wrote to it."""

    def __init__(self, pk):
        self.id = pk
        self.pk = pk
        self.redrive_count = 0
        self.payload_encrypted = "not-real-ciphertext"
        self.saved = False

    def save(self, *args, **kwargs):
        self.saved = True


class _FakeQuerySet(list):
    def order_by(self, *args, **kwargs):
        return self

    def count(self):
        return len(self)

    def __getitem__(self, key):
        value = list.__getitem__(self, key)
        return _FakeQuerySet(value) if isinstance(key, slice) else value


class _FakeManager:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return _FakeQuerySet(self._rows)


class _FakeModel:
    def __init__(self, rows):
        self.objects = _FakeManager(rows)


def _patch_queue(rows):
    return mock.patch(
        "apps.schoolops.models_email_deadletter.EmailDeadLetter", _FakeModel(rows)
    )


@override_settings(SCHOOLOPS_EMAIL_DLQ_ENABLED=True)
class RedriveBlocksOnNonDeliveringBackendTests(SimpleTestCase):
    def test_parked_rows_are_counted_but_untouched(self):
        rows = [_FakeRow(i) for i in range(7)]
        with override_settings(EMAIL_BACKEND=CONSOLE), _patch_queue(rows):
            summary = redrive_dead_letters(limit=50)

        self.assertEqual(summary["blocked_no_backend"], 7)
        # scanned == 0 is the proof the guard fired BEFORE the row loop.
        self.assertEqual(summary["scanned"], 0)
        self.assertEqual(summary["redriven"], 0)
        self.assertFalse(any(r.saved for r in rows), "a blocked drain wrote to a row")

    def test_no_redrive_attempt_is_consumed(self):
        rows = [_FakeRow(1)]
        with override_settings(EMAIL_BACKEND=CONSOLE), _patch_queue(rows):
            for _ in range(10):  # ten crons, well past the default ceiling of 5
                redrive_dead_letters(limit=50)
        self.assertEqual(rows[0].redrive_count, 0)
        self.assertFalse(rows[0].saved)

    def test_the_send_path_is_never_reached(self):
        rows = [_FakeRow(1)]
        with override_settings(EMAIL_BACKEND=CONSOLE), _patch_queue(rows), mock.patch(
            "apps.schoolops.email_delivery.send_transactional"
        ) as sender:
            redrive_dead_letters(limit=50)
        sender.assert_not_called()

    def test_a_real_backend_does_not_block(self):
        with override_settings(EMAIL_BACKEND=SMTP), _patch_queue([]):
            summary = redrive_dead_letters(limit=50)
        self.assertEqual(summary["blocked_no_backend"], 0)

    def test_summary_always_carries_the_key(self):
        # drain_edge_outbox reads it unconditionally.
        with override_settings(EMAIL_BACKEND=SMTP), _patch_queue([]):
            self.assertIn("blocked_no_backend", redrive_dead_letters(limit=50))


class DrainCommandSurfacesTheBlockTests(SimpleTestCase):
    def _render(self, summary):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch(
            "apps.schoolops.email_delivery.redrive_dead_letters", return_value=summary
        ):
            call_command("drain_edge_outbox", "--skip-sms", stdout=out, stderr=StringIO())
        return out.getvalue()

    BLOCKED = {
        "scanned": 0, "redriven": 0, "still_pending": 0, "exhausted": 0,
        "abandoned": 0, "enabled": True, "blocked_no_backend": 12,
    }
    EMPTY = {
        "scanned": 0, "redriven": 0, "still_pending": 0, "exhausted": 0,
        "abandoned": 0, "enabled": True, "blocked_no_backend": 0,
    }

    def test_a_blocked_drain_does_not_read_as_an_empty_queue(self):
        blocked = self._render(self.BLOCKED)
        empty = self._render(self.EMPTY)
        self.assertNotEqual(blocked, empty)
        self.assertIn("EMAIL NOT DELIVERED", blocked)
        self.assertIn("12", blocked)

    def test_an_empty_queue_stays_quiet(self):
        self.assertNotIn("EMAIL NOT DELIVERED", self._render(self.EMPTY))

    def test_the_message_says_the_mail_is_intact(self):
        # An operator reading this must not think the queue was lost.
        self.assertIn("intact", self._render(self.BLOCKED))
