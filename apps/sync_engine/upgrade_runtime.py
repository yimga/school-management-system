"""Quiet the box while it is being upgraded, then bring it back.

Three things have to stop happening during an upgrade, and each has a different owner:

  * **user writes** — a bursar issuing a receipt against a schema that is mid-migration;
  * **background workers** — a Celery task doing the same thing with nobody watching;
  * **the old code** — which keeps serving from memory until the workers reload.

None of them can be solved by inventing new machinery here, and all three attempts to do
so would be worse than reusing what the box already has.

WRITES: the platform already ships ``MaintenanceModeMiddleware``, already allowlists
``/health/`` (so the blue-green gate still works), already exempts superusers, and already
renders a branded 503. What it reads is a DB-backed singleton — which is exactly the wrong
source during a migration. But it consults its CACHE first, so a freeze here is a cache
write and nothing else: no DB round trip, no schema dependency, no new middleware, and no
new 503 template. The key is deleted at the end, so the database value is re-read and the
freeze cannot outlive the upgrade even if this process dies (it also carries a TTL).

WORKERS: a management command cannot kill the Celery process that started it, and
pretending otherwise would produce a spin-down that silently no-ops. What it CAN do is
tell the workers to stop consuming, over the broker they are already connected to. With no
broker there is nothing to pause and the honest answer is to say so.

RELOAD: the same. Swapping a ``.py`` under a running interpreter changes nothing until the
process restarts, so the manager sends the master a HUP where it can find one — a pidfile
the operator configured, or an explicit command — and where it can find neither it REPORTS
that the swap needs a container restart rather than implying a reload it never performed.
Every path is opt-in configuration, because guessing at a PID and signalling it is how you
kill a school's web server at 09:41 on a Tuesday.
"""
from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess  # noqa: S404 - operator-configured argv, never a shell string

from django.conf import settings

logger = logging.getLogger(__name__)

# The key MaintenanceModeMiddleware reads before it consults the database.
_MAINTENANCE_BASE_KEY = "site_settings_v1"

_DEFAULT_FREEZE_TTL_SECONDS = 1800  # magic-number-allow: write-freeze ceiling (30m)
_RELOAD_SIGNAL_TIMEOUT = 10  # magic-number-allow: seconds to wait on a reload command
# Enough of a failing command's stderr to diagnose it, bounded so a chatty tool cannot
# push a 4 KB wall of text into an upgrade log line.
_COMMAND_STDERR_MAX_CHARS = 160  # magic-number-allow: stderr excerpt in an outcome line


def _setting(name, default):
    return getattr(settings, name, default)


def freeze_ttl_seconds() -> int:
    """Ceiling on the write freeze.

    A freeze with no expiry is a school locked out of its own system because an upgrade
    died between the freeze and the thaw. Everything below is best-effort; this is the
    guarantee.
    """
    try:
        return max(60, int(_setting("RMC_OTA_WRITE_FREEZE_TTL_SECONDS", _DEFAULT_FREEZE_TTL_SECONDS)))
    except (TypeError, ValueError):
        return _DEFAULT_FREEZE_TTL_SECONDS


def _maintenance_key() -> str:
    from apps.siteconfig.cache_utils import tenant_cache_key

    # No request to scope by — correct on an edge box, which serves exactly one tenant, so
    # the prefix this resolves to is the same one a request on that box would produce.
    return tenant_cache_key(_MAINTENANCE_BASE_KEY, None)


def freeze_writes() -> bool:
    """Put the box into the maintenance 503 for everyone except superusers.

    Returns whether the freeze was actually installed. False is a legitimate outcome (no
    usable cache) and the caller reports it rather than proceeding as if writes stopped.
    """
    if not bool(_setting("RMC_OTA_FREEZE_WRITES", True)):
        return False
    try:
        from django.core.cache import cache

        cache.set(_maintenance_key(), {"maintenance_mode": True}, freeze_ttl_seconds())
        return True
    except Exception:  # noqa: BLE001 - a freeze we cannot install is reported, not fatal
        logger.debug("ota: could not install the write freeze", exc_info=True)
        return False


def thaw_writes() -> bool:
    """Remove the freeze. Deleting rather than writing False, so the DB value is re-read.

    Writing ``{"maintenance_mode": False}`` would PIN the box out of maintenance for the
    cache TTL — including a maintenance mode an operator had switched on deliberately
    before the upgrade started. Deleting restores whatever the database actually says.
    """
    try:
        from django.core.cache import cache

        cache.delete(_maintenance_key())
        return True
    except Exception:  # noqa: BLE001
        logger.debug("ota: could not lift the write freeze", exc_info=True)
        return False


def writes_frozen() -> bool:
    try:
        from django.core.cache import cache

        value = cache.get(_maintenance_key())
        return bool(isinstance(value, dict) and value.get("maintenance_mode"))
    except Exception:  # noqa: BLE001
        return False


