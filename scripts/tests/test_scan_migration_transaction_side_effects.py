"""Stdlib unittest coverage for ``scan_migration_transaction_side_effects``.

MUST-FIRE tests: the scanner must FLAG the deploy-abort pattern (DB op inside a
broad swallowing except) and category-(b) I/O, and must NOT flag the safe patterns
(nested-atomic savepoint, re-raise, pure-Python except, allow-marker). The
``test_live_tree_is_clean`` case doubles as the live calibration.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan_migration_transaction_side_effects as s  # noqa: E402


def _cats(findings):
    return {f["category"] for f in findings}


class DbOpInBroadExceptTests(unittest.TestCase):
    def test_flags_db_op_swallowed_by_broad_except(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        cur.execute('DROP INDEX x')\n"
            "    except Exception:\n"
            "        pass\n"
        )
        out = s.scan_source(src, "apps/x/migrations/0001_x.py")
        self.assertEqual(len(out), 1, out)
        self.assertEqual(out[0]["category"], "db-op-in-broad-except")

    def test_flags_orm_save_and_iterator(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        for r in M.objects.all().iterator():\n"
            "            r.save()\n"
            "    except Exception:\n"
            "        pass\n"
        )
        out = s.scan_source(src, "apps/x/migrations/0001_x.py")
        # both .iterator() and .save() are unprotected DB ops
        self.assertEqual(len(out), 2, out)
        self.assertTrue(all(f["category"] == "db-op-in-broad-except" for f in out))

    def test_bare_except_is_broad(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        cur.execute('x')\n"
            "    except:\n"
            "        pass\n"
        )
        out = s.scan_source(src, "apps/x/migrations/0001_x.py")
        self.assertEqual(len(out), 1, out)

    def test_tuple_including_Exception_is_broad(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        cur.execute('x')\n"
            "    except (ValueError, Exception):\n"
            "        pass\n"
        )
        self.assertEqual(len(s.scan_source(src, "apps/x/migrations/0001_x.py")), 1)


class SafePatternsNotFlaggedTests(unittest.TestCase):
    def test_nested_atomic_savepoint_is_safe(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        with transaction.atomic(using=se.connection.alias):\n"
            "            cur.execute('DROP INDEX x')\n"
            "    except Exception:\n"
            "        pass\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])

    def test_reraising_handler_is_safe(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        cur.execute('x')\n"
            "    except Exception:\n"
            "        raise\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])

    def test_savepoint_rollback_handler_is_safe(self):
        src = (
            "def f(apps, se):\n"
            "    sid = conn.savepoint()\n"
            "    try:\n"
            "        cur.execute('x')\n"
            "    except Exception:\n"
            "        conn.savepoint_rollback(sid)\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])

    def test_narrow_except_not_flagged(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        cur.execute('x')\n"
            "    except (ProgrammingError, OperationalError):\n"
            "        pass\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])

    def test_pure_python_except_not_flagged(self):
        # get_field / getattr / json.dumps in a broad except -> no DB op -> safe.
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        fld = Model._meta.get_field('slug')\n"
            "        val = getattr(site, 'x')\n"
            "    except Exception:\n"
            "        pass\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])

    def test_db_op_outside_the_broad_except_not_flagged(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        v = normalize(code)\n"
            "    except Exception:\n"
            "        v = None\n"
            "    M.objects.filter(x=1).update(y=v)\n"
        )
        # .update() sits OUTSIDE the try body (and 'update' isn't in the op set)
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])


class IoInMigrationTests(unittest.TestCase):
    def test_flags_send_mail(self):
        src = "def f(apps, se):\n    send_mail('s', 'b', 'from', ['to'])\n"
        out = s.scan_source(src, "apps/x/migrations/0001_x.py")
        self.assertEqual(_cats(out), {"io-in-migration"})

    def test_flags_celery_delay(self):
        src = "def f(apps, se):\n    my_task.delay(1)\n"
        self.assertEqual(_cats(s.scan_source(src, "apps/x/migrations/0001_x.py")), {"io-in-migration"})

    def test_flags_requests_post(self):
        src = "def f(apps, se):\n    requests.post('http://x')\n"
        self.assertEqual(_cats(s.scan_source(src, "apps/x/migrations/0001_x.py")), {"io-in-migration"})

    def test_flags_email_message_ctor(self):
        src = "def f(apps, se):\n    EmailMessage('s', 'b').send()\n"
        self.assertIn("io-in-migration", _cats(s.scan_source(src, "apps/x/migrations/0001_x.py")))


class MarkerTests(unittest.TestCase):
    def test_allow_marker_same_line_suppresses(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        cur.execute('x')  # migration-side-effect-allow: reviewed\n"
            "    except Exception:\n"
            "        pass\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])

    def test_allow_marker_line_above_suppresses(self):
        src = (
            "def f(apps, se):\n"
            "    try:\n"
            "        # migration-side-effect-allow: reviewed\n"
            "        cur.execute('x')\n"
            "    except Exception:\n"
            "        pass\n"
        )
        self.assertEqual(s.scan_source(src, "apps/x/migrations/0001_x.py"), [])


class LiveTreeTests(unittest.TestCase):
    def test_live_tree_is_clean(self):
        # Calibration: the real migration tree must have zero findings. Fails the
        # instant a new deploy-abort-class migration lands.
        findings = s.scan_tree()
        self.assertEqual(findings, [], f"migration side-effect findings: {findings}")


if __name__ == "__main__":
    unittest.main()
