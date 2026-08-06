"""Prove the analytics nightly BATCH tasks are woken SURGICALLY.

Four nightly-batch @shared_tasks live in apps/analytics/celery_tasks.py — a
module NOT named tasks.py — so Celery's bare app.autodiscover_tasks()
(config/celery.py) never imported them: their beat entries in config/settings.py
(analytics-compute-nightly-risk / -compute-nightly-grade-predictions /
-build-student-embeddings / -at-risk-drift-watchdog) named UNREGISTERED tasks and
were silent no-ops. apps/analytics/tasks.py now re-exports exactly those four,
so their decorators run and the entries resolve.

The FIFTH analytics beat entry, analytics-send-risk-digest-daily
(analytics.send_risk_digest_all), was woken 2026-08-05: apps/analytics/tasks.py
now re-exports it (so it registers) after send_risk_digest was refactored to
check RiskDigestRecipient BEFORE running the per-school LLM narration (bounding
spend to opted-in schools). The beat entry stays env-gated
(ENABLE_RISK_DIGEST_BEAT) and outbound only reaches enabled recipients.

RULE ZERO: the presence of a @shared_task name in source proves NOTHING about
whether the module is imported. Only the live registry knows. These tests probe
app.tasks after production-equivalent autodiscovery — the positive assertions
in-process (TestCase), and the authoritative "woke ONLY these" snapshot in a
FRESH subprocess (immune to in-process registry pollution from other tests that
may import the deferred module).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from django.test import TestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# The four wrappers woken by apps/analytics/tasks.py.
WOKEN_TASKS = {
    "analytics.compute_nightly_risk",
    "analytics.compute_nightly_grade_predictions",
    "analytics.build_student_embeddings",
    "analytics.check_at_risk_drift_watchdog",
}
# Registered before this fix (from apps/analytics/tasks.py's own @shared_tasks).
PRE_EXISTING_ANALYTICS_TASKS = {
    "analytics.compute_risk_factors",
    "analytics.nightly_risk_factors",
    "analytics.send_deadline_reminders",
}
DEFERRED_TASK = "analytics.send_risk_digest_all"
DEFERRED_BEAT_ENTRY = "analytics-send-risk-digest-daily"

# Beat entry key -> task name it must resolve to once woken (config/settings.py).
WOKEN_BEAT_ENTRIES = {
    "analytics-compute-nightly-risk": "analytics.compute_nightly_risk",
    "analytics-compute-nightly-grade-predictions":
        "analytics.compute_nightly_grade_predictions",
    "analytics-build-student-embeddings": "analytics.build_student_embeddings",
    "analytics-at-risk-drift-watchdog": "analytics.check_at_risk_drift_watchdog",
}


def _in_process_registry() -> set[str]:
    """Live registry after production-equivalent autodiscovery (this process)."""
    from config.celery import app

    app.loader.import_default_modules()
    return set(app.tasks.keys())


_SUBPROCESS_PROBE = (
    "import os, sys, json;"
    "sys.path.insert(0, os.getcwd());"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
    "import django; django.setup();"
    "from config.celery import app;"
    "app.loader.import_default_modules();"
    "print('REGISTRY_JSON:' + json.dumps(sorted(app.tasks.keys())))"
)


def _fresh_subprocess_registry() -> set[str]:
    """Registry from a FRESH interpreter doing exactly what the CI gate does.

    Immune to in-process registry pollution (e.g. another test importing the
    deferred module), so this is the authoritative "what production would
    actually register" snapshot.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_PROBE],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "registry probe subprocess failed:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    line = next(
        (ln for ln in proc.stdout.splitlines() if ln.startswith("REGISTRY_JSON:")),
        None,
    )
    assert line is not None, f"probe emitted no registry line:\n{proc.stdout}"
    return set(json.loads(line[len("REGISTRY_JSON:"):]))