# ── background workers ───────────────────────────────────────────────────────
def _celery_control():
    """The Celery control interface, or ``None`` when there is no broker to talk to."""
    if not str(_setting("CELERY_BROKER_URL", "") or "").strip():
        return None
    try:
        from config.celery import app  # noqa: PLC0415 - optional, boot-order sensitive

        return app.control
    except Exception:  # noqa: BLE001 - no celery, no broker, nothing to pause
        logger.debug("ota: celery control unavailable", exc_info=True)
        return None


def pause_workers() -> str:
    """Stop background workers consuming new tasks. Returns a human-readable outcome.

    ``cancel_consumer`` rather than ``shutdown``: a paused worker finishes what it is
    already holding and then idles, which is a drain. Shutting it down would abandon
    in-flight work, and an upgrade that loses a queued receipt to protect a schema has
    traded one data problem for another.
    """
    command = str(_setting("RMC_OTA_WORKER_PAUSE_COMMAND", "") or "").strip()
    if command:
        return _run_operator_command(command, "pause")
    control = _celery_control()
    if control is None:
        return "no broker configured; no background workers to pause"
    try:
        control.cancel_consumer(_default_queue())
        return f"workers told to stop consuming {_default_queue()!r}"
    except Exception as exc:  # noqa: BLE001
        return f"could not pause workers ({exc})"


def resume_workers() -> str:
    """Undo :func:`pause_workers`. Always attempted, including after a failed upgrade."""
    command = str(_setting("RMC_OTA_WORKER_RESUME_COMMAND", "") or "").strip()
    if command:
        return _run_operator_command(command, "resume")
    control = _celery_control()
    if control is None:
        return "no broker configured; nothing to resume"
    try:
        control.add_consumer(_default_queue())
        return f"workers resumed on {_default_queue()!r}"
    except Exception as exc:  # noqa: BLE001
        return f"could not resume workers ({exc})"


def _default_queue() -> str:
    return str(_setting("CELERY_TASK_DEFAULT_QUEUE", "") or "celery")


# ── web workers ──────────────────────────────────────────────────────────────
def reload_workers() -> str:
    """Ask the web server to re-exec on the new code. Returns what actually happened.

    Three configured paths and one honest refusal, in order:

    1. ``RMC_OTA_WORKER_RELOAD_COMMAND`` — an explicit argv the operator chose
       (``supervisorctl restart web``, ``docker compose kill -s HUP web``). Split with
       ``shlex``, never handed to a shell.
    2. ``RMC_OTA_WORKER_RELOAD_PIDFILE`` — a gunicorn/uwsgi master pid. HUP is gunicorn's
       graceful reload: it starts new workers on the new code and retires the old ones as
       they finish their current request.
    3. Neither — report that the swap needs a container restart. It does NOT go hunting
       for a plausible parent process to signal, because a wrong guess kills a school's
       web server.
    """
    command = str(_setting("RMC_OTA_WORKER_RELOAD_COMMAND", "") or "").strip()
    if command:
        return _run_operator_command(command, "reload")

    pidfile = str(_setting("RMC_OTA_WORKER_RELOAD_PIDFILE", "") or "").strip()
    if pidfile:
        try:
            with open(pidfile, encoding="utf-8") as handle:
                pid = int(handle.read().strip())
        except (OSError, ValueError) as exc:
            return f"reload skipped: unreadable pidfile {pidfile} ({exc})"
        hup = getattr(signal, "SIGHUP", None)
        if hup is None:
            return "reload skipped: this platform has no SIGHUP (Windows)"
        try:
            os.kill(pid, hup)
            return f"SIGHUP sent to master pid {pid} (graceful reload)"
        except OSError as exc:
            return f"reload failed: could not signal pid {pid} ({exc})"

    return (
        "reload NOT configured — python already imported stays imported, so this swap "
        "reaches users on the next container restart. Set RMC_OTA_WORKER_RELOAD_COMMAND "
        "or RMC_OTA_WORKER_RELOAD_PIDFILE to make it immediate."
    )


def _run_operator_command(command: str, label: str) -> str:
    """Run an operator-configured argv. Never a shell string — see scan_subprocess_shell_true."""
    argv = shlex.split(command)
    if not argv:
        return f"{label} skipped: empty command"
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, shell=False, operator-configured
            argv,
            capture_output=True,
            text=True,
            timeout=_RELOAD_SIGNAL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{label} failed: {argv[0]} ({exc})"
    if completed.returncode != 0:
        return f"{label} command exited {completed.returncode}: {(completed.stderr or '').strip()[:_COMMAND_STDERR_MAX_CHARS]}"
    return f"{label} command ok: {' '.join(argv[:3])}"


__all__ = [
    "freeze_ttl_seconds",
    "freeze_writes",
    "thaw_writes",
    "writes_frozen",
    "pause_workers",
    "resume_workers",
    "reload_workers",
]
