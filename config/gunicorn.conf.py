# Gunicorn config for Render and other PaaS.
#
# Sizing is resource-aware: services/web_runtime.py reads the container's REAL
# cgroup CPU/RAM allocation + the DB connection budget and picks workers/threads
# that fit, plus the anti-crash settings (worker recycling, preload, /dev/shm
# heartbeat). Everything is env-configurable; set GUNICORN_WORKERS to pin an
# explicit count or GUNICORN_AUTOSCALE=0 to disable autoscaling. If the planner
# can't be imported for any reason we fall back to the old static behavior so
# the process always boots.
import os
import re
import sys

# Always bind HTTP to 0.0.0.0:PORT so the platform's port scan detects the service.
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
accesslog = "-"
errorlog = "-"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    match = re.match(r"\s*(\d+)", str(raw))
    return int(match.group(1)) if match else default


try:
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:  # exec'd without __file__ (e.g. a config sanity check)
    _here = os.path.abspath(os.path.join(os.getcwd(), "config"))
_ROOT = os.path.dirname(_here)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from services.web_runtime import plan_web_runtime

    _plan = plan_web_runtime(os.environ)
    workers = _plan.workers
    threads = _plan.threads
    worker_class = _plan.worker_class
    timeout = _plan.timeout
    graceful_timeout = _plan.graceful_timeout
    max_requests = _plan.max_requests
    max_requests_jitter = _plan.max_requests_jitter
    preload_app = _plan.preload_app
    if _plan.worker_tmp_dir:
        worker_tmp_dir = _plan.worker_tmp_dir

    # Surface the resolved plan to workers (read back by /health/) and the log.
    os.environ["RMC_WEB_RESOLVED_WORKERS"] = str(workers)
    os.environ["RMC_WEB_RESOLVED_THREADS"] = str(threads)
    os.environ["RMC_WEB_RESOLVED_MAX_REQUESTS"] = str(max_requests)
    os.environ["RMC_WEB_RESOLVED_PRELOAD"] = "1" if preload_app else "0"
    os.environ["RMC_WEB_SIZING_DECIDED_BY"] = str(_plan.rationale.get("decided_by", ""))

    print(
        "[gunicorn] resource-aware plan: "
        f"workers={workers} threads={threads} class={worker_class} "
        f"max_requests={max_requests}(+{max_requests_jitter}) "
        f"preload={preload_app} tmp_dir={_plan.worker_tmp_dir} "
        f"timeout={timeout} graceful={graceful_timeout} | {_plan.rationale}",
        flush=True,
    )
except Exception as exc:  # noqa: BLE001 - never let sizing break process boot
    # Static fallback (the prior behavior): env-driven, conservative defaults.
    worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
    workers = _int_env("WEB_CONCURRENCY", 1)
    threads = _int_env("GUNICORN_THREADS", 4)
    timeout = _int_env("GUNICORN_TIMEOUT", 120)
    max_requests = _int_env("GUNICORN_MAX_REQUESTS", 400)
    max_requests_jitter = _int_env("GUNICORN_MAX_REQUESTS_JITTER", 80)
    graceful_timeout = _int_env("GUNICORN_GRACEFUL_TIMEOUT", 30)
    print(
        f"[gunicorn] resource-aware sizing unavailable ({exc!r}); "
        f"using static config workers={workers} threads={threads}",
        flush=True,
    )