class AnalyticsNightlyBatchRegistrationTests(TestCase):
    # import_default_modules() runs Django system checks; some query the DB.
    databases = "__all__"

    def test_woken_compute_tasks_are_registered(self):
        """Each of the four nightly-batch tasks must resolve in the live registry.

        FAILS on a tree without the tasks.py re-export (invisible to
        autodiscovery); PASSES once re-exported.
        """
        registered = _in_process_registry()
        for name in sorted(WOKEN_TASKS):
            self.assertIn(
                name,
                registered,
                f"{name} is NOT registered — its beat entry is a silent no-op. "
                "Re-export it from apps/analytics/tasks.py.",
            )

    def test_woken_beat_entries_resolve(self):
        """Each woken beat entry (when present) must name a registered task.

        The entries are env-gated (ENABLE_*_BEAT), so assert conditionally: if an
        entry is in the schedule it must resolve; absence is fine (feature off).
        """
        from config.celery import app

        registered = _in_process_registry()
        schedule = app.conf.beat_schedule or {}
        for entry_key, task_name in WOKEN_BEAT_ENTRIES.items():
            if entry_key not in schedule:
                continue
            entry = schedule[entry_key]
            resolved = (
                entry.get("task")
                if isinstance(entry, dict)
                else getattr(entry, "task", None)
            )
            self.assertEqual(resolved, task_name)
            self.assertIn(
                task_name,
                registered,
                f"beat entry {entry_key!r} names {task_name!r}, not registered "
                "— a silent no-op.",
            )


class AnalyticsSurgicalWakeSnapshotTests(TestCase):
    """Authoritative fresh-subprocess proofs (production autodiscovery)."""

    def test_woke_only_the_intended_set_and_nothing_else(self):
        """The analytics.* registry must be EXACTLY the 3 pre-existing + 4 compute
        wrappers + the now-woken risk digest.

        This is the before/after diff proof: no OTHER analytics task woke.
        """
        registry = _fresh_subprocess_registry()
        analytics = {k for k in registry if k.startswith("analytics.")}
        self.assertEqual(
            analytics,
            PRE_EXISTING_ANALYTICS_TASKS | WOKEN_TASKS | {DEFERRED_TASK},
            "analytics.* registry drifted from the intended set.",
        )

    def test_risk_digest_is_now_registered(self):
        """The risk-digest task is now woken (2026-08-05): re-exported from
        apps/analytics/tasks.py after its recipient check moved before narration.
        """
        registry = _fresh_subprocess_registry()
        self.assertIn(
            DEFERRED_TASK,
            registry,
            f"{DEFERRED_TASK} must be registered — it is re-exported from "
            "apps/analytics/tasks.py.",
        )

    def test_gate_exits_zero(self):
        """scripts/verify_beat_task_registry.py must now pass (exit 0)."""
        proc = subprocess.run(
            [sys.executable, str(_REPO_ROOT / "scripts" / "verify_beat_task_registry.py")],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"gate did not exit 0:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )


class AnalyticsDeferredEntryDocumentedTests(TestCase):
    def test_risk_digest_no_longer_in_known_dead(self):
        """The risk-digest entry is woken (2026-08-05) — it must be GONE from the
        baseline (the gate demands the list only shrink when an entry resolves).
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "verify_beat_task_registry",
            _REPO_ROOT / "scripts" / "verify_beat_task_registry.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        known = module.KNOWN_DEAD_ENTRIES
        self.assertNotIn(
            DEFERRED_BEAT_ENTRY,
            known,
            f"{DEFERRED_BEAT_ENTRY} was woken; it must not be in KNOWN_DEAD_ENTRIES.",
        )
        # The four earlier-woken compute entries must also not be listed as dead.
        for entry_key in WOKEN_BEAT_ENTRIES:
            self.assertNotIn(
                entry_key,
                known,
                f"{entry_key} was woken; it must not be in KNOWN_DEAD_ENTRIES.",
            )
