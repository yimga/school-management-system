"""Nuance engine must not use SIGALRM outside the main thread (Gunicorn gthread)."""

from __future__ import annotations

import signal
import threading
from concurrent.futures import ThreadPoolExecutor

from django.test import SimpleTestCase

from apps.policies.grading_nuance_templates import REPORT_CARD_AVG_WEIGHTED
from apps.siteconfig.nuance_engine import (
    _run_with_timeout,
    _sigalrm_timeout_available,
    default_test_contexts_for_hook,
    evaluate_json_logic,
    verify_nuance_safety,
)

_REPORT_CARD_TEST_CONTEXTS = default_test_contexts_for_hook("report_card_avg")


class NuanceEngineWorkerThreadTimeoutTests(SimpleTestCase):
    def test_sigalrm_not_used_on_worker_thread(self):
        if not hasattr(signal, "SIGALRM"):
            self.skipTest("SIGALRM unavailable on this platform")
        holder: dict[str, bool] = {}

        def probe():
            holder["sigalrm"] = _sigalrm_timeout_available()

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(holder.get("sigalrm"))

    def test_verify_nuance_safety_from_worker_thread(self):
        def run_verify():
            return verify_nuance_safety(
                REPORT_CARD_AVG_WEIGHTED,
                _REPORT_CARD_TEST_CONTEXTS,
                reject_negative_fee=False,
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            ok, err = pool.submit(run_verify).result(timeout=5)
        self.assertTrue(ok, err)

    def test_evaluate_json_logic_from_worker_thread(self):
        ctx = _REPORT_CARD_TEST_CONTEXTS[0]

        def run_eval():
            return evaluate_json_logic(REPORT_CARD_AVG_WEIGHTED, ctx)

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(run_eval).result(timeout=5)
        self.assertAlmostEqual(float(result), 7.0)

    def test_run_with_timeout_from_worker_thread_returns_numeric_result(self):
        ctx = _REPORT_CARD_TEST_CONTEXTS[0]

        def run_eval():
            return _run_with_timeout(REPORT_CARD_AVG_WEIGHTED, ctx)

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(run_eval).result(timeout=5)
        self.assertAlmostEqual(float(result), 7.0)
