"""Resource-aware Gunicorn sizing (services/web_runtime.py).

cpu/mem are injected so these assert the SIZING LOGIC deterministically,
independent of the test host. SimpleTestCase: pure computation, no DB.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from services.web_runtime import plan_web_runtime

GIB = 1024 * 1024 * 1024
TWO_GB = 2 * GIB
EIGHT_GB = 8 * GIB


class WebRuntimePlanTests(SimpleTestCase):
    def _plan(self, env, cpu=1.0, mem=TWO_GB):
        return plan_web_runtime(env, effective_cpu=cpu, memory_bytes=mem)

    # ── worker count precedence ──────────────────────────────────────────────
    def test_explicit_workers_win_and_skip_autoscale(self):
        plan = self._plan({"GUNICORN_WORKERS": "5"}, cpu=1.0, mem=TWO_GB)
        self.assertEqual(plan.workers, 5)
        self.assertEqual(plan.rationale["decided_by"], "explicit_workers")

    def test_autoscale_off_falls_back_to_web_concurrency(self):
        plan = self._plan({"GUNICORN_AUTOSCALE": "0", "WEB_CONCURRENCY": "3"})
        self.assertEqual(plan.workers, 3)
        self.assertEqual(plan.rationale["decided_by"], "web_concurrency")

    def test_standard_box_is_memory_bound_to_two_workers(self):
        # 2GB/1CPU with 600MB/worker + 400MB headroom -> (2048-400)//600 = 2.
        plan = self._plan({}, cpu=1.0, mem=TWO_GB)
        self.assertEqual(plan.workers, 2)
        self.assertEqual(plan.rationale["decided_by"], "memory")

    def test_db_connection_budget_can_bind_workers(self):
        # Plenty of RAM/CPU, but DB budget 12 / 4 threads = 3 workers max.
        plan = plan_web_runtime(
            {"DB_MAX_APP_CONNECTIONS": "12", "GUNICORN_THREADS": "4"},
            effective_cpu=4.0,
            memory_bytes=EIGHT_GB,
        )
        self.assertEqual(plan.workers, 3)
        self.assertEqual(plan.rationale["decided_by"], "db_connections")

    def test_max_workers_caps_the_result(self):
        plan = plan_web_runtime(
            {"GUNICORN_MAX_WORKERS": "2"},
            effective_cpu=8.0,
            memory_bytes=EIGHT_GB,
        )
        self.assertEqual(plan.workers, 2)

    def test_never_returns_zero_workers(self):
        plan = plan_web_runtime({}, effective_cpu=0.1, memory_bytes=128 * 1024 * 1024)
        self.assertGreaterEqual(plan.workers, 1)

    # ── threads + SSE reserve coupling ───────────────────────────────────────
    def test_gthread_threads_keep_sse_reserve_plus_one(self):
        plan = self._plan(
            {"GUNICORN_THREADS": "2", "SSE_THREAD_RESERVE": "2", "GUNICORN_WORKER_CLASS": "gthread"}
        )
        self.assertEqual(plan.threads, 3)  # max(2, reserve+1)

    def test_explicit_threads_respected_when_above_reserve(self):
        plan = self._plan({"GUNICORN_THREADS": "6", "SSE_THREAD_RESERVE": "2"})
        self.assertEqual(plan.threads, 6)

    # ── crash-loop guards ────────────────────────────────────────────────────
    def test_max_requests_default_and_jitter_ratio(self):
        plan = self._plan({})
        self.assertEqual(plan.max_requests, 400)
        self.assertEqual(plan.max_requests_jitter, 80)  # 20% of 400

    def test_max_requests_env_override(self):
        plan = self._plan({"GUNICORN_MAX_REQUESTS": "1000", "GUNICORN_MAX_REQUESTS_JITTER": "50"})
        self.assertEqual(plan.max_requests, 1000)
        self.assertEqual(plan.max_requests_jitter, 50)

    def test_max_requests_can_be_disabled(self):
        plan = self._plan({"GUNICORN_MAX_REQUESTS": "0"})
        self.assertEqual(plan.max_requests, 0)
        self.assertEqual(plan.max_requests_jitter, 0)

    def test_preload_default_on_and_overridable(self):
        self.assertTrue(self._plan({}).preload_app)
        self.assertFalse(self._plan({"GUNICORN_PRELOAD": "0"}).preload_app)

    def test_worker_tmp_dir_explicit_env_wins(self):
        plan = self._plan({"GUNICORN_WORKER_TMP_DIR": "/tmp/rmc-shm"})
        self.assertEqual(plan.worker_tmp_dir, "/tmp/rmc-shm")

    def test_timeout_and_graceful_parsing(self):
        plan = self._plan({"GUNICORN_TIMEOUT": "90", "GUNICORN_GRACEFUL_TIMEOUT": "20"})
        self.assertEqual(plan.timeout, 90)
        self.assertEqual(plan.graceful_timeout, 20)

    def test_rationale_exposes_detected_resources(self):
        plan = self._plan({}, cpu=1.0, mem=TWO_GB)
        self.assertEqual(plan.rationale["memory_mb"], 2048)
        self.assertEqual(plan.rationale["effective_cpu"], 1.0)
        self.assertEqual(plan.rationale["cpu_workers"], 3)
        self.assertEqual(plan.rationale["mem_workers"], 2)
