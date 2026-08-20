"""Walk the ENTIRE box<->cloud chain and name the first link that is broken.

    python manage.py verify_edge_link            # offline checks only
    python manage.py verify_edge_link --http     # ...plus live calls to the cloud
    python manage.py verify_edge_link --json     # machine-readable, for the runbook

WHY A NEW COMMAND. The pieces were already checkable, one at a time, by someone who
knew which of a dozen commands to run and in what order. That is the wrong shape for
the question people actually ask, which is "is this box talking to the cloud, yes or
no?" -- and the wrong shape for an installer standing in a server room. Worse, the
existing tools each answered about their own layer, so a box could pass every one of
them individually and still not sync, because nothing checked that the SCHEDULER was
driving cycles at all.

Each check answers one question, in the order the data actually flows, and stops being
interesting once an earlier one fails -- a credential check is noise when the host does
not resolve. Every failure carries the command that fixes it, because a diagnosis an
operator cannot act on is just a more precise way of being stuck.

Writes nothing, on either side. ``--http`` makes real requests to the cloud: the pull
probe is an ordinary bundle GET and the push probe is an empty body the cloud rejects
by design. The one thing this command can CHANGE is process-local and deliberate —
the scheduler check registers the sync job if this box became an edge box after the
process started, which is the same thing the next scan tick would have done anyway.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"

_SYMBOL = {PASS: "[ok]", FAIL: "[FAIL]", WARN: "[warn]", SKIP: "[--]"}

# A box that has not synced in this long is not "quiet", it is stuck. Five intervals of
# the 180s default: long enough to absorb a missed tick and a slow cycle, short enough
# that a genuinely wedged box does not read as healthy.
_STALE_RUN_SECONDS = 900


class Command(BaseCommand):
    help = "Verify the box<->cloud sync link end to end and report the first broken link."

    def add_arguments(self, parser):
        parser.add_argument(
            "--http",
            action="store_true",
            help="Make live requests to the cloud (reachability + credential).",
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
        parser.add_argument(
            "--timeout", type=float, default=20.0, help="HTTP timeout in seconds (default 20)."
        )

    def handle(self, *args, **options):
        checks: list[dict] = []

        def add(name, status, detail, fix=""):
            checks.append({"check": name, "status": status, "detail": detail, "fix": fix})
            return status

        # 1 -- is this deployment even meant to sync? --------------------------------
        from apps.sync_engine.edge_enabled import why

        verdict = why()
        if verdict["enabled"]:
            add("deployment", PASS, f"edge sync is live - {verdict['reason']}")
        elif not verdict["sovereign_box"]:
            add(
                "deployment",
                SKIP,
                "this is a cloud deployment, not a sovereign box - nothing to verify",
            )
            return self._emit(checks, options, exit_on_fail=False)
        else:
            add(
                "deployment",
                FAIL,
                f"edge sync is off - {verdict['reason']}",
                "python manage.py pair_box --wait   (or set RMC_EDGE_SYNC_ENABLED=1)",
            )

        # 2 -- does the box know WHERE its cloud is, and who it is? -------------------
        from apps.sync_engine.edge_binding import binding_summary

        binding = binding_summary()
        if binding["operator_base"]:
            add(
                "cloud address",
                PASS,
                f"{binding['operator_base']} (source: {binding['source']})",
            )
        else:
            add(
                "cloud address",
                FAIL,
                "this box does not know where its cloud is",
                "python manage.py pair_box   (or set RMC_EDGE_SCHOOL_SLUG so it can be derived)",
            )

        if binding["paired"]:
            expiry = binding["credential_expires_at"]
            add(
                "credential",
                PASS,
                f"held for {binding['school_slug'] or '?'}"
                + (f", expires {expiry}" if expiry else ", no expiry"),
            )
        else:
            add(
                "credential",
                FAIL,
                "no usable credential - this box has never completed a pairing",
                "python manage.py pair_box --wait",
            )

        # 3 -- which school is this box FOR? -----------------------------------------
        from apps.sync_engine.edge_scheduler import resolve_edge_school

        try:
            school = resolve_edge_school()
        except Exception:  # noqa: BLE001 — an unmigrated box still deserves a report
            school = None
        if school is not None:
            add("school", PASS, f"{school.slug} ({school.name})")
        else:
            add(
                "school",
                FAIL,
                "cannot resolve which school this box serves (none, or more than one)",
                "set RMC_EDGE_SCHOOL_SLUG to pin it",
            )

        # 4 -- is anything actually DRIVING the cycle? --------------------------------
        # The check nothing else made. A box can be perfectly configured and simply
        # never run, which looks identical from the cloud to a box that is offline.
        self._check_scheduler(add)
        if school is not None:
            self._check_recent_runs(add, school)
            self._check_directives(add, school)
            self._check_pending_confirmations(add, school)

        # 5 -- live, if asked ---------------------------------------------------------
        if options["http"]:
            self._check_http(add, options["timeout"])
        else:
            add("cloud reachability", SKIP, "not probed - re-run with --http")

        return self._emit(checks, options)

    # ------------------------------------------------------------------ checks --
    def _check_scheduler(self, add):
        try:
            from apps.platform_runtime.periodic import (
                EDGE_SYNC_JOB_NAME,
                ensure_edge_sync_job_registered,
            )

            registered = ensure_edge_sync_job_registered()
        except Exception as exc:  # noqa: BLE001
            add("scheduler", WARN, f"could not inspect the job registry ({exc})")
            return
        if registered:
            add("scheduler", PASS, f"{EDGE_SYNC_JOB_NAME} is registered in this process")
        else:
            add(
                "scheduler",
                FAIL,
                "no sync job is registered - nothing in this process will ever run a cycle",
                "this follows from an earlier failure; fix that first",
            )

    def _check_recent_runs(self, add, school):
        from django.utils import timezone

        from apps.sync_engine.models import EdgeSyncRun

        try:
            run = EdgeSyncRun.objects.filter(school=school).order_by("-created_at").first()
        except Exception as exc:  # noqa: BLE001 — a box mid-migration must still report
            add("recent activity", WARN, f"could not inspect ({exc})")
            return
        if run is None:
            add(
                "recent activity",
                WARN,
                "this box has never recorded a sync cycle",
                "python manage.py edge_autosync   (runs one now)",
            )
            return
        age = int((timezone.now() - run.created_at).total_seconds())
        summary = (
            f"last cycle {age}s ago: ok={run.ok} pushed={run.pushed} "
            f"pulled={run.pulled} deleted={run.deleted}"
        )
        if age > _STALE_RUN_SECONDS:
            add(
                "recent activity",
                WARN,
                f"{summary} - that is stale; the scheduler may not be ticking",
                "check that /health/ is being reached, or run edge_autosync from cron",
            )
        elif not run.ok:
            add(
                "recent activity",
                WARN,
                f"{summary} - {run.error or run.message or 'no detail'}",
            )
        else:
            add("recent activity", PASS, summary)

    def _check_directives(self, add, school):
        """The cloud->box channel: is anything queued, and is it being collected?"""
        from django.utils import timezone

        from apps.sync_engine.models import EdgeSyncDirective

        try:
            pending = (
                EdgeSyncDirective.objects.filter(school=school, served_at__isnull=True)
                .order_by("requested_at")
                .first()
            )
        except Exception as exc:  # noqa: BLE001
            add("cloud directives", WARN, f"could not inspect ({exc})")
            return
        if pending is None:
            add("cloud directives", PASS, "nothing queued for this box")
            return
        age = int((timezone.now() - pending.requested_at).total_seconds())
        if age > _STALE_RUN_SECONDS:
            add(
                "cloud directives",
                FAIL,
                f"'{pending.kind}' has been waiting {age}s and the box has not collected it",
                "the box is not reaching the cloud - re-run with --http",
            )
        else:
            add(
                "cloud directives",
                WARN,
                f"'{pending.kind}' queued {age}s ago, not yet collected (normal briefly)",
            )

    def _check_pending_confirmations(self, add, school):
        try:
            from apps.sync_engine.models_pairing import PendingPushConfirmation

            count = PendingPushConfirmation.objects.filter(school=school).count()
        except Exception as exc:  # noqa: BLE001
            add("ambiguous pushes", WARN, f"could not inspect ({exc})")
            return
        if count:
            add(
                "ambiguous pushes",
                WARN,
                f"{count} push(es) whose outcome is unknown - the next cycle asks the cloud",
            )
        else:
            add("ambiguous pushes", PASS, "none outstanding")

    def _check_http(self, add, timeout):
        from apps.sync_engine.connectivity_probe import probe_cloud_http

        try:
            result = probe_cloud_http(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            add("cloud reachability", FAIL, f"probe raised: {exc}")
            return
        probes = result.get("probes") or {}

        # A 401/403 is a REACHABILITY pass and a CREDENTIAL failure. Collapsing them
        # into one verdict is how "the cloud is down" gets blamed for a bad token.
        for name in ("pull", "push"):
            probe = probes.get(name) or {}
            status = probe.get("status")
            detail = probe.get("detail") or ""
            if status == 0:
                add(
                    f"cloud {name}",
                    FAIL,
                    detail,
                    "check DNS, the box's internet, and the base URL",
                )
            elif status in (401, 403):
                add(
                    f"cloud {name}",
                    FAIL,
                    f"reachable, but the credential was refused (HTTP {status}) - {detail}",
                    "python manage.py pair_box --unpair --yes && python manage.py pair_box --wait",
                )
            elif status == 404:
                add(
                    f"cloud {name}",
                    FAIL,
                    f"reachable, but the sync endpoint is missing (HTTP 404) - {detail}",
                    "the cloud is on a build older than this box; deploy the cloud first",
                )
            elif status in (502, 503, 504):
                add(
                    f"cloud {name}",
                    FAIL,
                    f"gateway error HTTP {status} - the cloud's proxy answered, the app did not",
                    "check the cloud's application logs; this is not a box-side fault",
                )
            elif status is None:
                add(f"cloud {name}", WARN, "no result returned by the probe")
            else:
                add(f"cloud {name}", PASS, f"HTTP {status} - {detail}")

    # ------------------------------------------------------------------ output --
    def _emit(self, checks, options, *, exit_on_fail=True):
        failed = [c for c in checks if c["status"] == FAIL]
        if options["json"]:
            self.stdout.write(json.dumps({"ok": not failed, "checks": checks}, indent=2))
            if failed and exit_on_fail:
                raise SystemExit(1)
            return

        self.stdout.write("Box <-> cloud link")
        self.stdout.write("")
        styles = {
            PASS: self.style.SUCCESS,
            FAIL: self.style.ERROR,
            WARN: self.style.WARNING,
            SKIP: str,
        }
        for c in checks:
            line = f"  {_SYMBOL[c['status']]:>6}  {c['check']:<20} {c['detail']}"
            self.stdout.write(styles[c["status"]](line))
            if c["fix"] and c["status"] == FAIL:
                self.stdout.write(f"          -> {c['fix']}")
        self.stdout.write("")
        if failed:
            self.stdout.write(
                self.style.ERROR(
                    f"{len(failed)} broken link(s). Fix the FIRST one - the rest are "
                    "usually consequences of it."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Every checked link is good."))
        if failed and exit_on_fail:
            # Non-zero so this can gate a deploy step or a runbook check.
            raise SystemExit(1)
